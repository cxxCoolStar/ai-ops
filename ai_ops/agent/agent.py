import argparse
import json
import os
import time
import urllib.request
import uuid
import re
import hashlib

from ai_ops import config
from ai_ops.monitoring.log_monitor import start_monitoring


def _post_json(url, payload, api_key=None, timeout=15):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _get_nested(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _elk_search(elk_url, index, query, size=50, since_seconds=300, search_after=None, timeout=15):
    base = (elk_url or "").rstrip("/")
    idx = (index or "").strip()
    if not base:
        raise ValueError("elk_url is required")
    if not idx:
        raise ValueError("elk_index is required")
    body = {
        "size": int(size),
        "sort": [{"@timestamp": "asc"}, {"event.id": "asc"}],
        "query": {
            "bool": {
                "must": [{"query_string": {"query": str(query or "").strip()}}],
                "filter": [{"range": {"@timestamp": {"gte": f"now-{int(since_seconds)}s"}}}],
            }
        },
        "_source": True,
    }
    if search_after:
        body["search_after"] = search_after
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{base}/{idx}/_search", data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    payload = json.loads(raw) if raw else {}
    hits = (((payload.get("hits") or {}).get("hits")) or []) if isinstance(payload, dict) else []
    return hits


def _elk_hit_to_error_text(hit):
    src = hit.get("_source") or {}
    msg = (
        _get_nested(src, "error", "stack_trace")
        or src.get("error.stack_trace")
        or src.get("message")
        or _get_nested(src, "log", "original")
        or ""
    )
    if isinstance(msg, (dict, list)):
        msg = json.dumps(msg, ensure_ascii=False)
    ts = src.get("@timestamp") or ""
    level = _get_nested(src, "log", "level") or src.get("log.level") or ""
    service = _get_nested(src, "service", "name") or src.get("service.name") or ""
    prefix = " ".join([p for p in [ts, service, level] if p])
    text = str(msg or "")
    return f"{prefix}\n{text}".strip() if prefix else text.strip()


def _normalize_for_key(text):
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<uuid>", s, flags=re.IGNORECASE)
    s = re.sub(r"\b0x[0-9a-f]+\b", "<hex>", s, flags=re.IGNORECASE)
    s = re.sub(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b", "<ts>", s)
    s = re.sub(r"[A-Za-z]:\\\\[^\s\"']+", "<path>", s)
    s = re.sub(r"(/[^ \n\t\"']+)+", "<path>", s)
    s = re.sub(r"\b\d{3,}\b", "<num>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_exception_message(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for ln in reversed(lines[-20:]):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\s*:\s*(.*)$", ln)
        if m:
            return m.group(1), (m.group(2) or "").strip()
    return "", ""


def _extract_java_exception_message(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for ln in reversed(lines[-60:]):
        m = re.search(r"Caused by:\s*([A-Za-z0-9_.$]+)(?::\s*(.*))?$", ln)
        if m:
            ex = (m.group(1) or "").strip()
            msg = (m.group(2) or "").strip()
            return ex.split(".")[-1], msg
        m = re.match(r"^([A-Za-z0-9_.$]+(?:Exception|Error))(?::\s*(.*))?$", ln)
        if m:
            ex = (m.group(1) or "").strip()
            msg = (m.group(2) or "").strip()
            return ex.split(".")[-1], msg
        m = re.match(r"^Exception in thread\s+\"[^\"]+\"\s+([A-Za-z0-9_.$]+)(?::\s*(.*))?$", ln)
        if m:
            ex = (m.group(1) or "").strip()
            msg = (m.group(2) or "").strip()
            return ex.split(".")[-1], msg
    return "", ""


def _extract_java_frames(text, limit=8):
    frames = []
    pattern = re.compile(r"^\s*at\s+([A-Za-z0-9_.$]+)\(([^():]+)(?::(\d+))?\)\s*$", flags=re.MULTILINE)
    for m in pattern.finditer(text or ""):
        func = (m.group(1) or "").strip()
        file_name = (m.group(2) or "").strip()
        if not file_name or file_name.lower() == "unknown source":
            file_name = ""
        frames.append({"file": file_name, "function": func})
        if len(frames) >= int(limit):
            break
    return frames


def _detect_markers(text):
    s = text or ""
    python_tb = "Traceback (most recent call last):" in s
    python_frame = bool(re.search(r'File\s+"[^"]+",\s+line\s+\d+,\s+in\s+\w+', s))
    java_caused_by = "Caused by:" in s or "Exception in thread" in s
    java_frame = bool(re.search(r"^\s*at\s+[A-Za-z0-9_.$]+\([^()]+\)", s, flags=re.MULTILINE))
    return {
        "python_tb": python_tb,
        "python_frame": python_frame,
        "java_caused_by": java_caused_by,
        "java_frame": java_frame,
    }


def _select_relevant_excerpt(text, project_lang, context_lines_before=0, max_chars=20000):
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines(True)
    if not lines:
        return ""
    context_lines_before = max(int(context_lines_before or 0), 0)

    def slice_from_index(i):
        start = max(0, i - context_lines_before)
        return "".join(lines[start:])[: int(max_chars)]

    joined = "".join(lines)
    markers = _detect_markers(joined)
    lang = (project_lang or "auto").strip().lower()
    if lang == "auto":
        if markers["python_tb"] or markers["python_frame"]:
            lang = "python"
        elif markers["java_caused_by"] or markers["java_frame"]:
            lang = "java"

    if lang == "python":
        for i in range(len(lines) - 1, -1, -1):
            if "Traceback (most recent call last):" in lines[i]:
                return slice_from_index(i)
        for i in range(len(lines) - 1, -1, -1):
            if re.search(r'File\s+"[^"]+",\s+line\s+\d+,\s+in\s+\w+', lines[i]):
                return slice_from_index(i)
    if lang == "java":
        for i in range(len(lines) - 1, -1, -1):
            if "Caused by:" in lines[i] or "Exception in thread" in lines[i]:
                return slice_from_index(i)
        for i in range(len(lines) - 1, -1, -1):
            if re.match(r"^\s*at\s+[A-Za-z0-9_.$]+\([^()]+\)", lines[i]):
                return slice_from_index(i)

    for i in range(len(lines) - 1, -1, -1):
        if re.match(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\s*:", lines[i].strip()):
            return slice_from_index(i)

    tail = "".join(lines[-200:])[: int(max_chars)]
    return tail


def _extract_frames(text, limit=8):
    frames = []
    pattern = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+([A-Za-z_][A-Za-z0-9_]*)')
    for m in pattern.finditer(text or ""):
        file_path = m.group(1) or ""
        func = m.group(3) or ""
        file_name = os.path.basename(file_path.replace("\\", "/"))
        if not file_name:
            continue
        frames.append({"file": file_name, "function": func})
        if len(frames) >= int(limit):
            break
    return frames


def _fingerprint(exception_type, message_key, frames):
    basis = "\n".join(
        [
            (exception_type or "").strip().lower(),
            (message_key or "").strip(),
            " ".join(f"{f.get('file')}:{f.get('function')}" for f in (frames or []) if f.get("file")),
        ]
    ).strip()
    if not basis:
        return ""
    return hashlib.sha256(basis.encode("utf-8", errors="ignore")).hexdigest()


def _fallback_fingerprint(text):
    norm = _normalize_for_key(text)[:500]
    if not norm:
        return ""
    return hashlib.sha256(norm.encode("utf-8", errors="ignore")).hexdigest()


def _should_report(filter_level, exception_type, frames, markers):
    level = (filter_level or "balanced").strip().lower()
    has_marker = bool(markers.get("python_tb") or markers.get("python_frame") or markers.get("java_caused_by") or markers.get("java_frame"))
    has_frames = bool(frames)
    has_ex = bool((exception_type or "").strip())
    if level == "lenient":
        return True
    if level == "strict":
        return has_marker or has_frames
    return has_marker or has_frames or has_ex


def run_agent(args):
    server_base = (args.server_url or config.AGENT_SERVER_URL).rstrip("/")
    endpoint = f"{server_base}/v1/tasks"
    last_seen = {}
    source = (args.source or "file").strip().lower()
    repo_url = (args.repo_url or "").strip()
    if not repo_url:
        raise ValueError("repo_url is required (set AGENT_REPO_URL or pass --repo-url)")

    def on_error(full_error):
        excerpt = _select_relevant_excerpt(
            full_error,
            project_lang=args.project_lang,
            context_lines_before=args.context_lines_before,
            max_chars=args.max_raw_excerpt,
        )
        markers = _detect_markers(excerpt)
        lang = (args.project_lang or "auto").strip().lower()
        if lang == "auto":
            if markers["python_tb"] or markers["python_frame"]:
                lang = "python"
            elif markers["java_caused_by"] or markers["java_frame"]:
                lang = "java"

        exception_type = ""
        message = ""
        frames = []
        if lang == "java":
            exception_type, message = _extract_java_exception_message(excerpt)
            frames = _extract_java_frames(excerpt, limit=args.max_frames)
        else:
            exception_type, message = _extract_exception_message(excerpt)
            frames = _extract_frames(excerpt, limit=args.max_frames)

        if not _should_report(args.filter_level, exception_type, frames, markers):
            print("[agent] dropped log chunk: no exception evidence")
            return

        message_key = _normalize_for_key(message)[:160] if message else ""
        fp = _fingerprint(exception_type, message_key, frames) or _fallback_fingerprint(excerpt)
        if fp:
            now = time.time()
            last_ts = last_seen.get(fp, 0.0)
            if (now - last_ts) < args.dedup_window_seconds:
                return
            last_seen[fp] = now

        code_host = (args.code_host or "gitlab").strip().lower()
        payload = {
            "repo_url": repo_url,
            "code_host": code_host,
            "error_content": (excerpt or "")[: int(args.max_raw_excerpt)],
            "schema_version": "1.0",
            "event_id": str(uuid.uuid4()),
            "occurred_at": int(time.time()),
            "repo": {
                "repo_url": repo_url,
                "code_host": code_host,
                "default_branch": args.default_branch,
            },
            "service": {
                "name": args.service_name,
                "environment": args.environment,
            },
            "error": {
                "exception_type": exception_type,
                "message_key": message_key,
                "fingerprint": fp,
                "frames": frames,
                "raw_excerpt": (excerpt or "")[: int(args.max_raw_excerpt)],
            },
        }
        resp = _post_json(endpoint, payload, api_key=args.api_key, timeout=args.http_timeout_seconds)
        task_id = resp.get("task_id")
        print(f"[agent] reported error, task_id={task_id}")

    print(f"[agent] repo_url: {repo_url}")
    print(f"[agent] server: {server_base}")
    print(f"[agent] source={source}")
    if source == "elk":
        search_after = None
        while True:
            hits = _elk_search(
                elk_url=args.elk_url,
                index=args.elk_index,
                query=args.elk_query,
                size=args.elk_batch_size,
                since_seconds=args.elk_since_seconds,
                search_after=search_after,
                timeout=args.http_timeout_seconds,
            )
            for h in hits:
                search_after = h.get("sort") or search_after
                text = _elk_hit_to_error_text(h)
                if text:
                    on_error(text)
            time.sleep(max(float(args.elk_poll_seconds), 0.2))
    else:
        if not args.log_path:
            raise ValueError("--log-path is required when --source=file")
        log_path = os.path.abspath(args.log_path)
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        if not os.path.exists(log_path):
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"--- agent started at {time.ctime()} ---\n")

        observer = start_monitoring(log_path, on_error)
        try:
            print(f"[agent] watching: {log_path}")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default=os.getenv("AGENT_SOURCE", "file"), choices=["file", "elk"])
    p.add_argument("--log-path", default=os.getenv("LOG_FILE_PATH"))
    p.add_argument("--repo-url", default=os.getenv("AGENT_REPO_URL", getattr(config, "AGENT_REPO_URL", None)))
    p.add_argument("--server-url", default=None)
    p.add_argument("--code-host", default="gitlab")
    p.add_argument("--default-branch", default="main")
    p.add_argument("--service-name", default=os.getenv("SERVICE_NAME", "app"))
    p.add_argument("--environment", default=os.getenv("ENVIRONMENT", "dev"))
    p.add_argument("--project-lang", default="auto", choices=["auto", "python", "java"])
    p.add_argument("--filter-level", default="balanced", choices=["strict", "balanced", "lenient"])
    p.add_argument("--context-lines-before", type=int, default=20)
    p.add_argument("--max-raw-excerpt", type=int, default=20000)
    p.add_argument("--max-frames", type=int, default=8)
    p.add_argument("--api-key", default=os.getenv("AGENT_API_KEY"))
    p.add_argument("--dedup-window-seconds", type=int, default=3600)
    p.add_argument("--http-timeout-seconds", type=int, default=15)
    p.add_argument("--elk-url", default=os.getenv("ELK_URL", getattr(config, "ELK_URL", "http://127.0.0.1:9200")))
    p.add_argument("--elk-index", default=os.getenv("ELK_INDEX", getattr(config, "ELK_INDEX", "filebeat-*")))
    p.add_argument("--elk-query", default=os.getenv("ELK_QUERY", getattr(config, "ELK_QUERY", "log.level:ERROR")))
    p.add_argument("--elk-poll-seconds", type=float, default=float(os.getenv("ELK_POLL_SECONDS", getattr(config, "ELK_POLL_SECONDS", 2))))
    p.add_argument("--elk-since-seconds", type=int, default=int(os.getenv("ELK_SINCE_SECONDS", getattr(config, "ELK_SINCE_SECONDS", 300))))
    p.add_argument("--elk-batch-size", type=int, default=int(os.getenv("ELK_BATCH_SIZE", getattr(config, "ELK_BATCH_SIZE", 50))))
    return p.parse_args()


if __name__ == "__main__":
    run_agent(parse_args())
