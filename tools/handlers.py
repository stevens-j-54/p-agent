"""
Tool Handlers
"""

import json
import logging

logger = logging.getLogger(__name__)


# --- Workspace handlers ---

def handle_save_document(get_workspace, repo_name: str, file_path: str, content: str) -> str:
    logger.info("[%s] Saving document: %s", repo_name, file_path)
    result = get_workspace(repo_name).save_document(file_path=file_path, content=content)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_read_document(get_workspace, repo_name: str, file_path: str) -> str:
    logger.info("[%s] Reading document: %s", repo_name, file_path)
    result = get_workspace(repo_name).read_document(file_path=file_path)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_delete_document(get_workspace, repo_name: str, file_path: str) -> str:
    logger.info("[%s] Deleting document: %s", repo_name, file_path)
    result = get_workspace(repo_name).delete_document(file_path=file_path)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_delete_folder(get_workspace, repo_name: str, folder_path: str, force: bool = False) -> str:
    logger.info("[%s] Deleting folder: %s (force=%s)", repo_name, folder_path, force)
    result = get_workspace(repo_name).delete_folder(folder_path=folder_path, force=force)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_rename_document(get_workspace, repo_name: str, old_path: str, new_path: str) -> str:
    logger.info("[%s] Renaming document: %s -> %s", repo_name, old_path, new_path)
    result = get_workspace(repo_name).rename_document(old_path=old_path, new_path=new_path)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_create_folder(get_workspace, repo_name: str, folder_path: str) -> str:
    logger.info("[%s] Creating folder: %s", repo_name, folder_path)
    result = get_workspace(repo_name).create_folder(folder_path=folder_path)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_commit_and_push(get_workspace, repo_name: str, commit_message: str) -> str:
    logger.info("[%s] Committing: %s", repo_name, commit_message)
    result = get_workspace(repo_name).commit_and_push(commit_message=commit_message)
    if result.get("success"):
        logger.info("%s: %s", result.get('action'), result.get('message'))
    else:
        logger.error("Commit failed: %s", result.get('error'))
    return json.dumps(result)


def handle_examine_workspace(get_workspace, repo_name: str) -> str:
    logger.info("[%s] Examining workspace", repo_name)
    result = get_workspace(repo_name).examine_workspace()
    return json.dumps(result)


# --- GitHub admin handlers ---

def handle_list_repos(github) -> str:
    logger.info("Listing GitHub repos")
    result = github.list_repos()
    return json.dumps(result)


def handle_create_repo(github, get_workspace, name: str, description: str = "", private: bool = True) -> str:
    logger.info("Creating GitHub repo: %s", name)
    result = github.create_repo(name=name, description=description, private=private)
    if result.get("success"):
        # Immediately initialise a local workspace for the new repo
        logger.info("Initialising local workspace for: %s", name)
        try:
            get_workspace(name)
        except Exception as e:
            logger.warning("Repo created but workspace init failed: %s", e)
            result["workspace_warning"] = f"Repo created but workspace init failed: {e}"
    else:
        logger.error("Failed to create repo: %s", result.get('error'))
    return json.dumps(result)


def handle_delete_repo(github, repo_name: str, confirm: bool = False) -> str:
    logger.info("Deleting GitHub repo: %s (confirm=%s)", repo_name, confirm)
    result = github.delete_repo(repo_name=repo_name, confirm=confirm)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_create_issue(github, repo_name: str, title: str, body: str) -> str:
    logger.info("[%s] Creating issue: %s", repo_name, title)
    result = github.create_issue(repo_name=repo_name, title=title, body=body)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_create_branch(
    github,
    repo_name: str,
    branch_name: str,
    from_branch: str = "main",
    *,
    get_workspace=None,
) -> str:
    """Create branch on GitHub, then check out locally when get_workspace is provided."""
    logger.info("[%s] Creating branch: %s from %s", repo_name, branch_name, from_branch)
    result = github.create_branch(repo_name=repo_name, branch_name=branch_name, from_branch=from_branch)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
        return json.dumps(result)
    if get_workspace is None:
        logger.warning("[%s] No get_workspace; skipping local checkout for %s", repo_name, branch_name)
        result["checkout_warning"] = "Local workspace unavailable; branch exists on GitHub only."
        return json.dumps(result)
    # Check out the new branch locally so subsequent commits go to the right place
    logger.info("[%s] Checking out branch locally: %s", repo_name, branch_name)
    checkout_result = get_workspace(repo_name).checkout_branch(branch_name)
    if not checkout_result.get("success"):
        logger.warning("[%s] Branch created on GitHub but local checkout failed: %s",
                       repo_name, checkout_result.get('error'))
        result["checkout_warning"] = checkout_result.get("error")
    return json.dumps(result)


def handle_merge_branch(github, repo_name: str, head_branch: str,
                        base_branch: str = "main", commit_message: str = "") -> str:
    logger.info("[%s] Merging branch: %s -> %s", repo_name, head_branch, base_branch)
    result = github.merge_branch(
        repo_name=repo_name,
        head_branch=head_branch,
        base_branch=base_branch,
        commit_message=commit_message
    )
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_create_pull_request(github, repo_name: str, title: str, body: str,
                               head_branch: str, base_branch: str = "main") -> str:
    logger.info("[%s] Creating PR: %s", repo_name, title)
    result = github.create_pull_request(
        repo_name=repo_name, title=title, body=body,
        head_branch=head_branch, base_branch=base_branch
    )
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_check_ci_status(github, repo_name: str, branch_name: str) -> str:
    logger.info("[%s] Checking CI status for branch: %s", repo_name, branch_name)
    result = github.check_ci_status(repo_name=repo_name, branch_name=branch_name)
    if result.get("passed"):
        logger.info("CI passed for %s/%s", repo_name, branch_name)
    elif result.get("success"):
        logger.warning("CI failed for %s/%s: %s", repo_name, branch_name,
                       result.get("failed_steps"))
    return json.dumps(result)


def handle_open_upstream_pr(github, title: str, body: str,
                            branch_name: str, base_branch: str = "main") -> str:
    logger.info("Opening upstream PR: %s (branch: %s)", title, branch_name)
    result = github.open_upstream_pr(
        title=title,
        body=body,
        branch_name=branch_name,
        base_branch=base_branch
    )
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


# --- Fetch handler ---

def handle_fetch_url(fetch, url: str) -> str:
    logger.info("Fetching URL: %s", url)
    result = fetch.fetch_url(url=url)
    if not result.get("success"):
        logger.error("Fetch error: %s", result.get('error'))
    return json.dumps(result)


# --- Agent-core handlers ---

def handle_list_agent_core(agent_core) -> str:
    logger.info("Listing agent-core files")
    result = agent_core.list_files()
    return json.dumps(result)


def handle_read_agent_core(agent_core, file_path: str) -> str:
    logger.info("Reading agent-core file: %s", file_path)
    result = agent_core.read_file(file_path)
    return json.dumps(result)


def handle_create_agent_core(agent_core, file_path: str, content: str, commit_message: str) -> str:
    logger.info("Creating agent-core file: %s", file_path)
    result = agent_core.upsert_file(file_path=file_path, content=content, commit_message=commit_message)
    return json.dumps(result)


def handle_update_memory(agent_core, content: str, commit_message: str) -> str:
    logger.info("Updating memory: %s", commit_message)
    result = agent_core.upsert_file(file_path="MEMORY.md", content=content, commit_message=commit_message)
    return json.dumps(result)


def handle_update_agent_core(agent_core, file_path: str, content: str, commit_message: str) -> str:
    logger.info("Updating agent-core file: %s", file_path)
    result = agent_core.upsert_file(file_path=file_path, content=content, commit_message=commit_message)
    return json.dumps(result)


# --- Router ---

def handle_tool_call(tool_name: str, tool_input: dict, services: dict) -> str:
    """Route a tool call to its handler via dispatch table."""
    gw = services.get("get_workspace")
    gh = services.get("github")
    ac = services.get("agent_core")
    ft = services.get("fetch")
    rn = tool_input.get("repo_name", "workspace")  # default repo for workspace tools

    dispatch = {
        # Workspace
        "save_document":    lambda: handle_save_document(gw, rn, tool_input["file_path"], tool_input["content"]),
        "read_document":    lambda: handle_read_document(gw, rn, tool_input["file_path"]),
        "delete_document":  lambda: handle_delete_document(gw, rn, tool_input["file_path"]),
        "delete_folder":    lambda: handle_delete_folder(gw, rn, tool_input["folder_path"], tool_input.get("force", False)),
        "rename_document":  lambda: handle_rename_document(gw, rn, tool_input["old_path"], tool_input["new_path"]),
        "create_folder":    lambda: handle_create_folder(gw, rn, tool_input["folder_path"]),
        "commit_and_push":  lambda: handle_commit_and_push(gw, rn, tool_input["commit_message"]),
        "examine_workspace": lambda: handle_examine_workspace(gw, rn),
        # GitHub
        "list_repos":       lambda: handle_list_repos(gh),
        "create_repo":      lambda: handle_create_repo(gh, gw, tool_input["name"], tool_input.get("description", ""), tool_input.get("private", True)),
        "delete_repo":      lambda: handle_delete_repo(gh, tool_input["repo_name"], tool_input.get("confirm", False)),
        "create_issue":     lambda: handle_create_issue(gh, tool_input["repo_name"], tool_input["title"], tool_input["body"]),
        "create_branch":    lambda: handle_create_branch(
            gh,
            tool_input["repo_name"],
            tool_input["branch_name"],
            tool_input.get("from_branch", "main"),
            get_workspace=gw,
        ),
        "merge_branch":     lambda: handle_merge_branch(gh, tool_input["repo_name"], tool_input["head_branch"], tool_input.get("base_branch", "main"), tool_input.get("commit_message", "")),
        "create_pull_request": lambda: handle_create_pull_request(gh, tool_input["repo_name"], tool_input["title"], tool_input["body"], tool_input["head_branch"], tool_input.get("base_branch", "main")),
        "check_ci_status":  lambda: handle_check_ci_status(gh, tool_input["repo_name"], tool_input["branch_name"]),
        "open_upstream_pr": lambda: handle_open_upstream_pr(gh, tool_input["title"], tool_input["body"], tool_input["branch_name"], tool_input.get("base_branch", "main")),
        # Fetch
        "fetch_url":        lambda: handle_fetch_url(ft, tool_input["url"]),
        # Agent-core
        "list_agent_core":  lambda: handle_list_agent_core(ac),
        "read_agent_core":  lambda: handle_read_agent_core(ac, tool_input["file_path"]),
        "create_agent_core": lambda: handle_create_agent_core(ac, tool_input["file_path"], tool_input["content"], tool_input["commit_message"]),
        "update_memory":    lambda: handle_update_memory(ac, tool_input["content"], tool_input["commit_message"]),
        "update_agent_core": lambda: handle_update_agent_core(ac, tool_input["file_path"], tool_input["content"], tool_input["commit_message"]),
    }

    handler = dispatch.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    return handler()
