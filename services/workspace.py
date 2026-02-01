"""
Workspace service - manages the local git workspace
"""

import os
import subprocess
from pathlib import Path

from config import GIT_USER_NAME, GIT_USER_EMAIL


class Workspace:
    """Manages the local git workspace."""

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.repo_url = None

    def init(self):
        """Initialize the workspace by cloning or pulling the repo."""
        token = os.environ.get('GITHUB_TOKEN')
        repo_name = os.environ.get('GITHUB_REPO')

        if not token:
            raise ValueError("GITHUB_TOKEN environment variable not set")
        if not repo_name:
            raise ValueError("GITHUB_REPO environment variable not set (format: username/repo-name)")

        # Construct authenticated repo URL
        self.repo_url = f"https://{token}@github.com/{repo_name}.git"

        if self.workspace_dir.exists() and (self.workspace_dir / ".git").exists():
            # Workspace exists - update remote URL and pull latest
            print(f"Workspace exists at {self.workspace_dir}, pulling latest...")
            self._run_git(["remote", "set-url", "origin", self.repo_url])
            self._run_git(["pull"])
        else:
            # Clone fresh
            print(f"Cloning repository to {self.workspace_dir}...")
            self.workspace_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", self.repo_url, str(self.workspace_dir)],
                check=True,
                capture_output=True
            )

        # Configure git user for commits
        self._run_git(["config", "user.email", GIT_USER_EMAIL])
        self._run_git(["config", "user.name", GIT_USER_NAME])

        print(f"Workspace ready: {self.workspace_dir}")
        return self

    def _run_git(self, args: list) -> subprocess.CompletedProcess:
        """Run a git command in the workspace directory."""
        return subprocess.run(
            ["git"] + args,
            cwd=self.workspace_dir,
            check=True,
            capture_output=True,
            text=True
        )

    def save_document(self, file_path: str, content: str) -> dict:
        """Save a document to the workspace."""
        try:
            full_path = self.workspace_dir / file_path

            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the file
            full_path.write_text(content)

            # Stage the file
            self._run_git(["add", file_path])

            return {
                "success": True,
                "action": "saved",
                "path": file_path,
                "message": f"Document saved to workspace: {file_path}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
            
    def delete_document(self, file_path: str) -> dict:
        """Delete a document from the workspace."""
        try:
            full_path = self.workspace_dir / file_path
            
            if not full_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }
            
            # Delete the file
            full_path.unlink()
            
            # Stage the deletion
            self._run_git(["add", file_path])
            
            return {
                "success": True,
                "action": "deleted",
                "path": file_path,
                "message": f"Document deleted from workspace: {file_path}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def commit_and_push(self, commit_message: str) -> dict:
        """Commit staged changes and push to remote."""
        try:
            # Check if there are changes to commit
            status = self._run_git(["status", "--porcelain"])

            if not status.stdout.strip():
                return {
                    "success": True,
                    "action": "no_changes",
                    "message": "No changes to commit."
                }

            # Commit
            self._run_git(["commit", "-m", commit_message])

            # Push
            self._run_git(["push"])

            return {
                "success": True,
                "action": "pushed",
                "message": f"Changes committed and pushed successfully."
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "error": f"Git error: {e.stderr}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def list_documents(self) -> dict:
        """List all documents in the workspace."""
        try:
            documents = []
            for file_path in self.workspace_dir.rglob("*"):
                if file_path.is_file() and ".git" not in str(file_path):
                    relative_path = file_path.relative_to(self.workspace_dir)
                    documents.append(str(relative_path))

            return {
                "success": True,
                "documents": sorted(documents)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
