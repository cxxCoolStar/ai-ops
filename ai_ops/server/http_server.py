import json
import hashlib
import hmac
import os
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

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


class TaskRunner:
    def __init__(self):
        self.tasks = {}
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        self.store = TraceStore(config.TRACE_DB_PATH)
        self.workspace = WorkspaceManager()
        self._start_workers()

    def submit(self, event):
        task_id = str(uuid.uuid4())
        with self.lock:
            self.tasks[task_id] = {
                "task_id": task_id,
                "status": "QUEUED",
                "created_at": int(time.time()),
            }
        self.queue.put(
            {
                "kind": "EVENT",
                "task_id": task_id,
                "event": event,
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
        event = job.get("event") or {}
        repo = event.get("repo") or {}
        err = event.get("error") or {}
        repo_url = (repo.get("repo_url") or "").strip()
        code_host = (repo.get("code_host") or config.CODE_HOST).strip().lower()
        raw_excerpt = err.get("raw_excerpt") or ""
        ex = (err.get("exception_type") or "").strip()
        msg = (err.get("message_key") or "").strip()
        if raw_excerpt:
            error_content = raw_excerpt
        else:
            error_content = (ex + "\n" + msg).strip()

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
            self.workspace.clone_into(repo_url, repo_dir)
            if code_host == "gitlab":
                platform = GitLabService(cwd=repo_dir)
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
            self.workspace.clone_into(repo_url, repo_dir)
            if code_host == "github":
                repo_name = _github_repo_from_url(repo_url) or config.GITHUB_REPO
                platform = GitHubService(cwd=repo_dir, repo_name=repo_name)
            elif code_host == "gitlab":
                platform = GitLabService(cwd=repo_dir)
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

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/v1/tasks":
            if not self._check_auth():
                self._send_json(401, {"error": "unauthorized"})
                return
            body = self._read_json()
            if not isinstance(body, dict):
                self._send_json(400, {"error": "invalid_json"})
                return
            schema_version = (body.get("schema_version") or "").strip()
            event_id = (body.get("event_id") or "").strip()
            occurred_at = body.get("occurred_at")
            repo = body.get("repo") or {}
            err = body.get("error") or {}
            repo_url = (repo.get("repo_url") or "").strip()
            code_host = (repo.get("code_host") or "").strip().lower()
            raw_excerpt = err.get("raw_excerpt") or ""
            ex = (err.get("exception_type") or "").strip()
            msg = (err.get("message_key") or "").strip()
            fp = (err.get("fingerprint") or "").strip()
            frames = err.get("frames")
            if schema_version != "1.0":
                self._send_json(400, {"error": "schema_version_required", "expected": "1.0"})
                return
            if not event_id:
                self._send_json(400, {"error": "event_id_required"})
                return
            if not isinstance(occurred_at, int):
                self._send_json(400, {"error": "occurred_at_required_int"})
                return
            if not repo_url:
                self._send_json(400, {"error": "repo_url_required"})
                return
            if not code_host:
                self._send_json(400, {"error": "code_host_required"})
                return
            if not (raw_excerpt or ex or msg):
                self._send_json(400, {"error": "error_required"})
                return
            if not fp:
                self._send_json(400, {"error": "fingerprint_required"})
                return
            if frames is not None and not isinstance(frames, list):
                self._send_json(400, {"error": "frames_must_be_list"})
                return
            task_id = self.runner.submit(body)
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

        if path != "/v1/tasks":
            self._send_json(404, {"error": "not_found"})
            return

    def do_GET(self):
        if self.path.startswith("/v1/tasks/"):
            task_id = self.path[len("/v1/tasks/") :].strip()
            task = self.runner.get(task_id)
            if not task:
                self._send_json(404, {"error": "not_found"})
                return
            self._send_json(200, task)
            return
        self._send_json(404, {"error": "not_found"})

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
