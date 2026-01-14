import os
import re
import shutil
import time
import urllib.parse
import uuid

from ai_ops import config
from ai_ops.vcs.git_service import GitService


class WorkspaceManager:
    def __init__(self, base_dir=None):
        self.base_dir = os.path.abspath(base_dir or config.WORKSPACES_DIR)
        os.makedirs(self.base_dir, exist_ok=True)

    def allocate(self, repo_url=None, trace_id=None):
        slug = self._repo_slug(repo_url) if repo_url else ""
        short = (trace_id or "").replace("-", "")[:8] or uuid.uuid4().hex[:8]
        ts = int(time.time())
        if slug:
            name = f"{slug}-ws-{ts}-{short}"
        else:
            name = f"ws-{ts}-{short}"
        path = os.path.join(self.base_dir, name)
        os.makedirs(path, exist_ok=False)
        return path

    def release(self, path):
        if not path:
            return
        abs_path = os.path.abspath(path)
        if abs_path.startswith(self.base_dir + os.sep) and os.path.exists(abs_path):
            for _ in range(8):
                try:
                    shutil.rmtree(abs_path, ignore_errors=False)
                    return
                except PermissionError:
                    time.sleep(0.25)
                except FileNotFoundError:
                    return
                except OSError:
                    time.sleep(0.25)
            shutil.rmtree(abs_path, ignore_errors=True)

    def clone_into(self, repo_url, dest_dir):
        return GitService.clone(repo_url, dest_dir)

    def _repo_slug(self, repo_url):
        url = (repo_url or "").strip()
        name = ""
        if url.startswith("http://") or url.startswith("https://"):
            parsed = urllib.parse.urlparse(url)
            name = os.path.basename(parsed.path)
        elif "@" in url and ":" in url:
            name = url.rsplit(":", 1)[-1]
            name = os.path.basename(name)
        else:
            name = os.path.basename(url)

        if name.endswith(".git"):
            name = name[: -len(".git")]
        name = (name or "repo").strip().lower()
        name = re.sub(r"[^a-z0-9._-]+", "-", name).strip("-._")
        if not name:
            name = "repo"
        return name[:32]

