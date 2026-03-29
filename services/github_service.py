"""
GitHubService - GitHub API operations for repo and project management
"""

import logging
import os
import time

import requests
from github import Github
from github.GithubException import GithubException

from config import GITHUB_USERNAME, CODEBASE_REPO_NAME, UPSTREAM_CODEBASE_REPO

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

    def _github_error(self, e: GithubException) -> dict:
        """Extract a detailed error dict from a GithubException, including validation errors."""
        data = e.data or {}
        message = data.get('message', str(e))
        errors = data.get('errors', [])
        logger.error(
            "GitHub API error %s: %s | errors: %s | full data: %s",
            e.status, message, errors, data
        )
        detail = f"GitHub error {e.status}: {message}"
        if errors:
            detail += f" | details: {errors}"
        return {"success": False, "error": detail, "github_errors": errors}

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
            return self._github_error(e)
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
            return self._github_error(e)
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
            return self._github_error(e)
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
            return self._github_error(e)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_pull_request(self, repo_name: str, title: str, body: str,
                            head_branch: str, base_branch: str = "main") -> dict:
        """Create a pull request within a repository (same-repo PR)."""
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
            return self._github_error(e)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sync_fork_with_upstream(self) -> dict:
        """
        Sync the fork's main branch with upstream main using GitHub's merge-upstream API.
        This is a remote-to-remote operation — no local git required.
        """
        try:
            token = os.environ.get('GITHUB_TOKEN')
            response = requests.post(
                f"https://api.github.com/repos/{self.username}/{CODEBASE_REPO_NAME}/merge-upstream",
                json={"branch": "main"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=15,
            )
            if response.status_code == 200:
                msg = response.json().get("message", "Fork synced with upstream")
                return {"success": True, "message": msg}
            return {
                "success": False,
                "error": f"GitHub API {response.status_code}: {response.text[:200]}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cleanup_merged_branches(self) -> dict:
        """
        Delete feature branches on the fork whose PRs have been merged upstream.
        Queries the upstream repo for closed/merged PRs originating from this fork.
        """
        try:
            upstream_repo = self.github.get_repo(UPSTREAM_CODEBASE_REPO)
            fork_repo = self._get_repo(CODEBASE_REPO_NAME)
            fork_full_name = f"{self.username}/{CODEBASE_REPO_NAME}"

            merged_branches = set()
            for pr in upstream_repo.get_pulls(state="closed", base="main"):
                if (
                    pr.merged
                    and pr.head.repo
                    and pr.head.repo.full_name == fork_full_name
                    and pr.head.ref != "main"
                ):
                    merged_branches.add(pr.head.ref)

            deleted = []
            for branch_name in merged_branches:
                try:
                    fork_repo.get_git_ref(f"heads/{branch_name}").delete()
                    deleted.append(branch_name)
                    logger.info("Deleted merged branch: %s", branch_name)
                except GithubException:
                    pass  # already deleted or doesn't exist

            return {"success": True, "deleted": deleted}
        except GithubException as e:
            return self._github_error(e)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_ci_status(self, repo_name: str, branch_name: str,
                        timeout_seconds: int = 300) -> dict:
        """
        Wait for the latest CI workflow run on a branch to complete and return
        the result. Polls every 15 seconds up to timeout_seconds.

        On failure, returns the names of the jobs and steps that failed so the
        agent can diagnose and fix the issue before opening a PR.
        """
        if "/" not in repo_name:
            repo_name = f"{self.username}/{repo_name}"

        token = os.environ.get('GITHUB_TOKEN')
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        base_url = f"https://api.github.com/repos/{repo_name}"
        deadline = time.time() + timeout_seconds

        # Brief pause to let GitHub queue the run after a fresh push
        time.sleep(5)

        no_run_deadline = time.time() + 60  # give up if no run appears within 60s

        while time.time() < deadline:
            try:
                resp = requests.get(
                    f"{base_url}/actions/runs",
                    params={"branch": branch_name, "per_page": 1},
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                runs = resp.json().get("workflow_runs", [])

                if not runs:
                    if time.time() > no_run_deadline:
                        return {
                            "success": False,
                            "error": "No CI workflow run appeared within 60s — Actions may be disabled on this repo.",
                        }
                    time.sleep(10)
                    continue

                run = runs[0]

                if run["status"] != "completed":
                    logger.debug("CI run %s status: %s", run["id"], run["status"])
                    time.sleep(15)
                    continue

                conclusion = run.get("conclusion")
                result = {
                    "success": True,
                    "passed": conclusion == "success",
                    "conclusion": conclusion,
                    "run_url": run["html_url"],
                }

                if conclusion != "success":
                    jobs_resp = requests.get(
                        f"{base_url}/actions/runs/{run['id']}/jobs",
                        headers=headers,
                        timeout=10,
                    )
                    jobs_resp.raise_for_status()
                    failed_steps = []
                    for job in jobs_resp.json().get("jobs", []):
                        if job["conclusion"] not in ("success", "skipped"):
                            for step in job.get("steps", []):
                                if step["conclusion"] not in ("success", "skipped", None):
                                    failed_steps.append({
                                        "job": job["name"],
                                        "step": step["name"],
                                        "conclusion": step["conclusion"],
                                    })
                    result["failed_steps"] = failed_steps

                return result

            except Exception as e:
                logger.error("Error polling CI status: %s", e)
                time.sleep(15)

        return {"success": False, "error": f"Timed out after {timeout_seconds}s waiting for CI"}

    def open_upstream_pr(self, title: str, body: str, branch_name: str,
                         base_branch: str = "main") -> dict:
        """Open a PR from our fork against the upstream repository.

        Uses UPSTREAM_CODEBASE_REPO from config to identify the upstream.
        The head is formatted as 'fork-owner:branch' as required by GitHub's API.
        """
        try:
            upstream_repo = self.github.get_repo(UPSTREAM_CODEBASE_REPO)
            head = f"{self.username}:{branch_name}"

            logger.info(
                "Opening upstream PR: upstream=%s head=%s base=%s",
                UPSTREAM_CODEBASE_REPO, head, base_branch
            )

            pr = upstream_repo.create_pull(
                title=title,
                body=body,
                head=head,
                base=base_branch
            )
            return {
                "success": True,
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "message": f"Upstream PR #{pr.number} created: {pr.title}"
            }
        except GithubException as e:
            return self._github_error(e)
        except Exception as e:
            return {"success": False, "error": str(e)}
