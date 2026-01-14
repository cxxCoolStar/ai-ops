import os
import queue
import time

from ai_ops import config
from ai_ops.core.orchestrator import AutoRepairOrchestrator, build_error_signature
from ai_ops.integrations.claude_interface import ClaudeInterface
from ai_ops.integrations.email_service import EmailSender
from ai_ops.monitoring.log_monitor import start_monitoring
from ai_ops.trace.trace_store import TraceStore
from ai_ops.vcs.github_service import GitHubService
from ai_ops.vcs.gitlab_service import GitLabService


def main():
    print("AI Ops 错误报告系统 (Agentic GitOps 版) 启动中...")

    claude = ClaudeInterface()
    email = EmailSender()
    if config.CODE_HOST == "gitlab":
        code_host = GitLabService(cwd=os.getcwd())
    elif config.CODE_HOST == "github":
        code_host = GitHubService(cwd=os.getcwd())
    else:
        raise ValueError(f"Unsupported CODE_HOST: {config.CODE_HOST}")

    trace_store = TraceStore(config.TRACE_DB_PATH)
    orchestrator = AutoRepairOrchestrator(
        claude=claude,
        email=email,
        code_host=code_host,
        repo_root=os.getcwd(),
        trace_store=trace_store,
        code_host_name=config.CODE_HOST,
    )

    log_path = os.path.abspath(config.LOG_FILE_PATH)
    if not os.path.exists(log_path):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"--- 系统启动于 {time.ctime()} ---\n")

    error_queue = queue.Queue(maxsize=config.MAX_ERROR_QUEUE_SIZE)

    def process_error(error_content):
        error_queue.put(error_content)

    observer = start_monitoring(log_path, process_error)

    last_seen = {}
    dedup_window_seconds = config.DEDUP_WINDOW_SECONDS

    try:
        print(f"正在监控: {log_path}")
        print("按 Ctrl+C 停止运行。")
        while True:
            error_content = error_queue.get()
            signature = build_error_signature(error_content)
            if signature:
                now = time.time()
                last_ts = last_seen.get(signature, 0.0)
                if (now - last_ts) < dedup_window_seconds:
                    continue
                last_seen[signature] = now
            orchestrator.handle_error(error_content, repo_url="")
    except KeyboardInterrupt:
        print("\n正在停止系统...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()

