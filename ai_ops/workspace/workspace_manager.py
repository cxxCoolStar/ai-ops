import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid

from ai_ops import config
from ai_ops.vcs.git_service import GitService


class WorkspaceManager:
    _gitlab_username = None

    def __init__(self, base_dir=None):
        self.base_dir = os.path.abspath(base_dir or config.WORKSPACES_DIR)
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_gitlab_username(self):
        if self._gitlab_username:
            return self._gitlab_username
        base = (config.GITLAB_BASE_URL or "").rstrip("/")
        token = config.GITLAB_TOKEN or ""
        if not base or not token:
            return (getattr(config, "GITLAB_USERNAME", None) or "").strip()
        try:
            req = urllib.request.Request(f"{base}/api/v4/user", headers={"PRIVATE-TOKEN": token, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=config.GITLAB_TIMEOUT_SECONDS) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw) if raw else {}
            username = (data.get("username") or "").strip()
            if username:
                self._gitlab_username = username
                return username
        except Exception:
            pass
        return (getattr(config, "GITLAB_USERNAME", None) or "").strip()

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

    def clone_into(self, repo_url, dest_dir, code_host=None):
        host = (code_host or "").strip().lower()
        url = (repo_url or "").strip()
        if host == "gitlab" and url.startswith(("http://", "https://")) and config.GITLAB_TOKEN:
            parsed = urllib.parse.urlparse(url)
            if not parsed.username:
                username = (self._get_gitlab_username() or "oauth2").strip() or "oauth2"
                netloc = f"{username}@{parsed.hostname}"
                if parsed.port:
                    netloc = f"{netloc}:{parsed.port}"
                auth_url = parsed._replace(netloc=netloc).geturl()
                env, askpass_path = GitService._build_askpass_env(config.GITLAB_TOKEN)
                if getattr(config, "GITLAB_DISABLE_PROXY", True):
                    env.update(GitService._proxyless_env())
                try:
                    return GitService.clone(auth_url, dest_dir, env=env, disable_proxy=getattr(config, "GITLAB_DISABLE_PROXY", True))
                finally:
                    try:
                        os.remove(askpass_path)
                    except OSError:
                        pass
        return GitService.clone(url, dest_dir)

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
