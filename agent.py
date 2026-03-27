"""
Autonomous Email Agent
==========================================
A simple agent that polls its Gmail inbox and replies to emails.
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
)
from prompts import load_system_prompt, EMAIL_RECEIVED_TEMPLATE
from tools import TOOLS, handle_tool_call
from services import Workspace, EmailService, AgentCore, GitHubService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


class EmailAgent:
    def __init__(self):
        self.email_service = None
        self.claude = None
        self._workspaces: dict[str, Workspace] = {}
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

    def is_authorized_sender(self, sender):
        """Check if sender is in authorized list."""
        if not AUTHORIZED_SENDERS:
            logger.error("No authorized senders configured — rejecting all emails")
            return False

        email = sender
        if '<' in sender:
            email = sender.split('<')[1].split('>')[0]

        return email.lower() in [s.lower() for s in AUTHORIZED_SENDERS]

    def process_email(self, email):
        """Process an email using Claude with tool support."""
        self.agent_core.pull_latest()
        system_prompt = load_system_prompt()

        user_message = EMAIL_RECEIVED_TEMPLATE.format(
            sender=email['sender'],
            subject=email['subject'],
            body=email['body']
        )

        messages = [{"role": "user", "content": user_message}]

        try:
            response = self.claude.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
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
                    max_tokens=4096,
                    system=system_prompt,
                    tools=TOOLS,
                    messages=messages
                )

            text_blocks = [block.text for block in response.content if hasattr(block, 'text')]
            return "\n".join(text_blocks)

        except Exception as e:
            logger.error("Claude API error: %s", e)
            return f"Something went wrong on my end. Please try again.\n\n(Error: {str(e)[:100]})"


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

    logger.info("Polling interval: %ss | Authorized senders: %s",
                POLL_INTERVAL_SECONDS, AUTHORIZED_SENDERS or "ALL (not configured)")
    logger.info("Agent running")

    while True:
        try:
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

                    logger.info("Processing with Claude...")
                    response = agent.process_email(email)

                    logger.info("Sending reply...")
                    sent = agent.email_service.send_reply(email, response)

                    if sent:
                        agent.email_service.mark_as_read(email['id'])
                        logger.info("Done")
                    else:
                        logger.error("Reply failed — email left unread for retry")

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
