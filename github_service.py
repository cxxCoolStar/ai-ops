import os
import subprocess
import time
from github import Github
import config

class GitHubService:
    def __init__(self):
        self.token = config.GITHUB_TOKEN
        self.repo_name = config.GITHUB_REPO
        self.gh = Github(self.token) if self.token else None

    def _run_git(self, args):
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            cwd=os.getcwd(),
            check=True
        )
        return result

    def create_fix_branch(self, error_type):
        timestamp = int(time.time())
        branch_name = f"fix/{error_type.lower().replace(' ', '-')}-{timestamp}"
        
        # 确保回到主分支或基础分支 (假设为 master 或 main)
        # 这里简单处理，直接从当前分支切新分支
        self._run_git(["checkout", "-b", branch_name])
        return branch_name

    def commit_and_push(self, branch_name, commit_message):
        self._run_git(["add", "."])
        self._run_git(["commit", "-m", commit_message])
        self._run_git(["push", "origin", branch_name])

    def create_pull_request(self, branch_name, title, body):
        if not self.gh:
            raise ValueError("GitHub Token not configured.")
        if not self.repo_name:
            raise ValueError("GitHub Repo not configured.")

        repo = self.gh.get_repo(self.repo_name)
        base_branch = repo.default_branch or "main"
        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=base_branch
        )
        return pr.html_url

    def clean_up(self, base_branch="main"):
        # 切换回主分支并拉取最新代码（可选）
        self._run_git(["checkout", base_branch])

if __name__ == "__main__":
    pass
    # 简单测试
    # gs = GitHubService()
    # branch = gs.create_fix_branch("test-error")
    # print(f"Created branch: {branch}")
