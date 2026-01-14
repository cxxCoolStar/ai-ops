import os
import subprocess


class GitService:
    def __init__(self, cwd=None):
        self.cwd = os.path.abspath(cwd or os.getcwd())

    def run(self, args):
        return subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=self.cwd,
            check=True,
        )

    @staticmethod
    def clone(repo_url, dest_dir):
        dest_dir = os.path.abspath(dest_dir)
        os.makedirs(os.path.dirname(dest_dir) or ".", exist_ok=True)
        return subprocess.run(
            ["git", "clone", repo_url, dest_dir],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=os.getcwd(),
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

    def push(self, remote, branch_name):
        self.run(["push", remote, branch_name])

    def fetch(self, remote="origin", ref=None):
        args = ["fetch", remote]
        if ref:
            args.append(ref)
        self.run(args)

    def checkout_branch_from_remote(self, branch_name, remote="origin"):
        self.run(["checkout", "-B", branch_name, f"{remote}/{branch_name}"])

    def set_remote_url(self, remote, url):
        self.run(["remote", "set-url", remote, url])

    def current_commit(self):
        result = self.run(["rev-parse", "HEAD"])
        return (result.stdout or "").strip()
