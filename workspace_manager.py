import os
import shutil
import time
import uuid

import config
from git_service import GitService


class WorkspaceManager:
    def __init__(self, base_dir=None):
        self.base_dir = os.path.abspath(base_dir or config.WORKSPACES_DIR)
        os.makedirs(self.base_dir, exist_ok=True)

    def allocate(self):
        name = f"ws-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        path = os.path.join(self.base_dir, name)
        os.makedirs(path, exist_ok=False)
        return path

    def release(self, path):
        if not path:
            return
        abs_path = os.path.abspath(path)
        if abs_path.startswith(self.base_dir + os.sep) and os.path.exists(abs_path):
            shutil.rmtree(abs_path, ignore_errors=False)

    def clone_into(self, repo_url, dest_dir):
        return GitService.clone(repo_url, dest_dir)

    def normalize_gitlab_https_url(self, repo_url):
        url = (repo_url or "").strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return url
        return url
