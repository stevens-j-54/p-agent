"""
Autonomous Email Agent
==========================================
A simple agent that polls its Gmail inbox and Telegram for messages and replies.
"""

import os
import logging
import argparse
import time

import anthropic

from config import (
    POLL_INTERVAL_SECONDS,
    AUTHORIZED_SENDERS,
    CLAUDE_MODEL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_AUTHORIZED_IDS,
)
from prompts import load_system_prompt, EMAIL_RECEIVED_TEMPLATE, TELEGRAM_MESSAGE_TEMPLATE
from tools import TOOLS, handle_tool_call
from services import Workspace, EmailService, AgentCore, GitHubService, TelegramService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

MAX_TELEGRAM_HISTORY = 20  # message turns to keep per chat session


def _build_messages(thread_history, current_message):
    """
    Build the Claude messages array from thread history + current email.

    Merges consecutive same-role messages (e.g. two user emails in a row)
    and drops any leading assistant message, since Claude requires the first
    message to be from the user.
    """
    merged = []
    for msg in thread_history:
        if merged and merged[-1]['role'] == msg['role']:
            merged[-1]['content'] += '\n\n---\n\n' + msg['content']
        else:
            merged.append({'role': msg['role'], 'content': msg['content']})

    if merged and merged[0]['role'] == 'assistant':
        merged = merged[1:]

    merged.append({"role": "user", "content": current_message})
    return merged


class EmailAgent:
    def __init__(self):
        self.email_service = None
        self.telegram_service = None
        self.claude = None
        self._workspaces: dict[str, Workspace] = {}
        self._telegram_sessions: dict[int, list] = {}
        self.agent_core = None
        self.github_service = None

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

        self.claude = anthropic.Anthropic(api_key=api_key, max_retries=5)
        logger.info("Claude client initialised (model: %s)", CLAUDE_MODEL)
        return self

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

    def init_telegram(self):
        """Initialize Telegram service if a bot token is configured."""
        if not TELEGRAM_BOT_TOKEN:
            logger.info("No TELEGRAM_BOT_TOKEN configured — Telegram disabled")
            return self
        self.telegram_service = TelegramService(TELEGRAM_BOT_TOKEN)
        self.telegram_service.skip_pending()
        logger.info("Telegram service initialised")
        return self

    def is_authorized_sender(self, sender):
        """Check if an email sender is in the authorized list."""
        if not AUTHORIZED_SENDERS:
            logger.error("No authorized senders configured — rejecting all emails")
            return False

        email = sender
        if '<' in sender:
            email = sender.split('<')[1].split('>')[0]

        return email.lower() in [s.lower() for s in AUTHORIZED_SENDERS]

    def is_authorized_telegram_user(self, user_id: int) -> bool:
        """Check if a Telegram user ID is in the authorized list."""
        if not TELEGRAM_AUTHORIZED_IDS:
            logger.error("No authorized Telegram users configured — rejecting all messages")
            return False
        return user_id in TELEGRAM_AUTHORIZED_IDS

    def _run_claude(self, messages: list, system_prompt: str) -> str:
        """
        Core Claude tool-use loop shared by all channels.
        Runs until Claude stops requesting tools, then returns the final text response.
        """
        try:
            response = self.claude.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=16384,
                system=system_prompt,
                tools=TOOLS,
                messages=messages
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

                response = self.claude.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=16384,
                    system=system_prompt,
                    tools=TOOLS,
                    messages=messages
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
        messages = _build_messages(thread_history, user_message)
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

        # Pass a copy so intermediate tool-call messages don't pollute session history
        response = self._run_claude(list(history), system_prompt)

        history.append({"role": "assistant", "content": response})

        # Trim session to keep the context window manageable
        if len(history) > MAX_TELEGRAM_HISTORY:
            self._telegram_sessions[chat_id] = history[-MAX_TELEGRAM_HISTORY:]

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
    agent.init_telegram()

    logger.info("Polling interval: %ss | Authorized senders: %s",
                POLL_INTERVAL_SECONDS, AUTHORIZED_SENDERS or "ALL (not configured)")
    logger.info("Agent running")

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

                    if not agent.is_authorized_sender(email['sender']):
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

                    if not agent.is_authorized_telegram_user(user_id):
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
