"""
Unit tests for SchedulerService.

Uses a lightweight mock for agent_core so no git operations are performed.
SchedulerService is loaded directly from its module file to avoid triggering
services/__init__.py, which imports EmailService (and therefore google-auth).
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

# Load scheduler module without triggering services/__init__.py
_spec = importlib.util.spec_from_file_location(
    "services.scheduler",
    Path(__file__).parent.parent / "services" / "scheduler.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["services.scheduler"] = _mod
_spec.loader.exec_module(_mod)
SchedulerService = _mod.SchedulerService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scheduler(tasks=None):
    """Return a SchedulerService with a mocked agent_core."""
    agent_core = MagicMock()
    # read_file returns an empty schedule by default
    if tasks is None:
        agent_core.read_file.return_value = {"success": False, "error": "not found"}
    else:
        agent_core.read_file.return_value = {
            "success": True,
            "content": json.dumps({"tasks": tasks}),
        }
    agent_core.upsert_file.return_value = {"success": True}
    sched = SchedulerService(agent_core)
    sched.load_tasks()
    return sched


def _past_dt(seconds=60):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _future_dt(seconds=3600):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_get_due_tasks_returns_overdue():
    task = {
        "id": "aaa",
        "name": "Past task",
        "type": "recurring",
        "cron": "* * * * *",
        "run_at": None,
        "instruction": "run_hn_digest",
        "instruction_type": "skill",
        "next_run": _past_dt(120),
        "last_run": None,
        "created_at": _past_dt(3600),
        "status": "active",
    }
    sched = _make_scheduler([task])
    due = sched.get_due_tasks()
    assert len(due) == 1
    assert due[0]["id"] == "aaa"


def test_get_due_tasks_skips_future():
    task = {
        "id": "bbb",
        "name": "Future task",
        "type": "one_time",
        "cron": None,
        "run_at": _future_dt(7200),
        "instruction": "send me a report",
        "instruction_type": "natural_language",
        "next_run": _future_dt(7200),
        "last_run": None,
        "created_at": _past_dt(60),
        "status": "active",
    }
    sched = _make_scheduler([task])
    due = sched.get_due_tasks()
    assert due == []


def test_get_due_tasks_skips_completed():
    task = {
        "id": "ccc",
        "name": "Done task",
        "type": "one_time",
        "cron": None,
        "run_at": _past_dt(3600),
        "instruction": "do something",
        "instruction_type": "natural_language",
        "next_run": _past_dt(3600),
        "last_run": _past_dt(3600),
        "created_at": _past_dt(7200),
        "status": "completed",
    }
    sched = _make_scheduler([task])
    due = sched.get_due_tasks()
    assert due == []


def test_mark_complete_recurring_advances_next_run():
    task = {
        "id": "ddd",
        "name": "Recurring",
        "type": "recurring",
        "cron": "0 9 * * *",
        "run_at": None,
        "instruction": "run_hn_digest",
        "instruction_type": "skill",
        "next_run": _past_dt(60),
        "last_run": None,
        "created_at": _past_dt(3600),
        "status": "active",
    }
    sched = _make_scheduler([task])
    before_next = sched.list_tasks()[0]["next_run"]
    sched.mark_task_complete("ddd")
    after = sched.list_tasks()[0]
    # Status stays active for recurring tasks
    assert after["status"] == "active"
    # last_run should now be set
    assert after["last_run"] is not None
    # next_run should have moved forward
    assert after["next_run"] != before_next
    # next_run should be in the future
    next_dt = datetime.fromisoformat(after["next_run"])
    assert next_dt > datetime.now(timezone.utc)


def test_mark_complete_one_time_sets_completed():
    task = {
        "id": "eee",
        "name": "One-time",
        "type": "one_time",
        "cron": None,
        "run_at": _past_dt(60),
        "instruction": "write me a haiku",
        "instruction_type": "natural_language",
        "next_run": _past_dt(60),
        "last_run": None,
        "created_at": _past_dt(3600),
        "status": "active",
    }
    sched = _make_scheduler([task])
    sched.mark_task_complete("eee")
    after = sched.list_tasks()[0]
    assert after["status"] == "completed"
    assert after["last_run"] is not None


def test_add_task_assigns_id_and_next_run():
    sched = _make_scheduler()
    result = sched.add_task({
        "name": "Daily digest",
        "type": "recurring",
        "cron": "0 9 * * 1-5",
        "instruction": "run_hn_digest",
        "instruction_type": "skill",
    })
    assert result["success"] is True
    task = result["task"]
    assert task["id"]  # non-empty UUID
    assert task["next_run"]  # calculated
    next_dt = datetime.fromisoformat(task["next_run"])
    assert next_dt > datetime.now(timezone.utc)
    assert len(sched.list_tasks()) == 1


def test_add_task_one_time_requires_run_at():
    sched = _make_scheduler()
    result = sched.add_task({
        "name": "Missing run_at",
        "type": "one_time",
        "instruction": "do something",
        "instruction_type": "natural_language",
        # run_at intentionally omitted
    })
    assert result["success"] is False
    assert "run_at" in result["error"]


def test_add_task_recurring_requires_cron():
    sched = _make_scheduler()
    result = sched.add_task({
        "name": "Missing cron",
        "type": "recurring",
        "instruction": "run_hn_digest",
        "instruction_type": "skill",
        # cron intentionally omitted
    })
    assert result["success"] is False
    assert "cron" in result["error"]


def test_remove_task():
    task = {
        "id": "fff",
        "name": "To remove",
        "type": "one_time",
        "cron": None,
        "run_at": _future_dt(3600),
        "instruction": "do nothing",
        "instruction_type": "natural_language",
        "next_run": _future_dt(3600),
        "last_run": None,
        "created_at": _past_dt(60),
        "status": "active",
    }
    sched = _make_scheduler([task])
    assert len(sched.list_tasks()) == 1
    result = sched.remove_task("fff")
    assert result["success"] is True
    assert len(sched.list_tasks()) == 0


def test_remove_task_not_found():
    sched = _make_scheduler()
    result = sched.remove_task("nonexistent-id")
    assert result["success"] is False
    assert "No task found" in result["error"]
