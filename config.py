"""
Config for the AI Agent
"""

from pathlib import Path
import os
import json
from dotenv import load_dotenv

load_dotenv()

POLL_INTERVAL_SECONDS = 10

AUTHORIZED_SENDERS = json.loads(os.getenv("AUTHORIZED_SENDERS", "[]"))

CLAUDE_MODEL = "claude-sonnet-4-6"

GIT_USER_NAME = "James Stevens"
GIT_USER_EMAIL = "stevens@poolbegsolutions.com"

REPOS_BASE_DIR = Path("./repos")
AGENT_CORE_DIR = Path("./agent-core")

GITHUB_USERNAME = "stevens-j-54"
AGENT_CORE_REPO = f"{GITHUB_USERNAME}/agent-core"

CODEBASE_REPO_NAME = "p-agent"
UPSTREAM_CODEBASE_REPO = os.getenv("UPSTREAM_CODEBASE_REPO", "quaneh2/p-agent")

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_AUTHORIZED_IDS = json.loads(os.getenv("TELEGRAM_AUTHORIZED_IDS", "[]"))
