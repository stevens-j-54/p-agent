"""
Tool definitions
"""

REPO_NAME_PARAM = {
    "repo_name": {
        "type": "string",
        "description": "Name of the repository to work in. Defaults to 'workspace'. Use the short name (e.g. 'workspace', 'my-project'), not the full GitHub path."
    }
}

TOOLS = [
    {
        "name": "save_document",
        "description": "Save a document to a repository workspace. Use this when asked to write, draft, create, or prepare any document. Use commit_and_push afterwards to push changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                **REPO_NAME_PARAM,
                "file_path": {
                    "type": "string",
                    "description": "Path where the file should be saved relative to the repo root, e.g., 'notes/meeting-summary.md'. Use lowercase, hyphens, and .md or .txt extension."
                },
                "content": {
                    "type": "string",
                    "description": "The full content of the document to save."
                }
            },
            "required": ["file_path", "content"]
        }
    },
    {
        "name": "read_document",
        "description": "Read the contents of a document from a repository workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                **REPO_NAME_PARAM,
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read, e.g., 'notes/meeting-summary.md'"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "delete_document",
        "description": "Delete a document from a repository workspace. Use commit_and_push afterwards.",
        "input_schema": {
            "type": "object",
            "properties": {
                **REPO_NAME_PARAM,
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to delete, e.g., 'drafts/old-draft.md'"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "delete_folder",
        "description": "Delete a folder from a repository workspace. By default only deletes empty folders. Set force=true to delete with all contents. Use commit_and_push afterwards.",
        "input_schema": {
            "type": "object",
            "properties": {
                **REPO_NAME_PARAM,
                "folder_path": {
                    "type": "string",
                    "description": "Path to the folder to delete, e.g., 'drafts/old-project'"
                },
                "force": {
                    "type": "boolean",
                    "description": "If true, delete folder even if not empty. Default is false.",
                    "default": False
                }
            },
            "required": ["folder_path"]
        }
    },
    {
        "name": "rename_document",
        "description": "Rename or move a document within a repository workspace. Use commit_and_push afterwards.",
        "input_schema": {
            "type": "object",
            "properties": {
                **REPO_NAME_PARAM,
                "old_path": {
                    "type": "string",
                    "description": "Current path of the file, e.g., 'drafts/old-name.md'"
                },
                "new_path": {
                    "type": "string",
                    "description": "New path for the file, e.g., 'published/new-name.md'"
                }
            },
            "required": ["old_path", "new_path"]
        }
    },
    {
        "name": "create_folder",
        "description": "Create a new folder in a repository workspace. Use commit_and_push afterwards.",
        "input_schema": {
            "type": "object",
            "properties": {
                **REPO_NAME_PARAM,
                "folder_path": {
                    "type": "string",
                    "description": "Path for the new folder, e.g., 'projects/new-project'"
                }
            },
            "required": ["folder_path"]
        }
    },
    {
        "name": "commit_and_push",
        "description": "Commit all current changes in a repository workspace and push to GitHub.",
        "input_schema": {
            "type": "object",
            "properties": {
                **REPO_NAME_PARAM,
                "commit_message": {
                    "type": "string",
                    "description": "A clear commit message describing the changes."
                }
            },
            "required": ["commit_message"]
        }
    },
    {
        "name": "examine_workspace",
        "description": "Examine the file structure of a repository workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                **REPO_NAME_PARAM,
            },
            "required": []
        }
    },
    # --- GitHub admin tools ---
    {
        "name": "list_repos",
        "description": "List all GitHub repositories on the account.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "create_repo",
        "description": "Create a new GitHub repository and initialise a local workspace for it. Use this when you need a new dedicated space for a project or body of work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Repository name. Lowercase, hyphens, no spaces. E.g. 'research-notes', 'client-briefs'."
                },
                "description": {
                    "type": "string",
                    "description": "A short description of what this repository is for."
                },
                "private": {
                    "type": "boolean",
                    "description": "Whether the repository should be private. Defaults to true.",
                    "default": True
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "create_issue",
        "description": "Create a GitHub issue in a repository. Useful for tracking tasks, bugs, or ideas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "Name of the repository to create the issue in, e.g. 'workspace'."
                },
                "title": {
                    "type": "string",
                    "description": "Issue title."
                },
                "body": {
                    "type": "string",
                    "description": "Issue body. Markdown supported."
                }
            },
            "required": ["repo_name", "title", "body"]
        }
    },
    {
        "name": "create_branch",
        "description": "Create a new branch in a repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "Name of the repository."
                },
                "branch_name": {
                    "type": "string",
                    "description": "Name for the new branch, e.g. 'feature/new-section'."
                },
                "from_branch": {
                    "type": "string",
                    "description": "Branch to create from. Defaults to 'main'.",
                    "default": "main"
                }
            },
            "required": ["repo_name", "branch_name"]
        }
    },
    {
        "name": "merge_branch",
        "description": "Merge a branch into a base branch in a repository. Use this to merge feature branches into main on our own fork. Do NOT use this to merge into the upstream repository — use open_upstream_pr for that.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "Name of the repository."
                },
                "head_branch": {
                    "type": "string",
                    "description": "The branch to merge in (the source branch)."
                },
                "base_branch": {
                    "type": "string",
                    "description": "The branch to merge into. Defaults to 'main'.",
                    "default": "main"
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional commit message for the merge. If omitted, a default message is used."
                }
            },
            "required": ["repo_name", "head_branch"]
        }
    },
    {
        "name": "create_pull_request",
        "description": "Create a pull request in a repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "Name of the repository."
                },
                "title": {
                    "type": "string",
                    "description": "Pull request title."
                },
                "body": {
                    "type": "string",
                    "description": "Pull request description. Markdown supported."
                },
                "head_branch": {
                    "type": "string",
                    "description": "The branch containing the changes."
                },
                "base_branch": {
                    "type": "string",
                    "description": "The branch to merge into. Defaults to 'main'.",
                    "default": "main"
                }
            },
            "required": ["repo_name", "title", "body", "head_branch"]
        }
    },
    # --- Agent-core tools ---
    {
        "name": "list_agent_core",
        "description": "List all files in your agent-core configuration repository.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "read_agent_core",
        "description": "Read the contents of a file in your agent-core configuration repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read, e.g., 'IDENTITY.md'"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "create_agent_core",
        "description": "Create a new file in your agent-core configuration repository. Changes are committed and pushed immediately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path for the new file, e.g., 'preferences.md'"
                },
                "content": {
                    "type": "string",
                    "description": "The content for the new file"
                },
                "commit_message": {
                    "type": "string",
                    "description": "A clear commit message describing what this file is for"
                }
            },
            "required": ["file_path", "content", "commit_message"]
        }
    },
    {
        "name": "update_agent_core",
        "description": "Update an existing file in your agent-core configuration repository. Always read the current file first before updating.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to update, e.g., 'IDENTITY.md'"
                },
                "content": {
                    "type": "string",
                    "description": "The complete new content for the file"
                },
                "commit_message": {
                    "type": "string",
                    "description": "A clear commit message describing what changed and why"
                }
            },
            "required": ["file_path", "content", "commit_message"]
        }
    },
    {
        "name": "update_memory",
        "description": "Update your persistent memory (MEMORY.md). Use this at the end of a conversation to record anything worth remembering — preferences expressed, instructions given, useful context. Write the full updated content each time; this replaces the existing memory. Keep it concise.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The full updated content for MEMORY.md."
                },
                "commit_message": {
                    "type": "string",
                    "description": "A brief commit message describing what was added or changed."
                }
            },
            "required": ["content", "commit_message"]
        }
    }
]
