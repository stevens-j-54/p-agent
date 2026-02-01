"""
Tool definitions
"""

TOOLS = [
    {
        "name": "save_document",
        "description": "Save a document to the local workspace. Use this when asked to write, draft, create, or prepare any document. The document will be saved locally - use commit_and_push afterwards to push changes to the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path where the file should be saved relative to workspace root, e.g., 'notes/meeting-summary.md' or 'drafts/blog-post.md'. Use lowercase, hyphens, and .md or .txt extension."
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
        "name": "delete_document",
        "description": "Delete a document from the workspace. Use commit_and_push afterwards to push the deletion to the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to delete, e.g., 'drafts/old-draft.md'"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "commit_and_push",
        "description": "Commit all current changes in the workspace and push to the GitHub repository. Use this after saving documents to make them available to your employer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "commit_message": {
                    "type": "string",
                    "description": "A clear, professional commit message describing the changes."
                }
            },
            "required": ["commit_message"]
        }
    },
    {
        "name": "list_documents",
        "description": "List all documents currently in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]