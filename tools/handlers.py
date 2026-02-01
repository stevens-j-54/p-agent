"""
Tool Handlers
"""

import json

def handle_save_document(workspace, file_path: str, content: str) -> str:
    """Handle the save_document tool call."""
    print(f"    -> Saving document: {file_path}")
    result = workspace.save_document(
        file_path=file_path,
        content=content
    )
    if not result.get("success"):
        print(f"    !! Error: {result.get('error')}")
    return json.dumps(result)


def handle_commit_and_push(workspace, commit_message: str) -> str:
    """Handle the commit_and_push tool call."""
    print(f"    -> Committing and pushing: {commit_message}")
    result = workspace.commit_and_push(
        commit_message=commit_message
    )
    if result.get("success"):
        print(f"    -> {result.get('action')}: {result.get('message')}")
    else:
        print(f"    !! Error: {result.get('error')}")
    return json.dumps(result)


def handle_list_documents(workspace) -> str:
    """Handle the list_documents tool call."""
    print(f"    -> Listing documents")
    result = workspace.list_documents()
    return json.dumps(result)


def handle_tool_call(tool_name: str, tool_input: dict, services: dict) -> str:
    """
    Route a tool call to its handler.
    
    Args:
        tool_name: Name of the tool to call
        tool_input: Parameters for the tool
        services: Dict of available services (workspace, memory, etc.)
    """
    workspace = services.get("workspace")
    
    if tool_name == "save_document":
        return handle_save_document(
            workspace,
            file_path=tool_input["file_path"],
            content=tool_input["content"]
        )
    
    elif tool_name == "commit_and_push":
        return handle_commit_and_push(
            workspace,
            commit_message=tool_input["commit_message"]
        )
    
    elif tool_name == "list_documents":
        return handle_list_documents(workspace)
    
    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})