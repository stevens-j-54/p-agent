"""
Autonomous Email Agent
==========================================
A simple agent that polls its Gmail inbox and Telegram for messages and replies.
"""

import os
import json
import logging
import argparse
import time

import anthropic

from config import (
    POLL_INTERVAL_SECONDS,
    AUTHORIZED_SENDERS,
    CLAUDE_MODEL,
    TELEGRAM_BOT_TOKEN,
    AGENT_CORE_DIR,
)
from prompts import load_system_prompt, EMAIL_RECEIVED_TEMPLATE, TELEGRAM_MESSAGE_TEMPLATE
from tools import TOOLS, handle_tool_call
from services import Workspace, EmailService, AgentCore, GitHubService, TelegramService, FetchService
from skills import HNDigestSkill
from utils import build_messages, is_authorized_email_sender, is_authorized_telegram_user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

MAX_TELEGRAM_HISTORY = 20  # message turns to keep per chat session

# Anthropic rate-limit + burst control.
# Keep this in-process (per agent instance) to avoid immediate back-to-back
# calls causing repeated 429 → sleep → success → 429 patterns during tool loops.
ANTHROPIC_MIN_REQUEST_INTERVAL_SECONDS = 0.5
ANTHROPIC_MAX_RETRIES = 10
ANTHROPIC_BACKOFF_INITIAL_SECONDS = 1.0
ANTHROPIC_BACKOFF_MAX_SECONDS = 60.0



class EmailAgent:
    def __init__(self):
        self.email_service = None
        self.telegram_service = None
        self.claude = None
        self._workspaces: dict[str, Workspace] = {}
        self._telegram_sessions: dict[int, list] = {}
        self.agent_core = None
        self.github_service = None
        self.fetch_service = FetchService()
        self._anthropic_next_allowed_ts = 0.0
        self._anthropic_last_call_ts = 0.0
        self._skills: dict = {}

    def get_workspace(self, repo_name: str = "workspace") -> Workspace:
        """Get (or lazily initialise) a workspace for the given repo name."""
        if repo_name not in self._workspaces:
            logger.info("Initialising workspace: %s", repo_name)
            ws = Workspace(repo_name)
            ws.init()
            self._workspaces[repo_name] = ws
        return self._workspaces[repo_name]

    @property
    def services(self):
        return {
            "get_workspace": self.get_workspace,
            "github": self.github_service,
            "agent_core": self.agent_core,
            "fetch": self.fetch_service,
            "skills": self._skills,
        }

    def init_email(self):
        """Initialize email service."""
        self.email_service = EmailService()
        self.email_service.authenticate()
        return self

    def init_claude(self):
        """Initialize Claude client."""
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        # Disable SDK-level retries so we can apply a shared, cross-call limiter.
        self.claude = anthropic.Anthropic(api_key=api_key, max_retries=0)
        logger.info("Claude client initialised (model: %s)", CLAUDE_MODEL)
        return self

    def _extract_retry_after_seconds(self, exc: Exception):
        """
        Best-effort extraction of retry delay from Anthropic/HTTPX exceptions.
        Handles common shapes without depending on SDK internals.
        """
        response = getattr(exc, "response", None)
        if response is None:
            return None
        status_code = getattr(response, "status_code", None)
        if status_code != 429:
            return None
        headers = getattr(response, "headers", None) or {}

        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after is not None:
            try:
                return float(retry_after)
            except Exception:
                return None

        # Some APIs return a unix timestamp reset. If present, convert to seconds.
        reset = (
            headers.get("x-ratelimit-reset")
            or headers.get("X-RateLimit-Reset")
            or headers.get("anthropic-ratelimit-reset")
            or headers.get("Anthropic-RateLimit-Reset")
        )
        if reset is not None:
            try:
                reset_ts = float(reset)
                now = time.time()
                return max(0.0, reset_ts - now)
            except Exception:
                return None

        return None

    def _sleep_for_anthropic_throttle(self):
        now = time.time()
        # Burst control: ensure a minimum interval between calls.
        since_last = now - self._anthropic_last_call_ts
        if since_last < ANTHROPIC_MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(ANTHROPIC_MIN_REQUEST_INTERVAL_SECONDS - since_last)
            now = time.time()
        # Shared cooldown: if we've been told to wait until a certain time, respect it.
        if now < self._anthropic_next_allowed_ts:
            time.sleep(self._anthropic_next_allowed_ts - now)

    def _claude_messages_create(self, *, model: str, max_tokens: int, system: str, tools, messages):
        """
        Wrapper around Anthropic messages.create with shared throttling and retries.
        This avoids immediate follow-on calls after a successful retry window reset.
        """
        attempt = 0
        backoff = ANTHROPIC_BACKOFF_INITIAL_SECONDS
        while True:
            self._sleep_for_anthropic_throttle()
            self._anthropic_last_call_ts = time.time()
            try:
                return self.claude.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    tools=tools,
                    messages=messages
                )
            except Exception as e:
                retry_after = self._extract_retry_after_seconds(e)
                if retry_after is not None:
                    # Add a small cushion to avoid cutting it too close.
                    delay = max(0.0, retry_after) + 0.25
                    self._anthropic_next_allowed_ts = max(self._anthropic_next_allowed_ts, time.time() + delay)
                    logger.info("Anthropic 429 — retrying in %.3f seconds", delay)
                else:
                    # Unknown transient: exponential backoff.
                    delay = min(backoff, ANTHROPIC_BACKOFF_MAX_SECONDS)
                    self._anthropic_next_allowed_ts = max(self._anthropic_next_allowed_ts, time.time() + delay)
                    logger.info("Anthropic request failed — retrying in %.3f seconds (%s)", delay, type(e).__name__)
                    backoff = min(backoff * 2.0, ANTHROPIC_BACKOFF_MAX_SECONDS)

                attempt += 1
                if attempt > ANTHROPIC_MAX_RETRIES:
                    raise

    def init_workspace(self):
        """Initialize the default workspace."""
        self.get_workspace("workspace")
        return self

    def init_github(self):
        """Initialize the GitHub service."""
        self.github_service = GitHubService()
        logger.info("GitHub service initialised")
        return self

    def init_agent_core(self):
        """Initialize the agent-core configuration repo."""
        self.agent_core = AgentCore()
        self.agent_core.init()
        return self

    def init_skills(self):
        """Initialize skills, wiring in required services."""
        self._skills["hn_digest"] = HNDigestSkill(
            fetch_service=self.fetch_service,
            workspace_fn=self.get_workspace,
        )
        logger.info("Skills initialised: %s", list(self._skills.keys()))
        return self

    def sync_codebase(self):
        """
        Sync fork main with upstream and clean up merged branches.
        Also pulls the local p-agent workspace if already initialised so it
        stays in sync with the freshly-updated fork.
        """
        logger.info("Syncing fork with upstream...")
        result = self.github_service.sync_fork_with_upstream()
        if result.get("success"):
            logger.info("Fork sync: %s", result["message"])
        else:
            logger.warning("Fork sync failed (non-fatal): %s", result.get("error"))

        result = self.github_service.cleanup_merged_branches()
        if result.get("success"):
            deleted = result.get("deleted", [])
            if deleted:
                logger.info("Deleted merged branches: %s", ", ".join(deleted))
        else:
            logger.warning("Branch cleanup failed (non-fatal): %s", result.get("error"))

        if "p-agent" in self._workspaces:
            self._workspaces["p-agent"].pull_latest()

    def init_telegram(self):
        """Initialize Telegram service if a bot token is configured."""
        if not TELEGRAM_BOT_TOKEN:
            logger.info("No TELEGRAM_BOT_TOKEN configured — Telegram disabled")
            return self
        self._telegram_sessions = self._load_telegram_sessions()
        self.telegram_service = TelegramService(TELEGRAM_BOT_TOKEN)
        self.telegram_service.skip_pending()
        logger.info("Telegram service initialised")
        return self

    def _load_telegram_sessions(self) -> dict:
        """Load persisted Telegram session histories from agent-core."""
        sessions_path = AGENT_CORE_DIR / "telegram_sessions.json"
        if not sessions_path.exists():
            return {}
        try:
            data = json.loads(sessions_path.read_text())
            # JSON keys are always strings; convert back to int chat IDs
            return {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.warning("Could not load Telegram sessions (%s) — starting fresh", e)
            return {}

    def _save_telegram_sessions(self):
        """Persist Telegram session histories to agent-core, committing and pushing."""
        result = self.agent_core.upsert_file(
            "telegram_sessions.json",
            json.dumps(self._telegram_sessions, indent=2),
            "Update Telegram session history",
        )
        if not result.get("success"):
            logger.error("Failed to save Telegram sessions: %s", result.get("error"))

    def _run_claude(self, messages: list, system_prompt: str) -> str:
        """
        Core Claude tool-use loop shared by all channels.
        Runs until Claude stops requesting tools, then returns the final text response.
        """
        messages = list(messages)  # own the defensive copy; callers' lists are not mutated
        try:
            response = self._claude_messages_create(
                model=CLAUDE_MODEL,
                max_tokens=16384,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            )

            while response.stop_reason == "tool_use":
                tool_calls = [block for block in response.content if block.type == "tool_use"]
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for tool_call in tool_calls:
                    result = handle_tool_call(tool_call.name, tool_call.input, self.services)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": result
                    })

                messages.append({"role": "user", "content": tool_results})

                response = self._claude_messages_create(
                    model=CLAUDE_MODEL,
                    max_tokens=16384,
                    system=system_prompt,
                    tools=TOOLS,
                    messages=messages,
                )

            text_blocks = [block.text for block in response.content if hasattr(block, 'text')]
            return "\n".join(text_blocks)

        except Exception as e:
            logger.error("Claude API error: %s", e)
            return f"Something went wrong on my end. Please try again.\n\n(Error: {str(e)[:100]})"

    def process_email(self, email):
        """Process an email using Claude with tool support."""
        self.agent_core.pull_latest()
        system_prompt = load_system_prompt()

        user_message = EMAIL_RECEIVED_TEMPLATE.format(
            sender=email['sender'],
            subject=email['subject'],
            body=email['body']
        )

        thread_history = self.email_service.get_thread_context(
            email['thread_id'], email['id']
        )
        messages = build_messages(thread_history, user_message)
        return self._run_claude(messages, system_prompt)

    def process_telegram_update(self, update: dict) -> str:
        """
        Process a Telegram message using Claude with tool support.

        Maintains an in-memory conversation history per chat ID so the agent
        has multi-turn context within a session. History resets on restart.
        """
        message = update['message']
        chat_id = message['chat']['id']
        text = message.get('text', '')

        user = message.get('from', {})
        sender_name = user.get('first_name', 'User')
        if user.get('last_name'):
            sender_name += f" {user['last_name']}"

        self.agent_core.pull_latest()
        system_prompt = load_system_prompt()

        # Get or create session history for this chat
        history = self._telegram_sessions.setdefault(chat_id, [])

        user_content = TELEGRAM_MESSAGE_TEMPLATE.format(
            sender_name=sender_name,
            text=text,
        )
        history.append({"role": "user", "content": user_content})

        response = self._run_claude(history, system_prompt)

        history.append({"role": "assistant", "content": response})

        # Trim session to keep the context window manageable
        if len(history) > MAX_TELEGRAM_HISTORY:
            self._telegram_sessions[chat_id] = history[-MAX_TELEGRAM_HISTORY:]

        self._save_telegram_sessions()
        return response


def run_agent():
    """Main agent loop."""
    logger.info("=" * 50)
    logger.info("AI Agent starting up")
    logger.info("=" * 50)

    agent = EmailAgent()
    agent.init_email()
    agent.init_claude()
    agent.init_github()
    agent.init_workspace()
    agent.init_agent_core()
    agent.init_skills()
    agent.init_telegram()
    agent.sync_codebase()

    logger.info("Polling interval: %ss | Authorized senders: %s",
                POLL_INTERVAL_SECONDS, AUTHORIZED_SENDERS or "ALL (not configured)")
    logger.info("Agent is running")

    while True:
        try:
            # --- Email ---
            logger.debug("Checking for new emails...")
            emails = agent.email_service.get_unread_emails()

            if emails:
                logger.info("Found %d unread email(s)", len(emails))

                for msg in emails:
                    email = agent.email_service.get_email_details(msg['id'])

                    if not email:
                        continue

                    logger.info("Email from: %s | Subject: %s", email['sender'], email['subject'])

                    if not is_authorized_email_sender(email['sender']):
                        logger.warning("Skipping unauthorized sender: %s", email['sender'])
                        agent.email_service.mark_as_read(email['id'])
                        continue

                    logger.info("Processing email with Claude...")
                    response = agent.process_email(email)

                    logger.info("Sending email reply...")
                    sent = agent.email_service.send_reply(email, response)

                    if sent:
                        agent.email_service.mark_as_read(email['id'])
                        logger.info("Email done")
                    else:
                        logger.error("Email reply failed — left unread for retry")

            # --- Telegram ---
            if agent.telegram_service:
                logger.debug("Checking for Telegram messages...")
                updates = agent.telegram_service.get_updates()

                if updates:
                    logger.info("Found %d Telegram update(s)", len(updates))

                for update in updates:
                    if 'message' not in update:
                        continue

                    message = update['message']
                    if 'text' not in message:
                        continue

                    user_id = message.get('from', {}).get('id')
                    chat_id = message['chat']['id']

                    if not is_authorized_telegram_user(user_id):
                        logger.warning("Skipping unauthorized Telegram user: %s", user_id)
                        continue

                    logger.info("Processing Telegram message from user %s...", user_id)
                    response = agent.process_telegram_update(update)

                    agent.telegram_service.send_message(chat_id, response)
                    logger.info("Telegram reply sent")

            time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            logger.info("Agent stopped by user")
            break
        except Exception as e:
            logger.error("Error in main loop: %s", e, exc_info=True)
            logger.info("Retrying in %ss...", POLL_INTERVAL_SECONDS)
            time.sleep(POLL_INTERVAL_SECONDS)


def main():
    parser = argparse.ArgumentParser(description='AI Email Agent')
    parser.add_argument('--auth', action='store_true', help='Run authentication flow only')
    args = parser.parse_args()

    if args.auth:
        logger.info("Running authentication flow...")
        email_service = EmailService()
        email_service.authenticate(force_new=True)
        logger.info("Authentication complete — token.json ready for deployment")
    else:
        run_agent()


if __name__ == '__main__':
    main()
