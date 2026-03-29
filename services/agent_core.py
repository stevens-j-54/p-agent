"""
AgentCore service - manages the agent's personality and configuration repo
"""

import logging
import os

from github import Github
from github.GithubException import GithubException

from config import AGENT_CORE_DIR, AGENT_CORE_REPO
from prompts.system import DEFAULT_IDENTITY, DEFAULT_SOUL, DEFAULT_MEMORY

from .git_repo import GitRepo

logger = logging.getLogger(__name__)


class AgentCore(GitRepo):
    """Manages the agent-core repository containing personality and config."""

    def __init__(self):
        super().__init__(AGENT_CORE_DIR, AGENT_CORE_REPO)
        self.github = None
        self.repo = None
        self.core_dir = self.repo_dir

    def init(self):
        """
        Initialize agent-core repo.
        - Create repo if it doesn't exist
        - Clone/pull the repo
        - Seed with default files if missing
        """
        token = os.environ.get('GITHUB_TOKEN')

        if not token:
            raise ValueError("GITHUB_TOKEN environment variable not set")
        if not self.repo_name:
            raise ValueError("GITHUB_USERNAME not configured")

        self.github = Github(token)
        self._ensure_repo_exists()
        super().init()
        self._seed_if_needed()

        return self

    def _ensure_repo_exists(self):
        """Create the repo if it doesn't exist."""
        try:
            self.repo = self.github.get_repo(self.repo_name)
            logger.info("Agent-core repo exists: %s", self.repo_name)
        except GithubException as e:
            if e.status == 404:
                logger.info("Creating agent-core repo: %s", self.repo_name)
                user = self.github.get_user()
                just_repo_name = self.repo_name.split("/")[-1]
                self.repo = user.create_repo(
                    just_repo_name,
                    description="Agent personality and configuration",
                    private=True,
                    auto_init=True
                )
                logger.info("Agent-core repo created: %s", self.repo_name)
            else:
                raise

    def _seed_if_needed(self):
        """Seed any missing agent-core files with defaults."""
        seeds = {
            "IDENTITY.md": DEFAULT_IDENTITY,
            "SOUL.md": DEFAULT_SOUL,
            "MEMORY.md": f"# Memory\n\n{DEFAULT_MEMORY}",
        }

        missing = {f: c for f, c in seeds.items() if not (self.repo_dir / f).exists()}

        if missing:
            logger.info("Seeding agent-core with missing files: %s", ", ".join(missing))
            for filename, content in missing.items():
                (self.repo_dir / filename).write_text(content)

            self._run_git(["add", "."])
            self._run_git(["commit", "-m", "Initial setup: seed default identity, soul, and memory"])
            self._run_git(["push"])
            logger.info("Agent-core seeded successfully")

    def upsert_file(self, file_path: str, content: str, commit_message: str) -> dict:
        """Create or update a file in agent-core, commit, and push."""
        write_result = self.write_file(file_path, content)
        if not write_result.get("success"):
            return write_result
        return self.commit_and_push(commit_message)
