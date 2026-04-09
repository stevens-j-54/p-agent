# Task Scheduling and a Self-Updating Dashboard

*April 2026*

---

Until now, the agent was purely reactive. It woke up only when someone sent it a message — an email or a Telegram message — ran Claude, produced a reply, and went back to sleep. That model works well for on-demand tasks, but it has an obvious gap: there's no way to say "do this every morning at nine" or "remind me about X on a specific date." You'd have to manually trigger it each time.

This document covers the design and implementation of two related features added to address that:

1. **Task scheduling** — recurring and one-time tasks, stored persistently and checked on every poll cycle
2. **A self-updating dashboard** — a static GitHub Pages site that reflects the current schedule, rebuilt and pushed automatically whenever the schedule changes

---

## Why these two things together

The scheduling feature needed a way to present the task list to the user without them having to ask the agent. Email or Telegram would work for notifications, but for a live view of what's scheduled — especially useful when you want to see everything at once — a webpage is the right medium.

The challenge is cost. The agent already pays (in time and API credits) for every Claude call it makes. If regenerating the dashboard required Claude to think about it, the overhead would compound every time a task was added or completed. The solution is to make the dashboard entirely separate from Claude's reasoning loop: pure Python, no API calls, just reading a JSON file and writing HTML.

---

## Architecture overview

```
agent-core/SCHEDULES.json      ← persisted task store
      │
      ├── SchedulerService     ← loads/saves tasks, checks what's due
      │         │
      │         └── polling loop in agent.py (every 10s)
      │                   │
      │            execute_scheduled_task()
      │            ├── skill tasks → Python function, no Claude
      │            └── NL tasks → _run_claude() with lean prompt
      │
      └── DashboardSkill       ← reads SCHEDULES.json → generates HTML → git push
                │
         stevens-j-54/stevens-j-54.github.io (GitHub Pages)
```

Everything that touches scheduling flows through `SchedulerService`. Everything that touches the dashboard flows through `DashboardSkill`. The two services are deliberately not coupled to each other — the agent connects them from the outside.

---

## Storing tasks

Tasks live in `agent-core/SCHEDULES.json`. The agent-core repo already stores the agent's identity, memory, and Telegram session history, so it was the natural place to put scheduled tasks too: version-controlled, pushed to GitHub on every change, and automatically present on startup.

A task looks like this:

```json
{
  "id": "c3f1a2b4-...",
  "name": "Morning HN Digest",
  "type": "recurring",
  "cron": "0 9 * * 1-5",
  "run_at": null,
  "instruction": "run_hn_digest",
  "instruction_type": "skill",
  "next_run": "2026-04-10T09:00:00+00:00",
  "last_run": "2026-04-09T09:00:00+00:00",
  "created_at": "2026-04-01T10:00:00+00:00",
  "status": "active"
}
```

Two task types:

- **`recurring`** — a standard five-field cron expression, interpreted in UTC. Uses the `croniter` library to calculate the next scheduled run time. The expression `0 9 * * 1-5` fires at 09:00 UTC on weekdays.
- **`one_time`** — a specific ISO 8601 UTC datetime. Once the task fires, its status becomes `completed`.

Two instruction types:

- **`skill`** — the instruction field is the name of a registered Python skill (e.g. `"run_hn_digest"`). The skill is called directly as a Python function. No Claude API call is made.
- **`natural_language`** — the instruction field is a plain-English description of what to do. When the task fires, Claude is called with a lean system prompt to follow the instruction.

The distinction between instruction types is the main credit-control mechanism. If you want the agent to run the HN digest every morning, that's a skill call — zero extra cost beyond the Python execution. If you want it to draft a weekly summary of something and Telegram it to you, that goes through Claude but with a minimal prompt designed to keep token count low.

---

## SchedulerService

`services/scheduler.py` is a straightforward class with five public methods:

```python
class SchedulerService:
    def load_tasks(self) -> list[dict]
    def list_tasks(self) -> list[dict]
    def get_due_tasks(self) -> list[dict]
    def add_task(self, task_input: dict) -> dict
    def remove_task(self, task_id: str) -> dict
    def mark_task_complete(self, task_id: str) -> None
```

`get_due_tasks()` is the hot path — called on every polling cycle. It filters tasks where `status == "active"` and `next_run <= datetime.now(UTC)`. The comparison is done in UTC throughout; the stored datetimes are always timezone-aware ISO 8601 strings.

`mark_task_complete()` handles the two task types differently:

```python
if task["type"] == "recurring":
    task["last_run"] = now.isoformat()
    task["next_run"] = croniter(cron, now).get_next(datetime).isoformat()
else:
    task["last_run"] = now.isoformat()
    task["status"] = "completed"
```

For recurring tasks, `next_run` is computed from the current time, not from the previous scheduled time. This is a deliberate choice: if the agent was offline when a task was due, the next run is calculated from now rather than trying to catch up on missed slots. One backfill on startup, one advancement forward — no cascading reruns.

Every mutation persists immediately:

```python
def _persist(self, commit_message: str) -> None:
    content = json.dumps({"tasks": self._tasks}, indent=2)
    self.agent_core.upsert_file(SCHEDULES_FILE, content, commit_message)
```

`upsert_file` writes the file, commits it, and pushes — the same path used for memory updates and Telegram session state. If the process crashes after a task runs but before `mark_task_complete` is persisted, the task will re-run on the next startup. That's acceptable given the kinds of tasks this is designed to run; nothing here is write-once critical.

### Validation

`add_task()` validates before writing:

- `recurring` tasks require a valid `cron` field. `croniter` raises `CroniterBadCronError` on malformed expressions, which is caught and returned as a structured error.
- `one_time` tasks require a `run_at` field that can be parsed as a datetime.
- `skill` tasks are checked against the set of known skill names (`KNOWN_SKILLS = {"run_hn_digest"}`). An unknown skill name would silently fail at runtime, so it's better to reject it at creation time.

---

## Integrating with the polling loop

The main `while True:` loop in `agent.py` already checked for emails and Telegram messages every 10 seconds. The scheduler check runs after both of those:

```python
# --- Scheduler ---
if agent.scheduler:
    due_tasks = agent.scheduler.get_due_tasks()
    for task in due_tasks:
        logger.info("Running scheduled task: %s (id=%s)", task["name"], task["id"])
        try:
            result = agent.execute_scheduled_task(task)
            agent.scheduler.mark_task_complete(task["id"])
            agent.dashboard_skill.update()
            if TELEGRAM_OWNER_CHAT_ID and agent.telegram_service:
                msg = f"Scheduled task complete: {task['name']}\n\n{result}"
                agent.telegram_service.send_message(TELEGRAM_OWNER_CHAT_ID, msg)
        except Exception as task_err:
            logger.error("Scheduled task '%s' failed: %s", task["name"], task_err, exc_info=True)
```

The order matters: `mark_task_complete` and `dashboard_skill.update()` are called even if sending the Telegram notification fails. The task result is always persisted before any notification attempt.

Each due task is processed synchronously. The loop does not spin up threads or a task queue. Given the expected volume (a handful of scheduled tasks), this is appropriate — adding concurrency would introduce state management complexity without meaningful benefit.

### Executing tasks

`execute_scheduled_task()` branches on `instruction_type`:

```python
def execute_scheduled_task(self, task: dict) -> str:
    if task["instruction_type"] == "skill":
        skill = self._skills.get(task["instruction"])
        if not skill:
            return f"Unknown skill: {task['instruction']}"
        result = skill.run()
        return json.dumps(result)
    else:
        system_prompt = self._build_scheduled_task_prompt()
        messages = [{"role": "user", "content": task["instruction"]}]
        return self._run_claude(messages, system_prompt)
```

The lean system prompt for natural-language tasks:

```python
def _build_scheduled_task_prompt(self) -> str:
    identity = _load_file("IDENTITY.md", DEFAULT_IDENTITY)
    soul = _load_file("SOUL.md", DEFAULT_SOUL)
    memory = _load_file("MEMORY.md", DEFAULT_MEMORY)
    return (
        f"{identity}\n\n---\n\n{soul}\n\n---\n\n## Memory\n\n{memory}\n\n---\n\n"
        "You are running a scheduled task. Complete the instruction below and respond with the result."
    )
```

This excludes the full CAPABILITIES section — the part that describes workspace tools, codebase workflow, and the self-modification procedure. A scheduled natural-language task is unlikely to need any of that, and including it would add hundreds of tokens to every invocation. The agent still has its identity, values, and memory, so it can produce coherent output, but it isn't tempted to start modifying files or opening pull requests.

---

## Three new tools

To let the agent manage its own schedule through conversation, three tools were added:

**`add_scheduled_task`** — the main creation tool. The schema captures both task types with conditional required fields:

```json
{
  "name": "add_scheduled_task",
  "input_schema": {
    "properties": {
      "name":             { "type": "string" },
      "type":             { "enum": ["recurring", "one_time"] },
      "cron":             { "type": "string" },
      "run_at":           { "type": "string" },
      "instruction":      { "type": "string" },
      "instruction_type": { "enum": ["skill", "natural_language"] }
    },
    "required": ["name", "type", "instruction", "instruction_type"]
  }
}
```

Neither `cron` nor `run_at` is marked required at the JSON Schema level because which one is needed depends on `type`. The validation is handled in `SchedulerService.add_task()` instead, which can return a descriptive error message based on the combination of values.

**`remove_scheduled_task`** — takes a task ID and removes it.

**`list_scheduled_tasks`** — returns the full task list. Intended to be called before a removal, so the user or agent can identify the right ID.

When any scheduling tool succeeds, the handler calls `dashboard.update()` immediately before returning, so the dashboard is always in sync with what the tool confirms.

---

## The dashboard

`skills/dashboard.py` is the only piece in the system that has no Claude involvement whatsoever.

### GitHub Pages

The dashboard is published to `stevens-j-54/stevens-j-54.github.io`. GitHub treats any repository named `<username>.github.io` specially: the `main` branch root is automatically served as a static site at `https://<username>.github.io`. No configuration required — create the repo, push an `index.html`, and the page is live.

`DashboardSkill._ensure_repo_exists()` uses PyGithub to create the repo the first time `update()` is called, with `auto_init=True` so there's an initial commit to clone. After that, it's just a standard `GitRepo` clone — the same base class used for the workspace, agent-core, and the p-agent fork.

### HTML generation

`generate_html()` produces a single self-contained `index.html`. No build step, no framework, no JavaScript dependencies. Just a Python f-string with embedded CSS:

```python
def generate_html(self, tasks: list) -> str:
    recurring = [t for t in tasks if t.get("type") == "recurring" and t.get("status") != "completed"]
    one_time  = [t for t in tasks if t.get("type") == "one_time"  and t.get("status") != "completed"]
    completed = [t for t in tasks if t.get("status") == "completed"]
    # ... render tables ...
```

Three sections: recurring tasks, upcoming one-time tasks, completed tasks. Each row shows the name, schedule (cron expression or datetime), next run, last run, instruction type, and status. The page includes `<meta http-equiv="refresh" content="60">` to auto-reload every minute, so if you leave it open it stays current.

The visual style is a GitHub-dark-inspired palette with no external dependencies — no Google Fonts, no CDN. This was intentional: the page needs to load reliably regardless of network state, and there's nothing dynamic enough to justify JavaScript.

### Pushing without noise

`commit_and_push()` in the base `GitRepo` class checks for actual changes before committing:

```python
status = self._run_git(["status", "--porcelain"])
if not status.stdout.strip():
    return {"success": True, "action": "no_changes", "message": "No changes to commit."}
```

This means calling `dashboard.update()` after every scheduled task run doesn't create a commit if the HTML is identical (which it will be if the only change was a `last_run` timestamp that rounds to the same minute). In practice, task completions do change `last_run` and `next_run`, so most updates do produce a commit — but the guard prevents noise in the edge cases.

---

## Credit accounting

The table below summarises the API cost of each operation:

| Operation | Claude calls | Notes |
|---|---|---|
| User asks to add a task (Telegram/email) | 1 | Normal conversation call |
| `add_scheduled_task` tool executes | 0 | Python only |
| Dashboard update after add | 0 | Python only |
| Skill task fires (e.g. `run_hn_digest`) | 0 | Python only |
| Natural-language task fires | 1 | Lean prompt: ~500–800 tokens system prompt vs. ~2,000 for full prompt |
| Dashboard update after completion | 0 | Python only |
| Telegram completion notification | 0 | Direct API call |

The natural-language task path does cost credits, but the lean prompt reduces the fixed overhead by roughly 60% compared to a full conversation call. The skill path costs nothing extra at runtime — the Python function is called directly and the result is returned as a string.

---

## What this enables

With scheduling in place, a user can now say to the agent over Telegram:

> "Run the HN digest every weekday at 09:00 UTC"

The agent calls `add_scheduled_task` with `type=recurring`, `cron="0 9 * * 1-5"`, `instruction="run_hn_digest"`, `instruction_type="skill"`. From that point forward, the agent runs the digest independently every morning without any human input, notifies via Telegram when it's done, and keeps the dashboard up to date. The user can check the schedule at any time by visiting the GitHub Pages URL, or by asking the agent to `list_scheduled_tasks`.

One-time tasks work the same way:

> "On 13 April at 09:00 UTC, send me a reminder to review the Q2 budget"

The agent creates a `one_time` task with `instruction_type="natural_language"`. On that date, the agent wakes up, notices the task is due, calls Claude with the lean prompt, generates a Telegram message, marks the task complete, and updates the dashboard.

---

## Files changed

| File | Change |
|---|---|
| `services/scheduler.py` | New. `SchedulerService` with full CRUD and cron scheduling |
| `skills/dashboard.py` | New. `DashboardSkill` — pure-Python HTML generation and push |
| `tests/test_scheduler.py` | New. 10 unit tests for `SchedulerService` |
| `agent.py` | `init_scheduler`, `init_dashboard`, `execute_scheduled_task`, `_build_scheduled_task_prompt`, scheduler check block in polling loop |
| `tools/definitions.py` | 3 new tools: `add_scheduled_task`, `remove_scheduled_task`, `list_scheduled_tasks` |
| `tools/handlers.py` | Handlers for 3 new tools; `scheduler` and `dashboard` added to services dict |
| `prompts/system.py` | Scheduling section added to CAPABILITIES |
| `config.py` | `TELEGRAM_OWNER_CHAT_ID`, `DASHBOARD_REPO_NAME`, `DASHBOARD_DIR` |
| `pyproject.toml` | `croniter>=1.3.8` dependency |
| `services/__init__.py` | Export `SchedulerService` |
| `skills/__init__.py` | Export `DashboardSkill` |

New environment variable: `TELEGRAM_OWNER_CHAT_ID` — the Telegram chat ID to notify when scheduled tasks complete. If unset, tasks run silently.
