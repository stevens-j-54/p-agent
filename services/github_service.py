"""
GitHubService - GitHub API operations for repo and project management
"""

import logging
import os

from github import Github
from github.GithubException import GithubException

from config import GITHUB_USERNAME

logger = logging.getLogger(__name__)


class GitHubService:
    """Handles GitHub API operations: repos, issues, branches, PRs."""

    def __init__(self):
        token = os.environ.get('GITHUB_TOKEN')
        if not token:
            raise ValueError("GITHUB_TOKEN environment variable not set")
        self.github = Github(token)
        self.username = GITHUB_USERNAME
        self._user = None

    @property
    def user(self):
        if self._user is None:
            self._user = self.github.get_user()
        return self._user

    def _get_repo(self, repo_name: str):
        """Resolve and return a repo object. Accepts short name or full name."""
        if "/" not in repo_name:
            repo_name = f"{self.username}/{repo_name}"
        return self.github.get_repo(repo_name)

    def create_repo(self, name: str, description: str = "", private: bool = True) -> dict:
        """Create a new GitHub repository."""
        try:
            repo = self.user.create_repo(
                name,
                description=description,
                private=private,
                auto_init=True
            )
            return {
                "success": True,
                "name": repo.name,
                "full_name": repo.full_name,
                "url": repo.html_url,
                "private": repo.private,
                "message": f"Repository created: {repo.full_name}"
            }
        except GithubException as e:
            logger.error("GitHub API error: %s", e.data.get('message', str(e)))
            return {"success": False, "error": f"GitHub error: {e.data.get('message', str(e))}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_repos(self) -> dict:
        """List all repositories for the account."""
        try:
            repos = []
            for repo in self.user.get_repos():
                repos.append({
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "description": repo.description or "",
                    "private": repo.private,
                    "url": repo.html_url,
                })
            return {"success": True, "repos": repos}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_issue(self, repo_name: str, title: str, body: str, labels: list = None) -> dict:
        """Create an issue in a repository."""
        try:
            repo = self._get_repo(repo_name)
            kwargs = {"title": title, "body": body}
            if labels:
                kwargs["labels"] = labels
            issue = repo.create_issue(**kwargs)
            return {
                "success": True,
                "number": issue.number,
                "title": issue.title,
                "url": issue.html_url,
                "message": f"Issue #{issue.number} created: {issue.title}"
            }
        except GithubException as e:
            logger.error("GitHub API error: %s", e.data.get('message', str(e)))
            return {"success": False, "error": f"GitHub error: {e.data.get('message', str(e))}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_branch(self, repo_name: str, branch_name: str, from_branch: str = "main") -> dict:
        """Create a new branch in a repository."""
        try:
            repo = self._get_repo(repo_name)
            source = repo.get_branch(from_branch)
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=source.commit.sha
            )
            return {
                "success": True,
                "branch": branch_name,
                "from_branch": from_branch,
                "message": f"Branch '{branch_name}' created from '{from_branch}'"
            }
        except GithubException as e:
            logger.error("GitHub API error: %s", e.data.get('message', str(e)))
            return {"success": False, "error": f"GitHub error: {e.data.get('message', str(e))}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def merge_branch(self, repo_name: str, head_branch: str, base_branch: str = "main",
                     commit_message: str = "") -> dict:
        """Merge a branch into a base branch in a repository."""
        try:
            repo = self._get_repo(repo_name)
            merge_message = commit_message or f"Merge '{head_branch}' into '{base_branch}'"
            result = repo.merge(base=base_branch, head=head_branch, commit_message=merge_message)
            if result is None:
                # No-op merge: head is already up to date with base
                return {
                    "success": True,
                    "merged": False,
                    "message": f"'{head_branch}' is already up to date with '{base_branch}' — nothing to merge"
                }
            return {
                "success": True,
                "merged": True,
                "sha": result.sha,
                "message": f"Merged '{head_branch}' into '{base_branch}' ({result.sha[:7]})"
            }
        except GithubException as e:
            logger.error("GitHub API error: %s", e.data.get('message', str(e)))
            return {"success": False, "error": f"GitHub error: {e.data.get('message', str(e))}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_pull_request(self, repo_name: str, title: str, body: str,
                            head_branch: str, base_branch: str = "main") -> dict:
        """Create a pull request in a repository."""
        try:
            repo = self._get_repo(repo_name)
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch
            )
            return {
                "success": True,
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "message": f"PR #{pr.number} created: {pr.title}"
            }
        except GithubException as e:
            logger.error("GitHub API error: %s", e.data.get('message', str(e)))
            return {"success": False, "error": f"GitHub error: {e.data.get('message', str(e))}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
