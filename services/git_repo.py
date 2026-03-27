"""
GitRepo base class - common git repository functionality
"""

import logging
import os
import subprocess
from pathlib import Path

from config import GIT_USER_NAME, GIT_USER_EMAIL

logger = logging.getLogger(__name__)


class GitRepo:
    """Base class for git repository management."""

    def __init__(self, repo_dir: Path, repo_name: str):
        self.repo_dir = repo_dir
        self.repo_name = repo_name
        self.repo_url = None

    def init(self):
        """Initialize the repo by cloning or pulling."""
        token = os.environ.get('GITHUB_TOKEN')

        if not token:
            raise ValueError("GITHUB_TOKEN environment variable not set")
        if not self.repo_name:
            raise ValueError("GITHUB_USERNAME not configured")

        self.repo_url = f"https://{token}@github.com/{self.repo_name}.git"

        if self.repo_dir.exists() and (self.repo_dir / ".git").exists():
            logger.info("Pulling latest: %s", self.repo_dir)
            self._run_git(["remote", "set-url", "origin", self.repo_url])
            self._run_git(["pull"])
        else:
            logger.info("Cloning %s to %s", self.repo_name, self.repo_dir)
            self.repo_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", self.repo_url, str(self.repo_dir)],
                check=True,
                capture_output=True
            )

        self._run_git(["config", "user.email", GIT_USER_EMAIL])
        self._run_git(["config", "user.name", GIT_USER_NAME])

        logger.info("Repo ready: %s", self.repo_name)
        return self

    def _run_git(self, args: list) -> subprocess.CompletedProcess:
        """Run a git command in the repo directory."""
        return subprocess.run(
            ["git"] + args,
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
            text=True
        )

    def pull_latest(self) -> dict:
        """Pull latest changes from remote."""
        try:
            self._run_git(["pull"])
            return {"success": True}
        except Exception as e:
            logger.error("Pull failed for %s: %s", self.repo_name, e)
            return {"success": False, "error": str(e)}

    def checkout_branch(self, branch_name: str) -> dict:
        """Fetch from origin and check out a branch locally."""
        try:
            self._run_git(["fetch", "origin"])
            self._run_git(["checkout", branch_name])
            logger.info("Checked out branch: %s", branch_name)
            return {"success": True, "branch": branch_name}
        except subprocess.CalledProcessError as e:
            logger.error("Checkout failed for branch %s: %s", branch_name, e.stderr)
            return {"success": False, "error": f"Git error: {e.stderr}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_files(self) -> dict:
        """List all files in the repo."""
        try:
            files = []
            for file_path in self.repo_dir.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(self.repo_dir)
                    if relative_path.parts and relative_path.parts[0] == ".git":
                        continue
                    files.append(str(relative_path))

            return {
                "success": True,
                "files": sorted(files)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def read_file(self, file_path: str) -> dict:
        """Read contents of a file."""
        try:
            full_path = self.repo_dir / file_path

            if not full_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }

            if not full_path.is_file():
                return {
                    "success": False,
                    "error": f"Path is not a file: {file_path}"
                }

            content = full_path.read_text()

            return {
                "success": True,
                "path": file_path,
                "content": content
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def write_file(self, file_path: str, content: str) -> dict:
        """Write content to a file (creates parent dirs if needed)."""
        try:
            full_path = self.repo_dir / file_path

            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

            self._run_git(["add", file_path])

            return {
                "success": True,
                "path": file_path
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def commit_and_push(self, commit_message: str) -> dict:
        """Commit staged changes and push to remote."""
        try:
            status = self._run_git(["status", "--porcelain"])

            if not status.stdout.strip():
                return {
                    "success": True,
                    "action": "no_changes",
                    "message": "No changes to commit."
                }

            self._run_git(["commit", "-m", commit_message])
            self._run_git(["push", "-u", "origin", "HEAD"])

            return {
                "success": True,
                "action": "pushed",
                "message": "Changes committed and pushed successfully."
            }
        except subprocess.CalledProcessError as e:
            logger.error("Git error in %s: %s", self.repo_name, e.stderr)
            return {
                "success": False,
                "error": f"Git error: {e.stderr}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
