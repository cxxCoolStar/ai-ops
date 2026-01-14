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

# Claude 配置
CLAUDE_COMMAND = os.getenv("CLAUDE_COMMAND", "claude")

# GitHub 配置
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
