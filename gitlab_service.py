import json
import time
import urllib.parse
import urllib.request

import config
from git_service import GitService


class GitLabService:
    def __init__(self, cwd=None):
        self.base_url = config.GITLAB_BASE_URL.rstrip("/")
        self.token = config.GITLAB_TOKEN
        self.project = config.GITLAB_PROJECT
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

    def clean_up(self, base_branch="main"):
        self.git.checkout(base_branch)

    def create_pull_request(self, branch_name, title, body):
        if not self.token:
            raise ValueError("GitLab Token not configured.")
        if not self.project:
            raise ValueError("GitLab Project not configured.")

        target_branch = self._get_default_branch()
        payload = {
            "source_branch": branch_name,
            "target_branch": target_branch,
            "title": title,
            "description": body,
            "remove_source_branch": False,
        }
        resp = self._request_json(
            "POST",
            f"/api/v4/projects/{self._encode_project(self.project)}/merge_requests",
            payload=payload,
        )
        web_url = resp.get("web_url")
        if not web_url:
            raise ValueError("GitLab API did not return web_url.")
        return web_url

    def _get_default_branch(self):
        resp = self._request_json(
            "GET",
            f"/api/v4/projects/{self._encode_project(self.project)}",
        )
        default_branch = resp.get("default_branch")
        return default_branch or "main"

    def _encode_project(self, project):
        return urllib.parse.quote(project, safe="")

    def _request_json(self, method, path, payload=None):
        url = f"{self.base_url}{path}"
        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=config.GITLAB_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}
