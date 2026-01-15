import hashlib
import os
import subprocess
import time

from ai_ops import config
from ai_ops.trace.trace_store import StepScope


def require_non_empty(name, value):
    if value is None:
        raise ValueError(f"{name} is required.")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{name} is required.")
    return value


def build_error_signature(error_content):
    content = (error_content or "").strip()
    if not content:
        return ""
    normalized = "\n".join(line.strip() for line in content.splitlines() if line.strip())
    normalized = normalized[-8000:]
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()


class AutoRepairOrchestrator:
    def __init__(self, claude, email, code_host, repo_root=None, trace_store=None, code_host_name=None):
        self.claude = claude
        self.email = email
        self.code_host = code_host
        self.repo_root = os.path.abspath(repo_root or os.getcwd())
        self.trace_store = trace_store
        self.code_host_name = (code_host_name or config.CODE_HOST or "").strip().lower()

    def handle_error(self, error_content, repo_url=None, trace_id=None):
        print("\n[!] 检测到错误，开始代理式自动修复流程...")

        if getattr(config, "EMAIL_ENABLED", True):
            require_non_empty("SMTP_USER", config.SMTP_USER)
            require_non_empty("SMTP_PASSWORD", config.SMTP_PASSWORD)
            require_non_empty("RECEIVER_EMAIL", config.RECEIVER_EMAIL)
        require_non_empty("CLAUDE_COMMAND", config.CLAUDE_COMMAND)

        if self.code_host_name == "gitlab":
            require_non_empty("GITLAB_TOKEN", config.GITLAB_TOKEN)
            require_non_empty("GITLAB_PROJECT", config.GITLAB_PROJECT)
            require_non_empty("GITLAB_BASE_URL", config.GITLAB_BASE_URL)
        elif self.code_host_name == "github":
            require_non_empty("GITHUB_TOKEN", config.GITHUB_TOKEN)
        else:
            raise ValueError(f"Unsupported CODE_HOST: {self.code_host_name}")

        signature = build_error_signature(error_content)
        if self.trace_store:
            if not trace_id:
                trace_id = self.trace_store.new_trace_id()
                self.trace_store.create_trace(
                    trace_id=trace_id,
                    repo_url=repo_url or "",
                    code_host=self.code_host_name,
                    error_signature=signature,
                    error_excerpt=(error_content or "")[:2000],
                )

        print("正在准备修复分支...")
        with self._step(trace_id, "CREATE_FIX_BRANCH"):
            branch_name = self.code_host.create_fix_branch("agentic-fix")

        claude_mode = (getattr(config, "CLAUDE_FIX_MODE", "code_blocks") or "code_blocks").strip().lower()
        if claude_mode == "agentic":
            print("正在调用 Claude 直接修改仓库代码（agentic 模式）...")
            with self._step(trace_id, "AI_AGENTIC_EDIT"):
                self.claude.execute_agentic_fix(error_content, cwd=self.repo_root)
        else:
            print("正在向 Claude 请求结构化修复方案（code_block 输出）...")
            with self._step(trace_id, "AI_PROPOSE_PATCH"):
                blocks = self.claude.propose_fix_code_blocks(error_content)

            print("正在应用 Claude 提供的文件变更...")
            with self._step(trace_id, "APPLY_PATCH"):
                self._apply_code_blocks(blocks)

        print("正在运行提交前检查...")
        with self._step(trace_id, "PREFLIGHT_CHECK"):
            self._run_preflight_checks()

        print("正在生成 PR 报告总结 (原因、过程、结论)...")
        with self._step(trace_id, "AI_SUMMARY"):
            analysis = self.claude.get_structured_summary(error_content)

        print("正在提交修复代码并创建 PR...")
        commit_msg = f"fix(ai): agentic auto-repair for detected error\n\nLog: {error_content[:100]}..."
        commit_sha = ""
        with self._step(trace_id, "GIT_COMMIT_PUSH"):
            self.code_host.commit_and_push(branch_name, commit_msg)
            if hasattr(self.code_host, "git") and hasattr(self.code_host.git, "current_commit"):
                commit_sha = self.code_host.git.current_commit()

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
        with self._step(trace_id, "CREATE_PR"):
            pr_url = self.code_host.create_pull_request(branch_name, pr_title, pr_body)
            print(f"PR 已创建: {pr_url}")

        print("正在发送 HTML 修复报告邮件...")
        subject = "🛠️ AI 自动修复完成：PR 已提交"
        html_content = self._build_email_html(error_content, analysis, pr_url)
        with self._step(trace_id, "NOTIFY"):
            if getattr(config, "EMAIL_ENABLED", True):
                self.email.send_email(subject, html_content, is_html=True)

        with self._step(trace_id, "CLEANUP"):
            self.code_host.clean_up("main")
        print("本次代理修复流程圆满完成。")

        if self.trace_store:
            self.trace_store.finish_trace_ok(trace_id, pr_url, commit_sha)
        return pr_url

    def _step(self, trace_id, step_name):
        if not self.trace_store or not trace_id:
            return _NullScope()
        return StepScope(self.trace_store, trace_id, step_name)

    def _run_preflight_checks(self):
        subprocess.run(
            ["python", "-m", "compileall", "."],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=self.repo_root,
            check=True,
        )

    def _apply_code_blocks(self, blocks):
        for rel_path, content in blocks:
            normalized_rel = self._normalize_rel_path(rel_path)
            candidate_rels = self._candidate_rel_paths(normalized_rel)
            abs_path = ""
            for candidate_rel in candidate_rels:
                abs_candidate = self._safe_abs_path(self.repo_root, candidate_rel)
                if os.path.exists(abs_candidate):
                    abs_path = abs_candidate
                    break
            if not abs_path:
                raise ValueError(f"Claude 返回了不存在的文件路径: {rel_path}")
            with open(abs_path, "w", encoding="utf-8", newline="") as f:
                f.write(content)

    def _normalize_rel_path(self, rel_path):
        s = (rel_path or "").strip().replace("\\", "/")
        while s.startswith("./"):
            s = s[2:]
        if "/repo/" in s:
            s = s.rsplit("/repo/", 1)[-1]
        if s.startswith("repo/"):
            s = s[len("repo/") :]
        return s

    def _candidate_rel_paths(self, rel_path):
        s = (rel_path or "").strip().replace("\\", "/").lstrip("/").strip()
        if not s:
            return []
        candidates = []
        cur = s
        while cur and cur not in candidates:
            candidates.append(cur)
            if "/" not in cur:
                break
            cur = cur.split("/", 1)[-1]
        return candidates

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


class _NullScope:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
