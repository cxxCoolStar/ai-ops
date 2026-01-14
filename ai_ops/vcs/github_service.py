import time

from github import Github

from ai_ops import config
from ai_ops.vcs.git_service import GitService


class GitHubService:
    def __init__(self, cwd=None, repo_name=None, token=None):
        self.token = token if token is not None else config.GITHUB_TOKEN
        self.repo_name = repo_name if repo_name is not None else config.GITHUB_REPO
        self.gh = Github(self.token) if self.token else None
        self.git = GitService(cwd=cwd)

    def _maybe_configure_https_auth(self):
        if not self.token:
            return
        if not self.repo_name:
            return
        url = f"https://x-access-token:{self.token}@github.com/{self.repo_name}.git"
        self.git.set_remote_url("origin", url)

    def create_fix_branch(self, error_type):
        timestamp = int(time.time())
        branch_name = f"fix/{error_type.lower().replace(' ', '-')}-{timestamp}"

        self.git.checkout_new_branch(branch_name)
        return branch_name

    def commit_and_push(self, branch_name, commit_message):
        self._maybe_configure_https_auth()
        self.git.add_all()
        self.git.commit(commit_message)
        self.git.push("origin", branch_name)

    def fetch_pr_branch(self, pr_number):
        if not self.gh:
            raise ValueError("GitHub Token not configured.")
        if not self.repo_name:
            raise ValueError("GitHub Repo not configured.")
        pr = self.gh.get_repo(self.repo_name).get_pull(pr_number)
        branch = pr.head.ref
        if not branch:
            raise ValueError("GitHub PR head branch not found.")
        self._maybe_configure_https_auth()
        self.git.fetch("origin", branch)
        self.git.checkout_branch_from_remote(branch, remote="origin")
        return branch

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
            base=base_branch,
        )
        return pr.html_url

    def clean_up(self, base_branch="main"):
        self.git.checkout(base_branch)
