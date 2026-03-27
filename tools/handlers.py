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


def handle_create_issue(github, repo_name: str, title: str, body: str) -> str:
    logger.info("[%s] Creating issue: %s", repo_name, title)
    result = github.create_issue(repo_name=repo_name, title=title, body=body)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
    return json.dumps(result)


def handle_create_branch(github, get_workspace, repo_name: str, branch_name: str, from_branch: str = "main") -> str:
    logger.info("[%s] Creating branch: %s from %s", repo_name, branch_name, from_branch)
    result = github.create_branch(repo_name=repo_name, branch_name=branch_name, from_branch=from_branch)
    if not result.get("success"):
        logger.error("Tool error: %s", result.get('error'))
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
    result = agent_core.create_file(
        file_path=file_path,
        content=content,
        commit_message=commit_message
    )
    return json.dumps(result)


def handle_update_memory(agent_core, content: str, commit_message: str) -> str:
    logger.info("Updating memory: %s", commit_message)
    result = agent_core.update_file(
        file_path="MEMORY.md",
        content=content,
        commit_message=commit_message
    )
    return json.dumps(result)


def handle_update_agent_core(agent_core, file_path: str, content: str, commit_message: str) -> str:
    logger.info("Updating agent-core file: %s", file_path)
    result = agent_core.update_file(
        file_path=file_path,
        content=content,
        commit_message=commit_message
    )
    return json.dumps(result)


# --- Router ---

def handle_tool_call(tool_name: str, tool_input: dict, services: dict) -> str:
    """Route a tool call to its handler."""
    get_workspace = services.get("get_workspace")
    github = services.get("github")
    agent_core = services.get("agent_core")

    # Default repo_name for workspace tools
    repo_name = tool_input.get("repo_name", "workspace")

    if tool_name == "save_document":
        return handle_save_document(get_workspace, repo_name,
                                    file_path=tool_input["file_path"],
                                    content=tool_input["content"])

    elif tool_name == "read_document":
        return handle_read_document(get_workspace, repo_name,
                                    file_path=tool_input["file_path"])

    elif tool_name == "delete_document":
        return handle_delete_document(get_workspace, repo_name,
                                      file_path=tool_input["file_path"])

    elif tool_name == "delete_folder":
        return handle_delete_folder(get_workspace, repo_name,
                                    folder_path=tool_input["folder_path"],
                                    force=tool_input.get("force", False))

    elif tool_name == "rename_document":
        return handle_rename_document(get_workspace, repo_name,
                                      old_path=tool_input["old_path"],
                                      new_path=tool_input["new_path"])

    elif tool_name == "create_folder":
        return handle_create_folder(get_workspace, repo_name,
                                    folder_path=tool_input["folder_path"])

    elif tool_name == "commit_and_push":
        return handle_commit_and_push(get_workspace, repo_name,
                                      commit_message=tool_input["commit_message"])

    elif tool_name == "examine_workspace":
        return handle_examine_workspace(get_workspace, repo_name)

    elif tool_name == "list_repos":
        return handle_list_repos(github)

    elif tool_name == "create_repo":
        return handle_create_repo(github, get_workspace,
                                  name=tool_input["name"],
                                  description=tool_input.get("description", ""),
                                  private=tool_input.get("private", True))

    elif tool_name == "create_issue":
        return handle_create_issue(github,
                                   repo_name=tool_input["repo_name"],
                                   title=tool_input["title"],
                                   body=tool_input["body"])

    elif tool_name == "create_branch":
        return handle_create_branch(github, get_workspace,
                                    repo_name=tool_input["repo_name"],
                                    branch_name=tool_input["branch_name"],
                                    from_branch=tool_input.get("from_branch", "main"))

    elif tool_name == "merge_branch":
        return handle_merge_branch(github,
                                   repo_name=tool_input["repo_name"],
                                   head_branch=tool_input["head_branch"],
                                   base_branch=tool_input.get("base_branch", "main"),
                                   commit_message=tool_input.get("commit_message", ""))

    elif tool_name == "create_pull_request":
        return handle_create_pull_request(github,
                                          repo_name=tool_input["repo_name"],
                                          title=tool_input["title"],
                                          body=tool_input["body"],
                                          head_branch=tool_input["head_branch"],
                                          base_branch=tool_input.get("base_branch", "main"))

    elif tool_name == "open_upstream_pr":
        return handle_open_upstream_pr(github,
                                       title=tool_input["title"],
                                       body=tool_input["body"],
                                       branch_name=tool_input["branch_name"],
                                       base_branch=tool_input.get("base_branch", "main"))

    elif tool_name == "list_agent_core":
        return handle_list_agent_core(agent_core)

    elif tool_name == "read_agent_core":
        return handle_read_agent_core(agent_core, file_path=tool_input["file_path"])

    elif tool_name == "create_agent_core":
        return handle_create_agent_core(agent_core,
                                        file_path=tool_input["file_path"],
                                        content=tool_input["content"],
                                        commit_message=tool_input["commit_message"])

    elif tool_name == "update_memory":
        return handle_update_memory(agent_core,
                                    content=tool_input["content"],
                                    commit_message=tool_input["commit_message"])

    elif tool_name == "update_agent_core":
        return handle_update_agent_core(agent_core,
                                        file_path=tool_input["file_path"],
                                        content=tool_input["content"],
                                        commit_message=tool_input["commit_message"])

    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
