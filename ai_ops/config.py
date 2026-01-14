import os
from dotenv import load_dotenv

load_dotenv()

def _parse_int(value, default):
    s = (value if value is not None else "").strip()
    if s.startswith(("+", "-")):
        sign = s[0]
        digits = s[1:]
        if digits.isdigit():
            return int(sign + digits)
        return default
    if s.isdigit():
        return int(s)
    return default


SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = _parse_int(os.getenv("SMTP_PORT"), 587)
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")
EMAIL_ENABLED = (os.getenv("EMAIL_ENABLED", "true") or "true").strip().lower() in ("1", "true", "yes", "y", "on")

LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "app.log")
KEYWORDS = os.getenv("KEYWORDS", "ERROR,Exception,CRITICAL").split(",")
DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "2"))
DEDUP_WINDOW_SECONDS = _parse_int(os.getenv("DEDUP_WINDOW_SECONDS"), 3600)
MAX_ERROR_QUEUE_SIZE = _parse_int(os.getenv("MAX_ERROR_QUEUE_SIZE"), 100)

CLAUDE_COMMAND = os.getenv("CLAUDE_COMMAND", "claude")
CLAUDE_ARGS = os.getenv("CLAUDE_ARGS", "")
CLAUDE_FIX_MODE = os.getenv("CLAUDE_FIX_MODE", "code_blocks").strip().lower()

CODE_HOST = os.getenv("CODE_HOST", "gitlab").strip().lower()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
PR_COMMENT_COMMAND_PREFIX = os.getenv("PR_COMMENT_COMMAND_PREFIX", "/ai-ops")

GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
GITLAB_PROJECT = os.getenv("GITLAB_PROJECT")
GITLAB_TIMEOUT_SECONDS = _parse_int(os.getenv("GITLAB_TIMEOUT_SECONDS"), 30)

HTTP_HOST = os.getenv("HTTP_HOST", "127.0.0.1")
HTTP_PORT = _parse_int(os.getenv("HTTP_PORT"), 8080)
WORKSPACES_DIR = os.getenv("WORKSPACES_DIR", "workspaces")
TRACE_DB_PATH = os.getenv("TRACE_DB_PATH", "data/traces.db")
MAX_CONCURRENT_TASKS = _parse_int(os.getenv("MAX_CONCURRENT_TASKS"), 1)

AGENT_SERVER_URL = os.getenv("AGENT_SERVER_URL", f"http://{HTTP_HOST}:{HTTP_PORT}")
AGENT_API_KEY = os.getenv("AGENT_API_KEY")

SERVER_API_KEY = os.getenv("SERVER_API_KEY")
