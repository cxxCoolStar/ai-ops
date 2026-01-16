import json
import hashlib
import hmac
import os
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ai_ops import config
from ai_ops.core.orchestrator import AutoRepairOrchestrator, build_error_signature
from ai_ops.integrations.claude_interface import ClaudeInterface
from ai_ops.integrations.email_service import EmailSender
from ai_ops.trace.trace_store import TraceStore
from ai_ops.vcs.github_service import GitHubService
from ai_ops.vcs.gitlab_service import GitLabService
from ai_ops.workspace.workspace_manager import WorkspaceManager


def _github_repo_from_url(repo_url):
    url = (repo_url or "").strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        parsed = urlparse(url)
        path = (parsed.path or "").strip("/")
        if path.endswith(".git"):
            path = path[: -len(".git")]
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
        return ""
    if url.startswith("git@") and ":" in url:
        path = url.split(":", 1)[-1].strip()
        if path.endswith(".git"):
            path = path[: -len(".git")]
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
    return ""

def _gitlab_project_from_url(repo_url):
    url = (repo_url or "").strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        parsed = urlparse(url)
        path = (parsed.path or "").strip("/")
        if path.endswith(".git"):
            path = path[: -len(".git")]
        return path
    if url.startswith("git@") and ":" in url:
        path = url.split(":", 1)[-1].strip()
        if path.endswith(".git"):
            path = path[: -len(".git")]
        return path.strip("/")
    return ""


class TaskRunner:
    def __init__(self):
        self.tasks = {}
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        self.store = TraceStore(config.TRACE_DB_PATH)
        self.workspace = WorkspaceManager()
        self._start_workers()

    def submit(self, repo_url, error_content, code_host=None):
        task_id = str(uuid.uuid4())
        with self.lock:
            self.tasks[task_id] = {
                "task_id": task_id,
                "status": "QUEUED",
                "created_at": int(time.time()),
            }
        self.queue.put(
            {
                "kind": "ERROR",
                "task_id": task_id,
                "repo_url": repo_url,
                "error_content": error_content,
                "code_host": code_host,
            }
        )
        return task_id

    def submit_pr_feedback(self, repo_url, pr_url, pr_number, comment, code_host=None):
        task_id = str(uuid.uuid4())
        with self.lock:
            self.tasks[task_id] = {
                "task_id": task_id,
                "status": "QUEUED",
                "created_at": int(time.time()),
                "mr_url": pr_url,
                "pr_number": pr_number,
            }
        self.queue.put(
            {
                "kind": "PR_COMMENT",
                "task_id": task_id,
                "repo_url": repo_url,
                "pr_url": pr_url,
                "pr_number": pr_number,
                "comment": comment,
                "code_host": code_host,
            }
        )
        return task_id

    def get(self, task_id):
        with self.lock:
            return self.tasks.get(task_id)

    def _start_workers(self):
        for _ in range(max(1, config.MAX_CONCURRENT_TASKS)):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()

    def _worker_loop(self):
        while True:
            job = self.queue.get()
            self._run_job(job)

    def _run_job(self, job):
        kind = (job.get("kind") or "ERROR").strip().upper()
        if kind == "PR_COMMENT":
            return self._run_pr_comment_job(job)
        task_id = job["task_id"]
        repo_url = job["repo_url"]
        error_content = job["error_content"]
        code_host = (job.get("code_host") or config.CODE_HOST).strip().lower()

        with self.lock:
            self.tasks[task_id]["status"] = "RUNNING"

        trace_id = self.store.new_trace_id()
        self.store.create_trace(
            trace_id=trace_id,
            repo_url=repo_url,
            code_host=code_host,
            error_signature=build_error_signature(error_content),
            error_excerpt=(error_content or "")[:2000],
        )

        ws_root = self.workspace.allocate(repo_url=repo_url, trace_id=trace_id)
        repo_dir = os.path.join(ws_root, "repo")
        with self.lock:
            self.tasks[task_id]["workspace_dir"] = ws_root

        try:
            self.workspace.clone_into(repo_url, repo_dir, code_host=code_host)
            if code_host == "gitlab":
                project = _gitlab_project_from_url(repo_url) or config.GITLAB_PROJECT
                platform = GitLabService(cwd=repo_dir, project=project)
            elif code_host == "github":
                repo_name = _github_repo_from_url(repo_url) or config.GITHUB_REPO
                platform = GitHubService(cwd=repo_dir, repo_name=repo_name)
            else:
                raise ValueError(f"Unsupported code_host: {code_host}")

            claude = ClaudeInterface()
            email = EmailSender()
            orchestrator = AutoRepairOrchestrator(
                claude=claude,
                email=email,
                code_host=platform,
                repo_root=repo_dir,
                trace_store=self.store,
                code_host_name=code_host,
            )
            mr_url = orchestrator.handle_error(error_content, repo_url=repo_url, trace_id=trace_id)

            with self.lock:
                self.tasks[task_id]["status"] = "DONE"
                self.tasks[task_id]["trace_id"] = trace_id
                self.tasks[task_id]["mr_url"] = mr_url
        except Exception as e:
            self.store.finish_trace_fail(trace_id, "RUN_JOB", str(e))
            with self.lock:
                self.tasks[task_id]["status"] = "FAILED"
                self.tasks[task_id]["trace_id"] = trace_id
                self.tasks[task_id]["error"] = str(e)
        finally:
            try:
                self.workspace.release(ws_root)
            except Exception:
                pass

    def _run_pr_comment_job(self, job):
        task_id = job["task_id"]
        repo_url = job["repo_url"]
        pr_url = (job.get("pr_url") or "").strip()
        pr_number = int(job["pr_number"])
        comment = job.get("comment") or ""
        code_host = (job.get("code_host") or config.CODE_HOST).strip().lower()

        with self.lock:
            self.tasks[task_id]["status"] = "RUNNING"

        trace_id = self.store.new_trace_id()
        self.store.create_trace(
            trace_id=trace_id,
            repo_url=repo_url,
            code_host=code_host,
            error_signature=build_error_signature(comment),
            error_excerpt=(comment or "")[:2000],
        )

        ws_root = self.workspace.allocate(repo_url=repo_url, trace_id=trace_id)
        repo_dir = os.path.join(ws_root, "repo")
        with self.lock:
            self.tasks[task_id]["workspace_dir"] = ws_root

        try:
            self.workspace.clone_into(repo_url, repo_dir, code_host=code_host)
            if code_host == "github":
                repo_name = _github_repo_from_url(repo_url) or config.GITHUB_REPO
                platform = GitHubService(cwd=repo_dir, repo_name=repo_name)
            elif code_host == "gitlab":
                project = _gitlab_project_from_url(repo_url) or config.GITLAB_PROJECT
                platform = GitLabService(cwd=repo_dir, project=project)
            else:
                raise ValueError(f"Unsupported code_host: {code_host}")

            claude = ClaudeInterface()
            email = EmailSender()
            orchestrator = AutoRepairOrchestrator(
                claude=claude,
                email=email,
                code_host=platform,
                repo_root=repo_dir,
                trace_store=self.store,
                code_host_name=code_host,
            )
            result = orchestrator.handle_pr_feedback(
                pr_url=pr_url,
                pr_number=pr_number,
                feedback=str(comment),
                repo_url=repo_url,
                trace_id=trace_id,
            )

            with self.lock:
                self.tasks[task_id]["status"] = "DONE"
                self.tasks[task_id]["trace_id"] = trace_id
                self.tasks[task_id]["mr_url"] = result.get("mr_url") or pr_url
                self.tasks[task_id]["commit_sha"] = result.get("commit_sha") or ""
                self.tasks[task_id]["branch"] = result.get("branch") or ""
        except Exception as e:
            self.store.finish_trace_fail(trace_id, "RUN_PR_COMMENT_JOB", str(e))
            with self.lock:
                self.tasks[task_id]["status"] = "FAILED"
                self.tasks[task_id]["trace_id"] = trace_id
                self.tasks[task_id]["error"] = str(e)
        finally:
            try:
                self.workspace.release(ws_root)
            except Exception:
                pass


class ApiHandler(BaseHTTPRequestHandler):
    runner = None

    def _get_int_param(self, qs, key, default, minimum=None, maximum=None):
        raw = (qs.get(key) or [None])[0]
        try:
            val = int(raw) if raw is not None and str(raw).strip() != "" else int(default)
        except Exception:
            val = int(default)
        if minimum is not None:
            val = max(int(minimum), val)
        if maximum is not None:
            val = min(int(maximum), val)
        return val

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/v1/tasks":
            if not self._check_auth():
                self._send_json(401, {"error": "unauthorized"})
                return
            body = self._read_json()
            repo = body.get("repo") or {}
            err = body.get("error") or {}
            repo_url = (body.get("repo_url") or repo.get("repo_url") or "").strip()
            error_content = body.get("error_content") or err.get("raw_excerpt") or ""
            code_host = body.get("code_host") or repo.get("code_host")
            if not repo_url:
                self._send_json(400, {"error": "repo_url_required"})
                return
            if not str(error_content).strip():
                self._send_json(400, {"error": "error_content_required"})
                return
            task_id = self.runner.submit(repo_url, str(error_content), code_host=code_host)
            self._send_json(200, {"task_id": task_id})
            return

        if path == "/v1/pr-comments":
            if not self._check_auth():
                self._send_json(401, {"error": "unauthorized"})
                return
            body = self._read_json()
            repo_url = (body.get("repo_url") or "").strip()
            pr_url = (body.get("pr_url") or "").strip()
            pr_number = body.get("pr_number")
            comment = body.get("comment") or ""
            code_host = body.get("code_host")
            if not repo_url:
                self._send_json(400, {"error": "repo_url_required"})
                return
            if not pr_url:
                self._send_json(400, {"error": "pr_url_required"})
                return
            if pr_number is None or str(pr_number).strip() == "":
                self._send_json(400, {"error": "pr_number_required"})
                return
            if not str(comment).strip():
                self._send_json(400, {"error": "comment_required"})
                return
            task_id = self.runner.submit_pr_feedback(
                repo_url=repo_url,
                pr_url=pr_url,
                pr_number=int(pr_number),
                comment=str(comment),
                code_host=code_host,
            )
            self._send_json(200, {"task_id": task_id})
            return

        if path == "/v1/webhooks/github":
            raw = self._read_body_bytes()
            if not self._check_github_webhook(raw):
                self._send_json(401, {"error": "unauthorized"})
                return
            body = json.loads((raw or b"{}").decode("utf-8") or "{}")
            event = (self.headers.get("X-GitHub-Event") or "").strip()
            extracted = self._extract_github_pr_comment(event, body)
            if not extracted:
                self._send_json(200, {"ok": True, "ignored": True})
                return
            repo_url, pr_url, pr_number, comment = extracted

            prefix = (config.PR_COMMENT_COMMAND_PREFIX or "").strip()
            feedback = (comment or "").strip()
            if prefix:
                if not feedback.startswith(prefix):
                    self._send_json(200, {"ok": True, "ignored": True})
                    return
                feedback = feedback[len(prefix) :].strip()
                if not feedback:
                    self._send_json(200, {"ok": True, "ignored": True})
                    return

            task_id = self.runner.submit_pr_feedback(
                repo_url=repo_url,
                pr_url=pr_url,
                pr_number=int(pr_number),
                comment=feedback,
                code_host="github",
            )
            self._send_json(200, {"ok": True, "task_id": task_id})
            return

        if path == "/v1/debug/retrieval":
            body = self._read_json()
            error_content = body.get("error_content") or ""
            if not error_content:
                self._send_json(400, {"error": "error_content_required"})
                return
            result = self.runner.store.debug_retrieval(error_content)
            self._send_json(200, result)
            return

        if path != "/v1/tasks":
            self._send_json(404, {"error": "not_found"})
            return

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        qs = parse_qs(url.query or "")

        if path.startswith("/v1/tasks/"):
            task_id = path[len("/v1/tasks/") :].strip()
            task = self.runner.get(task_id)
            if not task:
                self._send_json(404, {"error": "not_found"})
                return
            self._send_json(200, task)
            return

        if path == "/v1/bug-cases":
            limit = self._get_int_param(qs, "limit", 50, minimum=1, maximum=200)
            offset = self._get_int_param(qs, "offset", 0, minimum=0)
            repo_url = (qs.get("repo_url") or [""])[0]
            q = (qs.get("q") or [""])[0]
            fmt = (qs.get("format") or [""])[0].strip().lower()
            items, total = self.runner.store.query_bug_cases(repo_url=repo_url, q=q, limit=limit, offset=offset)
            if fmt == "array":
                self._send_json(200, items)
            else:
                self._send_json(200, {"items": items, "total": total, "limit": limit, "offset": offset})
            return

        if path.startswith("/v1/bug-cases/"):
            case_id = path[len("/v1/bug-cases/") :].strip()
            case = self.runner.store.get_bug_case(case_id)
            if not case:
                self._send_json(404, {"error": "not_found"})
                return
            case["revisions"] = self.runner.store.get_bug_case_revisions(case_id)
            self._send_json(200, case)
            return

        if path == "/v1/traces":
            limit = self._get_int_param(qs, "limit", 50, minimum=1, maximum=200)
            offset = self._get_int_param(qs, "offset", 0, minimum=0)
            repo_url = (qs.get("repo_url") or [""])[0]
            status = (qs.get("status") or [""])[0]
            fmt = (qs.get("format") or [""])[0].strip().lower()
            items, total = self.runner.store.query_traces(repo_url=repo_url, status=status, limit=limit, offset=offset)
            if fmt == "array":
                self._send_json(200, items)
            else:
                self._send_json(200, {"items": items, "total": total, "limit": limit, "offset": offset})
            return

        if path.startswith("/v1/traces/"):
            trace_id = path[len("/v1/traces/") :].strip()
            trace = self.runner.store.get_trace(trace_id)
            if not trace:
                self._send_json(404, {"error": "not_found"})
                return
            steps = self.runner.store.list_steps(trace_id)
            top_matches = self.runner.store.search_similar_cases(trace.get("repo_url") or "", trace.get("error_excerpt") or "", limit=1)
            self._send_json(200, {"trace": trace, "steps": steps, "top_match": (top_matches[0] if top_matches else None)})
            return

        # Static UI Serving
        ui_dir = os.path.join(os.path.dirname(__file__), "ui")
        if path == "/":
            path = "/index.html"

        file_path = os.path.join(ui_dir, path.lstrip("/"))
        if os.path.exists(file_path) and os.path.isfile(file_path):
            # Security: ensure file is inside ui_dir
            if os.path.abspath(file_path).startswith(os.path.abspath(ui_dir)):
                self._send_file(file_path)
                return

        # Fallback for SPA
        index_path = os.path.join(ui_dir, "index.html")
        if not path.startswith("/v1/") and os.path.exists(index_path):
            self._send_file(index_path)
            return

        self._send_json(404, {"error": "not_found"})

    def _send_file(self, file_path):
        content_type = "text/plain"
        if file_path.endswith(".html"):
            content_type = "text/html"
        elif file_path.endswith(".js"):
            content_type = "application/javascript"
        elif file_path.endswith(".css"):
            content_type = "text/css"
        elif file_path.endswith(".png"):
            content_type = "image/png"
        elif file_path.endswith(".svg"):
            content_type = "image/svg+xml"

        try:
            with open(file_path, "rb") as f:
                data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except Exception:
            self._send_json(500, {"error": "internal_server_error"})

    def _read_body_bytes(self):
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length) if length > 0 else b""

    def _read_json(self):
        raw = self._read_body_bytes() or b"{}"
        return json.loads(raw.decode("utf-8"))

    def _check_auth(self):
        expected = (config.SERVER_API_KEY or "").strip()
        if not expected:
            return True
        actual = (self.headers.get("X-API-Key") or "").strip()
        return actual == expected

    def _check_github_webhook(self, raw_body):
        secret = (config.GITHUB_WEBHOOK_SECRET or "").encode("utf-8")
        if not secret:
            return True
        sig = (self.headers.get("X-Hub-Signature-256") or "").strip()
        if not sig.startswith("sha256="):
            return False
        expected = hmac.new(secret, raw_body or b"", hashlib.sha256).hexdigest()
        actual = sig[len("sha256=") :]
        return hmac.compare_digest(expected, actual)

    def _extract_github_pr_comment(self, event, payload):
        repo = (payload.get("repository") or {})
        repo_url = (repo.get("clone_url") or "").strip()
        if not repo_url:
            return None

        if event == "issue_comment":
            issue = payload.get("issue") or {}
            if not issue.get("pull_request"):
                return None
            pr_number = issue.get("number")
            pr_url = (issue.get("html_url") or "").strip()
            comment = ((payload.get("comment") or {}).get("body") or "").strip()
            if not pr_url or pr_number is None or not comment:
                return None
            return repo_url, pr_url, pr_number, comment

        if event == "pull_request_review_comment":
            pr = payload.get("pull_request") or {}
            pr_number = pr.get("number")
            pr_url = (pr.get("html_url") or "").strip()
            comment = ((payload.get("comment") or {}).get("body") or "").strip()
            if not pr_url or pr_number is None or not comment:
                return None
            return repo_url, pr_url, pr_number, comment

        if event == "pull_request_review":
            pr = payload.get("pull_request") or {}
            pr_number = pr.get("number")
            pr_url = (pr.get("html_url") or "").strip()
            review = payload.get("review") or {}
            comment = (review.get("body") or "").strip()
            if not pr_url or pr_number is None or not comment:
                return None
            return repo_url, pr_url, pr_number, comment

        return None

    def _send_json(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        return


def serve():
    runner = TaskRunner()
    ApiHandler.runner = runner
    server = ThreadingHTTPServer((config.HTTP_HOST, config.HTTP_PORT), ApiHandler)
    server.serve_forever()


if __name__ == "__main__":
    serve()
