import argparse
import json
import os
import time
import urllib.request

from ai_ops import config
from ai_ops.core.orchestrator import build_error_signature
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


def run_agent(args):
    server_base = (args.server_url or config.AGENT_SERVER_URL).rstrip("/")
    endpoint = f"{server_base}/v1/tasks"
    last_seen = {}

    def on_error(full_error):
        signature = build_error_signature(full_error)
        if signature:
            now = time.time()
            last_ts = last_seen.get(signature, 0.0)
            if (now - last_ts) < args.dedup_window_seconds:
                return
            last_seen[signature] = now

        payload = {
            "repo_url": args.repo_url,
            "error_content": full_error,
            "code_host": args.code_host,
        }
        resp = _post_json(endpoint, payload, api_key=args.api_key, timeout=args.http_timeout_seconds)
        task_id = resp.get("task_id")
        print(f"[agent] reported error, task_id={task_id}")

    log_path = os.path.abspath(args.log_path)
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    if not os.path.exists(log_path):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"--- agent started at {time.ctime()} ---\n")

    observer = start_monitoring(log_path, on_error)
    try:
        print(f"[agent] watching: {log_path}")
        print(f"[agent] repo_url: {args.repo_url}")
        print(f"[agent] server: {server_base}")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--log-path", required=True)
    p.add_argument("--repo-url", required=True)
    p.add_argument("--server-url", default=None)
    p.add_argument("--code-host", default="gitlab")
    p.add_argument("--api-key", default=os.getenv("AGENT_API_KEY"))
    p.add_argument("--dedup-window-seconds", type=int, default=3600)
    p.add_argument("--http-timeout-seconds", type=int, default=15)
    return p.parse_args()


if __name__ == "__main__":
    run_agent(parse_args())

