import time
import os
import queue
import hashlib
import subprocess
import config
from log_monitor import start_monitoring
from claude_interface import ClaudeInterface
from email_service import EmailSender
from github_service import GitHubService

def _require_non_empty(name, value):
    if value is None:
        raise ValueError(f"{name} is required.")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{name} is required.")
    return value

class AutoRepairOrchestrator:
    def __init__(self, claude, email, github):
        self.claude = claude
        self.email = email
        self.github = github

    def handle_error(self, error_content):
        print("\n[!] 检测到错误，开始代理式自动修复流程...")

        _require_non_empty("SMTP_USER", config.SMTP_USER)
        _require_non_empty("SMTP_PASSWORD", config.SMTP_PASSWORD)
        _require_non_empty("RECEIVER_EMAIL", config.RECEIVER_EMAIL)
        _require_non_empty("GITHUB_TOKEN", config.GITHUB_TOKEN)
        _require_non_empty("GITHUB_REPO", config.GITHUB_REPO)
        _require_non_empty("CLAUDE_COMMAND", config.CLAUDE_COMMAND)

        print("正在准备 GitHub 修复分支...")
        branch_name = self.github.create_fix_branch("agentic-fix")

        print("正在向 Claude 请求结构化修复方案（code_block 输出）...")
        blocks = self.claude.propose_fix_code_blocks(error_content)

        print("正在应用 Claude 提供的文件变更...")
        self._apply_code_blocks(blocks)

        print("正在运行提交前检查...")
        self._run_preflight_checks()

        print("正在生成 PR 报告总结 (原因、过程、结论)...")
        analysis = self.claude.get_structured_summary(error_content)

        print("正在提交修复代码并创建 PR...")
        commit_msg = f"fix(ai): agentic auto-repair for detected error\n\nLog: {error_content[:100]}..."
        self.github.commit_and_push(branch_name, commit_msg)

        pr_title = "🛠️ [AI Agentic Fix] 修复系统路径错误"
        pr_body = f"""# 🤖 AI 代理式自动修复报告

## 🔍 诊断与修复过程
{analysis}

---
- **检测时间**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`
- **修复方式**: Claude Code 代理自动化修改
- **分支**: `{branch_name}`

*由 [AI-Ops] 系统自动生成并提交。*
"""
        pr_url = self.github.create_pull_request(branch_name, pr_title, pr_body)
        print(f"PR 已创建: {pr_url}")

        print("正在发送 HTML 修复报告邮件...")
        subject = "🛠️ AI 自动修复完成：PR 已提交"
        html_content = self._build_email_html(error_content, analysis, pr_url)
        self.email.send_email(subject, html_content, is_html=True)

        self.github.clean_up("main")
        print("本次代理修复流程圆满完成。")
        return pr_url

    def _run_preflight_checks(self):
        subprocess.run(
            ["python", "-m", "compileall", "."],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True
        )

    def _apply_code_blocks(self, blocks):
        repo_root = os.path.abspath(os.getcwd())
        for rel_path, content in blocks:
            abs_path = self._safe_abs_path(repo_root, rel_path)
            if not os.path.exists(abs_path):
                raise ValueError(f"Claude 返回了不存在的文件路径: {rel_path}")
            with open(abs_path, "w", encoding="utf-8", newline="") as f:
                f.write(content)

    def _safe_abs_path(self, repo_root, rel_path):
        if os.path.isabs(rel_path):
            raise ValueError(f"不允许绝对路径: {rel_path}")
        normalized = os.path.normpath(rel_path).lstrip("\\/ ")
        abs_path = os.path.abspath(os.path.join(repo_root, normalized))
        if not abs_path.startswith(repo_root + os.sep):
            raise ValueError(f"不允许越界路径: {rel_path}")
        return abs_path

    def _build_email_html(self, error_content, analysis, pr_url):
        return f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial; line-height: 1.6; color: #333; background-color: #f9f9f9; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); border: 1px solid #eee;">
                <div style="background: #24292e; color: white; padding: 25px; text-align: center;">
                    <h2 style="margin: 0;">AI-Ops 自动化运维</h2>
                </div>
                <div style="padding: 30px;">
                    <div style="border-left: 4px solid #f97583; background: #fff5f5; padding: 15px; margin-bottom: 25px;">
                        <strong style="color: #d73a49;">检测到报错：</strong><br>
                        <code style="font-size: 13px;">{error_content[:100]}...</code>
                    </div>
                    
                    <p style="font-size: 16px;">AI 代理（Claude Code）已自动定位并修复了代码逻辑。点击下方按钮查看变更详情：</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{pr_url}" style="background: #2ea44f; color: white; padding: 12px 25px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">进入 GitHub 查看 PR</a>
                    </div>
                    
                    <div style="background: #f6f8fa; padding: 15px; border-radius: 6px; font-size: 14px; color: #555;">
                        <strong>修复总结：</strong><br>
                        {analysis[:300].replace('\n', '<br>')}...
                    </div>
                </div>
                <div style="background: #eee; padding: 15px; text-align: center; font-size: 11px; color: #999;">
                    本项目由 AI-Ops 自动维护
                </div>
            </div>
        </body>
        </html>
        """

def _build_error_signature(error_content):
    content = (error_content or "").strip()
    if not content:
        return ""
    normalized = "\n".join(line.strip() for line in content.splitlines() if line.strip())
    normalized = normalized[-8000:]
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()

def main():
    print("AI Ops 错误报告系统 (Agentic GitOps 版) 启动中...")
    
    # 初始化组件
    claude = ClaudeInterface()
    email = EmailSender()
    github = GitHubService()
    orchestrator = AutoRepairOrchestrator(claude=claude, email=email, github=github)
    
    # 确保日志文件存在
    log_path = os.path.abspath(config.LOG_FILE_PATH)
    if not os.path.exists(log_path):
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"--- 系统启动于 {time.ctime()} ---\n")

    error_queue = queue.Queue(maxsize=config.MAX_ERROR_QUEUE_SIZE)

    def process_error(error_content):
        error_queue.put(error_content)

    # 启动监控
    observer = start_monitoring(log_path, process_error)

    last_seen = {}
    dedup_window_seconds = config.DEDUP_WINDOW_SECONDS

    try:
        print(f"正在监控: {log_path}")
        print("按 Ctrl+C 停止运行。")
        while True:
            error_content = error_queue.get()
            signature = _build_error_signature(error_content)
            if signature:
                now = time.time()
                last_ts = last_seen.get(signature, 0.0)
                if (now - last_ts) < dedup_window_seconds:
                    continue
                last_seen[signature] = now
            orchestrator.handle_error(error_content)
    except KeyboardInterrupt:
        print("\n正在停止系统...")
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
