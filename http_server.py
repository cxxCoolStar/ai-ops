import json
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
from claude_interface import ClaudeInterface
from email_service import EmailSender
from gitlab_service import GitLabService
from github_service import GitHubService
from main import AutoRepairOrchestrator, _build_error_signature
from trace_store import TraceStore
from workspace_manager import WorkspaceManager


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
            self.tasks[task_id] = {"task_id": task_id, "status": "QUEUED", "created_at": int(time.time())}
        self.queue.put({"task_id": task_id, "repo_url": repo_url, "error_content": error_content, "code_host": code_host})
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
            error_signature=_build_error_signature(error_content),
            error_excerpt=(error_content or "")[:2000],
        )

        ws_root = self.workspace.allocate()
        repo_dir = f"{ws_root}\\repo"
        try:
            self.workspace.clone_into(repo_url, repo_dir)
            if code_host == "gitlab":
                platform = GitLabService(cwd=repo_dir)
            elif code_host == "github":
                platform = GitHubService(cwd=repo_dir)
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
            self.workspace.release(ws_root)


class ApiHandler(BaseHTTPRequestHandler):
    runner = None

    def do_POST(self):
        if self.path != "/v1/tasks":
            self._send_json(404, {"error": "not_found"})
            return
        body = self._read_json()
        repo_url = (body.get("repo_url") or "").strip()
        error_content = body.get("error_content") or ""
        code_host = body.get("code_host")
        if not repo_url:
            self._send_json(400, {"error": "repo_url_required"})
            return
        if not str(error_content).strip():
            self._send_json(400, {"error": "error_content_required"})
            return
        task_id = self.runner.submit(repo_url, str(error_content), code_host=code_host)
        self._send_json(200, {"task_id": task_id})

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

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

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
