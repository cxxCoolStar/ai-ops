import os
import re
from dotenv import load_dotenv

load_dotenv()

def _env_int(name, default):
    raw = os.getenv(name)
    s = (raw if raw is not None else "").strip()
    if re.fullmatch(r"-?\d+", s or ""):
        return int(s)
    return int(default)


def _env_float(name, default):
    raw = os.getenv(name)
    s = (raw if raw is not None else "").strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", s or ""):
        return float(s)
    return float(default)


SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = _env_int("SMTP_PORT", 587)
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")

LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "app.log")
KEYWORDS = os.getenv("KEYWORDS", "ERROR,Exception,CRITICAL").split(",")
DEBOUNCE_SECONDS = _env_float("DEBOUNCE_SECONDS", 2.0)
DEDUP_WINDOW_SECONDS = _env_int("DEDUP_WINDOW_SECONDS", 3600)
MAX_ERROR_QUEUE_SIZE = _env_int("MAX_ERROR_QUEUE_SIZE", 100)

CLAUDE_COMMAND = os.getenv("CLAUDE_COMMAND", "claude")
CLAUDE_ARGS = os.getenv("CLAUDE_ARGS", "")
CLAUDE_FIX_MODE = os.getenv("CLAUDE_FIX_MODE", "code_blocks").strip().lower()

CODE_HOST = os.getenv("CODE_HOST", "gitlab").strip().lower()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
GITLAB_PROJECT = os.getenv("GITLAB_PROJECT")
GITLAB_TIMEOUT_SECONDS = _env_int("GITLAB_TIMEOUT_SECONDS", 30)

HTTP_HOST = os.getenv("HTTP_HOST", "127.0.0.1")
HTTP_PORT = _env_int("HTTP_PORT", 8080)
WORKSPACES_DIR = os.getenv("WORKSPACES_DIR", "workspaces")
TRACE_DB_PATH = os.getenv("TRACE_DB_PATH", "data/traces.db")
MAX_CONCURRENT_TASKS = _env_int("MAX_CONCURRENT_TASKS", 1)

AGENT_SERVER_URL = os.getenv("AGENT_SERVER_URL", f"http://{HTTP_HOST}:{HTTP_PORT}")
AGENT_API_KEY = os.getenv("AGENT_API_KEY")
AGENT_REPO_URL = os.getenv("AGENT_REPO_URL")

SERVER_API_KEY = os.getenv("SERVER_API_KEY")

ELK_URL = os.getenv("ELK_URL", "http://127.0.0.1:9200").rstrip("/")
ELK_INDEX = os.getenv("ELK_INDEX", "filebeat-*")
ELK_QUERY = os.getenv("ELK_QUERY", "log.level:ERROR")
ELK_POLL_SECONDS = _env_float("ELK_POLL_SECONDS", 2.0)
ELK_SINCE_SECONDS = _env_int("ELK_SINCE_SECONDS", 300)
ELK_BATCH_SIZE = _env_int("ELK_BATCH_SIZE", 50)
