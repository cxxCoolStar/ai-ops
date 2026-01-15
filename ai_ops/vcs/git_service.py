import os
import subprocess
import tempfile
import uuid


class GitService:
    def __init__(self, cwd=None):
        self.cwd = os.path.abspath(cwd or os.getcwd())

    @staticmethod
    def _git_prefix(disable_proxy=False):
        if not disable_proxy:
            return ["git"]
        return ["git", "-c", "http.proxy=", "-c", "https.proxy="]

    def run(self, args, env=None, disable_proxy=False):
        merged_env = None
        if env:
            merged_env = os.environ.copy()
            merged_env.update(env)
        return subprocess.run(
            self._git_prefix(disable_proxy=disable_proxy) + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=self.cwd,
            env=merged_env,
            check=True,
        )

    @staticmethod
    def _build_askpass_env(token):
        askpass_path = os.path.join(tempfile.gettempdir(), f"ai_ops_askpass_{uuid.uuid4().hex}.cmd")
        with open(askpass_path, "w", encoding="utf-8", newline="") as f:
            f.write("@echo off\r\n")
            f.write("echo %GIT_ASKPASS_TOKEN%\r\n")
        env = {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": askpass_path,
            "GIT_ASKPASS_TOKEN": token or "",
        }
        return env, askpass_path

    @staticmethod
    def _proxyless_env():
        return {
            "http_proxy": "",
            "https_proxy": "",
            "all_proxy": "",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
        }

    @staticmethod
    def clone(repo_url, dest_dir, env=None, disable_proxy=False):
        dest_dir = os.path.abspath(dest_dir)
        os.makedirs(os.path.dirname(dest_dir) or ".", exist_ok=True)
        merged_env = None
        if env:
            merged_env = os.environ.copy()
            merged_env.update(env)
        return subprocess.run(
            GitService._git_prefix(disable_proxy=disable_proxy) + ["clone", repo_url, dest_dir],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=os.getcwd(),
            env=merged_env,
            check=True,
        )

    def checkout_new_branch(self, branch_name):
        self.run(["checkout", "-b", branch_name])

    def checkout(self, branch_name):
        self.run(["checkout", branch_name])

    def add_all(self):
        self.run(["add", "."])

    def commit(self, message):
        self.run(["commit", "-m", message])

    def push(self, remote, branch_name, env=None, disable_proxy=False):
        self.run(["push", remote, branch_name], env=env, disable_proxy=disable_proxy)

    def push_with_token(self, remote, branch_name, token, extra_env=None, disable_proxy=False):
        env, askpass_path = self._build_askpass_env(token)
        if extra_env:
            env.update(extra_env)
        try:
            self.run(["push", remote, branch_name], env=env, disable_proxy=disable_proxy)
        finally:
            try:
                os.remove(askpass_path)
            except OSError:
                pass

    def set_remote_url(self, remote, url):
        self.run(["remote", "set-url", remote, url])

    def current_commit(self):
        result = self.run(["rev-parse", "HEAD"])
        return (result.stdout or "").strip()
