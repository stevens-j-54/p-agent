"""
DashboardSkill — generates a static HTML dashboard and pushes it to GitHub Pages.

The dashboard is hosted at https://stevens-j-54.github.io (repo: stevens-j-54.github.io).
GitHub automatically enables Pages for *.github.io repos from the main branch root.

This skill contains NO Claude API calls. It renders HTML from a Python template
and pushes the result via git. Called after any task is added, removed, or completed.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from github import Github
from github.GithubException import GithubException

from config import DASHBOARD_DIR, DASHBOARD_REPO_NAME, GITHUB_USERNAME
from services.git_repo import GitRepo

logger = logging.getLogger(__name__)


class DashboardSkill:
    def __init__(self, github_service, agent_core):
        self.github_service = github_service
        self.agent_core = agent_core
        self._repo: GitRepo | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self) -> dict:
        """
        Full update cycle:
        1. Load current tasks from agent-core
        2. Generate HTML
        3. Ensure GitHub Pages repo exists
        4. Push index.html
        """
        try:
            tasks = self._load_tasks()
            html = self.generate_html(tasks)
            self._ensure_repo_exists()
            repo = self._get_repo()
            repo.write_file("index.html", html)
            result = repo.commit_and_push("Update dashboard")
            if result.get("success"):
                url = f"https://{GITHUB_USERNAME}.github.io"
                logger.info("Dashboard updated: %s", url)
                return {"success": True, "url": url, "action": result.get("action")}
            return result
        except Exception as e:
            logger.error("Dashboard update failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    def generate_html(self, tasks: list) -> str:
        """Render the full index.html from the task list. Pure Python, no Claude."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        recurring = [t for t in tasks if t.get("type") == "recurring" and t.get("status") != "completed"]
        one_time = [t for t in tasks if t.get("type") == "one_time" and t.get("status") != "completed"]
        completed = [t for t in tasks if t.get("status") == "completed"]

        recurring_rows = self._task_rows(recurring, show_cron=True)
        one_time_rows = self._task_rows(one_time, show_cron=False)
        completed_rows = self._task_rows(completed, show_cron=False)

        def section(title: str, rows: str, empty_msg: str) -> str:
            body = rows if rows else f'<tr><td colspan="6" class="empty">{empty_msg}</td></tr>'
            return f"""
        <section>
            <h2>{title}</h2>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Schedule</th>
                            <th>Next Run</th>
                            <th>Last Run</th>
                            <th>Type</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>{body}</tbody>
                </table>
            </div>
        </section>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="60">
    <title>Agent Task Dashboard</title>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        :root {{
            --bg: #0d1117;
            --surface: #161b22;
            --border: #30363d;
            --text: #e6edf3;
            --muted: #8b949e;
            --accent: #58a6ff;
            --green: #3fb950;
            --yellow: #d29922;
            --red: #f85149;
        }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            font-size: 14px;
            line-height: 1.5;
            padding: 2rem 1rem;
        }}
        header {{
            max-width: 1100px;
            margin: 0 auto 2rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1rem;
        }}
        header h1 {{ font-size: 1.5rem; font-weight: 600; color: var(--text); }}
        header p {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }}
        section {{
            max-width: 1100px;
            margin: 0 auto 2.5rem;
        }}
        section h2 {{
            font-size: 1rem;
            font-weight: 600;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.75rem;
        }}
        .table-wrap {{ overflow-x: auto; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            overflow: hidden;
        }}
        th, td {{
            padding: 0.6rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            background: var(--bg);
        }}
        tbody tr:last-child td {{ border-bottom: none; }}
        tbody tr:hover {{ background: rgba(255,255,255,0.03); }}
        .empty {{ color: var(--muted); font-style: italic; text-align: center; padding: 1.5rem; }}
        .badge {{
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .badge-active   {{ background: rgba(63,185,80,0.15);  color: var(--green); }}
        .badge-completed{{ background: rgba(88,166,255,0.15); color: var(--accent); }}
        .badge-paused   {{ background: rgba(210,153,34,0.15); color: var(--yellow); }}
        .badge-skill    {{ background: rgba(88,166,255,0.10); color: var(--accent); }}
        .badge-nl       {{ background: rgba(139,148,158,0.15);color: var(--muted); }}
        code {{
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
            font-size: 0.8rem;
            background: rgba(110,118,129,0.1);
            padding: 0.1em 0.4em;
            border-radius: 4px;
        }}
        footer {{
            max-width: 1100px;
            margin: 3rem auto 0;
            color: var(--muted);
            font-size: 0.8rem;
            text-align: center;
            border-top: 1px solid var(--border);
            padding-top: 1rem;
        }}
    </style>
</head>
<body>
    <header>
        <h1>Agent Task Dashboard</h1>
        <p>Scheduled tasks managed by the agent &mdash; auto-refreshes every 60 seconds</p>
    </header>

    {section("Recurring Tasks", recurring_rows, "No recurring tasks scheduled")}
    {section("Upcoming One-Time Tasks", one_time_rows, "No one-time tasks scheduled")}
    {section("Completed Tasks", completed_rows, "No completed tasks")}

    <footer>Last updated: {now_str}</footer>
</body>
</html>"""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _task_rows(self, tasks: list, show_cron: bool) -> str:
        if not tasks:
            return ""
        rows = []
        for t in tasks:
            schedule = f'<code>{t.get("cron", "")}</code>' if show_cron else self._fmt_dt(t.get("run_at"))
            itype = t.get("instruction_type", "")
            type_badge = (
                '<span class="badge badge-skill">skill</span>'
                if itype == "skill"
                else '<span class="badge badge-nl">natural language</span>'
            )
            status = t.get("status", "active")
            status_badge = f'<span class="badge badge-{status}">{status}</span>'
            rows.append(
                f"<tr>"
                f"<td>{self._esc(t.get('name', ''))}</td>"
                f"<td>{schedule}</td>"
                f"<td>{self._fmt_dt(t.get('next_run'))}</td>"
                f"<td>{self._fmt_dt(t.get('last_run'))}</td>"
                f"<td>{type_badge}</td>"
                f"<td>{status_badge}</td>"
                f"</tr>"
            )
        return "\n".join(rows)

    @staticmethod
    def _fmt_dt(iso: str | None) -> str:
        if not iso:
            return '<span style="color:var(--muted)">—</span>'
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            return iso

    @staticmethod
    def _esc(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

    def _load_tasks(self) -> list:
        from services.scheduler import SCHEDULES_FILE
        result = self.agent_core.read_file(SCHEDULES_FILE)
        if not result.get("success"):
            return []
        try:
            return json.loads(result["content"]).get("tasks", [])
        except (json.JSONDecodeError, KeyError):
            return []

    def _ensure_repo_exists(self) -> None:
        """Create the GitHub Pages repo if it doesn't exist."""
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN not set")
        g = Github(token)
        repo_short = DASHBOARD_REPO_NAME.split("/")[-1]
        try:
            g.get_repo(DASHBOARD_REPO_NAME)
            logger.debug("Dashboard repo exists: %s", DASHBOARD_REPO_NAME)
        except GithubException as e:
            if e.status == 404:
                logger.info("Creating dashboard repo: %s", DASHBOARD_REPO_NAME)
                user = g.get_user()
                user.create_repo(
                    repo_short,
                    description="Agent task dashboard",
                    private=False,
                    auto_init=True,
                )
                logger.info("Dashboard repo created: %s", DASHBOARD_REPO_NAME)
                # Reset cached repo so it will be re-cloned
                self._repo = None
            else:
                raise

    def _get_repo(self) -> GitRepo:
        """Lazy-init the local git clone of the dashboard repo."""
        if self._repo is None:
            self._repo = GitRepo(DASHBOARD_DIR, DASHBOARD_REPO_NAME)
            self._repo.init()
        else:
            self._repo.pull_latest()
        return self._repo
