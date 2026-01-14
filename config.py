import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# SMTP 配置
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# 接收方配置
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# 日志监控配置
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "app.log")
KEYWORDS = os.getenv("KEYWORDS", "ERROR,Exception,CRITICAL").split(",")
DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "2"))
DEDUP_WINDOW_SECONDS = int(os.getenv("DEDUP_WINDOW_SECONDS", "3600"))
MAX_ERROR_QUEUE_SIZE = int(os.getenv("MAX_ERROR_QUEUE_SIZE", "100"))

# Claude 配置
CLAUDE_COMMAND = os.getenv("CLAUDE_COMMAND", "claude")

# 平台选择
CODE_HOST = os.getenv("CODE_HOST", "gitlab").strip().lower()

# GitHub 配置
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

# GitLab 配置
GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
GITLAB_PROJECT = os.getenv("GITLAB_PROJECT")
GITLAB_TIMEOUT_SECONDS = int(os.getenv("GITLAB_TIMEOUT_SECONDS", "30"))

# HTTP 与工作区
HTTP_HOST = os.getenv("HTTP_HOST", "127.0.0.1")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
WORKSPACES_DIR = os.getenv("WORKSPACES_DIR", "workspaces")
TRACE_DB_PATH = os.getenv("TRACE_DB_PATH", "data/traces.db")
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "1"))
