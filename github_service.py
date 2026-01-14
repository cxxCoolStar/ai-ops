import time
from github import Github
import config
from git_service import GitService

class GitHubService:
    def __init__(self, cwd=None):
        self.token = config.GITHUB_TOKEN
        self.repo_name = config.GITHUB_REPO
        self.gh = Github(self.token) if self.token else None
        self.git = GitService(cwd=cwd)

    def create_fix_branch(self, error_type):
        timestamp = int(time.time())
        branch_name = f"fix/{error_type.lower().replace(' ', '-')}-{timestamp}"

        self.git.checkout_new_branch(branch_name)
        return branch_name

    def commit_and_push(self, branch_name, commit_message):
        self.git.add_all()
        self.git.commit(commit_message)
        self.git.push("origin", branch_name)

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
        self.git.checkout(base_branch)

if __name__ == "__main__":
    pass
    # 简单测试
    # gs = GitHubService()
    # branch = gs.create_fix_branch("test-error")
    # print(f"Created branch: {branch}")
