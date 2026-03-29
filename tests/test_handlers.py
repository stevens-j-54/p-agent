"""Tests for tools.handlers — tool routing and GitHub/workspace integration."""

import json

from tools.handlers import handle_create_branch, handle_tool_call


class _FakeGitHub:
    def __init__(self, create_ok=True):
        self.create_ok = create_ok
        self.create_calls = []

    def create_branch(self, repo_name, branch_name, from_branch):
        self.create_calls.append((repo_name, branch_name, from_branch))
        if self.create_ok:
            return {"success": True, "message": "created"}
        return {"success": False, "error": "api error"}


class _FakeWorkspace:
    def __init__(self, checkout_ok=True):
        self.checkout_ok = checkout_ok

    def checkout_branch(self, branch_name):
        if self.checkout_ok:
            return {"success": True}
        return {"success": False, "error": "checkout failed"}


def test_handle_tool_call_create_branch_passes_get_workspace():
    gh = _FakeGitHub()
    workspaces = {}

    def get_workspace(name):
        if name not in workspaces:
            workspaces[name] = _FakeWorkspace()
        return workspaces[name]

    out = handle_tool_call(
        "create_branch",
        {"repo_name": "p-agent", "branch_name": "feat/test", "from_branch": "main"},
        {"github": gh, "get_workspace": get_workspace, "agent_core": None},
    )
    data = json.loads(out)
    assert data.get("success") is True
    assert gh.create_calls == [("p-agent", "feat/test", "main")]


def test_handle_create_branch_without_workspace_skips_checkout():
    gh = _FakeGitHub()
    out = handle_create_branch(
        gh,
        "p-agent",
        "feat/solo",
        "main",
        get_workspace=None,
    )
    data = json.loads(out)
    assert data.get("success") is True
    assert "checkout_warning" in data


def test_handle_create_branch_with_workspace_checks_out():
    gh = _FakeGitHub()
    ws = _FakeWorkspace()

    def get_workspace(name):
        assert name == "p-agent"
        return ws

    out = handle_create_branch(
        gh,
        "p-agent",
        "feat/x",
        "main",
        get_workspace=get_workspace,
    )
    data = json.loads(out)
    assert data.get("success") is True
    assert "checkout_warning" not in data
