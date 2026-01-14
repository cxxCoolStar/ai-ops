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
            cwd=os.getcwd()
        )
        if result.returncode != 0:
            print(f"Git 错误: {result.stderr}")
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
            return "Error: GitHub Token not configured."
        
        try:
            repo = self.gh.get_repo(self.repo_name)
            # 假设目标分支是 main，实际可以根据 git symbolic-ref 获取
            # 默认使用 main，因为现在大多数仓库默认都是 main
            base_branch = "main"
            try:
                # 尝试获取仓库的默认分支，这是最稳妥的办法
                repo_info = self.gh.get_repo(self.repo_name)
                base_branch = repo_info.default_branch
            except Exception as e:
                print(f"获取默认分支失败，尝试回退到 main: {e}")
                
            pr = repo.create_pull(
                title=title,
                body=body,
                head=branch_name,
                base=base_branch
            )
            return pr.html_url
        except Exception as e:
            return f"Error creating PR: {e}"

    def clean_up(self, base_branch="main"):
        # 切换回主分支并拉取最新代码（可选）
        self._run_git(["checkout", base_branch])

if __name__ == "__main__":
    pass
    # 简单测试
    # gs = GitHubService()
    # branch = gs.create_fix_branch("test-error")
    # print(f"Created branch: {branch}")
