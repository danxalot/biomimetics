# -*- coding: utf-8 -*-
"""
MCP Tool Definitions for Gemini Multimodal Live API.
Contains function declarations for Email, GDrive, WhatsApp, ARCA, and HITL tools.
Synchronized with BiOS Omni Server (copaw_omni_mcp.py).
"""

EMAIL_TOOLS = [
    {
        "name": "read_recent_emails",
        "description": "Read recent emails from a ProtonMail or Gmail account. Returns a formatted summary of Subject, From, Date, and Body snippet.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "account": {
                    "type": "STRING",
                    "description": "The email address to check (e.g., 'dan.exall@pm.me', 'dan.exall@gmail.com')."
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Number of recent emails to fetch (default: 5, max: 50)."
                }
            },
            "required": ["account"]
        }
    },
    {
        "name": "send_email",
        "description": "Send an email from a ProtonMail or Gmail account.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "account": {
                    "type": "STRING",
                    "description": "The sender email address (must be a configured account)."
                },
                "to": {
                    "type": "STRING",
                    "description": "The recipient's email address."
                },
                "subject": {
                    "type": "STRING",
                    "description": "Email subject line."
                },
                "body": {
                    "type": "STRING",
                    "description": "The main content of the email."
                }
            },
            "required": ["account", "to", "subject", "body"]
        }
    },
    {
        "name": "read_email",
        "description": "Read a specific email's full body content by its ID.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "account": {
                    "type": "STRING",
                    "description": "The email address to check."
                },
                "email_id": {
                    "type": "STRING",
                    "description": "The IMAP message ID of the email (obtained from read_recent_emails)."
                }
            },
            "required": ["account", "email_id"]
        }
    }
]

GDRIVE_TOOLS = [
    {
        "name": "search_gdrive",
        "description": "Search for files in Google Drive vault (Obsidian-life). Returns names and IDs.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search query."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_gdrive_file",
        "description": "Read the content of a file from Google Drive (e.g. Obsidian vault).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_id": {"type": "STRING", "description": "The File ID."}
            },
            "required": ["file_id"]
        }
    },
    {
        "name": "write_gdrive_file",
        "description": "Create or update a file in Google Drive vault.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "description": "Filename."},
                "content": {"type": "STRING", "description": "File content."},
                "parent_id": {"type": "STRING", "description": "Optional parent folder ID."}
            },
            "required": ["name", "content"]
        }
    }
]

WHATSAPP_TOOLS = [
    {
        "name": "send_whatsapp",
        "description": "Send a WhatsApp message via Green API. Phone format: 1234567890 (no +).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "to_phone": {"type": "STRING", "description": "Recipient phone number."},
                "message": {"type": "STRING", "description": "Message content."}
            },
            "required": ["to_phone", "message"]
        }
    },
    {
        "name": "analyze_whatsapp_image",
        "description": "Analyze an image received via WhatsApp using Gemini Vision.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_id": {"type": "STRING", "description": "The WhatsApp fileId."},
                "prompt": {"type": "STRING", "description": "Analysis prompt."}
            },
            "required": ["file_id"]
        }
    }
]

ARCA_TOOLS = [
    {
        "name": "get_universal_context",
        "description": "Retrieve specialized context frame around a subject (Service, Code, Workflow) from the Holographic Context Graph. Yields a 4-layer graph.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "subject": {"type": "STRING", "description": "Subject to query (e.g. 'agent_service')."},
                "radius": {"type": "INTEGER", "description": "Graph traversal depth (default 4)."}
            },
            "required": ["subject"]
        }
    },
    {
        "name": "search_arca",
        "description": "Search the ARCA semantic knowledge base for technical documentation and system history.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search query."}
            },
            "required": ["query"]
        }
    }
]

OPENCODE_TOOLS = [
    {
        "name": "execute_opencode_task",
        "description": "Dispatch a coding or technical task to an OpenCode agent (the local Serena code agent runs it on a free OpenCode model). Use this to control opencode agents: write code, refactor, plan, or reason over the codebase. Returns the agent's response.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target_model": {
                    "type": "STRING",
                    "description": "OpenCode model to run the task. Verified working: 'deepseek-v4-pro'. Also available: 'kimi-2.6'. Default to 'deepseek-v4-pro' if unsure."
                },
                "task_brief": {
                    "type": "STRING",
                    "description": "Clear, self-contained description of the task for the opencode agent to execute."
                },
                "technical_context": {
                    "type": "STRING",
                    "description": "Optional supporting context (file paths, constraints, prior decisions)."
                }
            },
            "required": ["target_model", "task_brief"]
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file from the local filesystem.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Absolute path to the file."}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file on the local filesystem. Creates directories if needed.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Absolute path to the destination file."},
                "content": {"type": "STRING", "description": "The text content to write."}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_files",
        "description": "List the contents of a directory.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "directory": {"type": "STRING", "description": "Absolute path to the directory."}
            },
            "required": ["directory"]
        }
    },
    {
        "name": "move_file",
        "description": "Move or rename a file on the local filesystem.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "src": {"type": "STRING", "description": "Absolute path to the source file."},
                "dest": {"type": "STRING", "description": "Absolute path to the destination."}
            },
            "required": ["src", "dest"]
        }
    }
]

CORE_RELAY_TOOLS = [
    {
        "name": "render_canvas",
        "description": "Render an HTML page on the user's local macOS screen via the CoPaw HUD canvas.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "html": {"type": "STRING", "description": "HTML content to render. Can be a full document or just the body content."},
            },
            "required": ["html"]
        }
    },
    {
        "name": "query_memory",
        "description": "Query the unified memory system (GCP Memory Orchestrator).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "The search query."},
                "limit": {"type": "INTEGER", "description": "Max results."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "memorize",
        "description": "Store structured context into the long-term cognitive layer (GCP Memory Orchestrator).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "content": {"type": "STRING", "description": "Information to store."},
                "source": {"type": "STRING", "description": "Source of information."},
                "tags": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Tags."}
            },
            "required": ["content"]
        }
    }
]

PROJECT_MGMT_TOOLS = [
    {
        "name": "dispatch_pm_brief",
        "description": "Record a new engineering requirement or project goal. Creates a GitHub issue and Notion task.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Clear title for the issue/task."},
                "description": {"type": "STRING", "description": "Detailed engineering brief."},
                "repo": {"type": "STRING", "description": "GitHub repository (owner/repo format)."}
            },
            "required": ["title", "description"]
        }
    },
    {
        "name": "update_notion_task_status",
        "description": "Update the status of a Notion task.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id": {"type": "STRING", "description": "The Notion page/task ID."},
                "status": {"type": "STRING", "description": "Status name (e.g. 'Ready for Dev')."}
            },
            "required": ["task_id", "status"]
        }
    },
    {
        "name": "search_notion_tasks",
        "description": "Search for tasks in the Notion project database by title.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search text to filter tasks by title."},
                "database_id": {"type": "STRING", "description": "Optional specific Notion database ID."}
            },
            "required": []
        }
    },
    {
        "name": "create_notion_task",
        "description": "Create a new task in the Notion project database.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Task title."},
                "description": {"type": "STRING", "description": "Optional task description."},
                "database_id": {"type": "STRING", "description": "Optional Notion database ID."}
            },
            "required": ["title"]
        }
    },
    {
        "name": "create_github_issue",
        "description": "Create a new GitHub issue in the project repository.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Issue title."},
                "body": {"type": "STRING", "description": "Issue body/description."},
                "repo": {"type": "STRING", "description": "GitHub repository (owner/repo format)."}
            },
            "required": ["title", "body"]
        }
    }
]

HITL_TOOLS = [
    {
        "name": "get_pending_approvals",
        "description": "Check for outstanding tool execution requests requiring approval.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "session_id": {"type": "STRING", "description": "Current session ID."}
            },
            "required": ["session_id"]
        }
    },
    {
        "name": "approve_tool_request",
        "description": "Approve or Deny a pending tool execution (HITL).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request_id": {"type": "STRING", "description": "The request ID."},
                "decision": {"type": "STRING", "enum": ["approved", "denied"], "description": "Decision."}
            },
            "required": ["request_id", "decision"]
        }
    }
]

COMPUTER_USE_TOOLS = [
    {
        "name": "take_screenshot",
        "description": "Capture a screenshot of the primary monitor.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "format": {
                    "type": "STRING",
                    "enum": ["base64", "file"],
                    "description": "Output format."
                }
            }
        }
    },
    {
        "name": "mouse_click",
        "description": "Click the mouse at specific screen coordinates (0-1000).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "x": {"type": "INTEGER", "description": "X coordinate."},
                "y": {"type": "INTEGER", "description": "Y coordinate."},
                "button": {"type": "STRING", "enum": ["left", "right", "middle"]},
                "clicks": {"type": "INTEGER"}
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "mouse_move",
        "description": "Move the mouse cursor to specific coordinates (0-1000).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "x": {"type": "INTEGER"},
                "y": {"type": "INTEGER"},
                "duration": {"type": "NUMBER"}
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "keyboard_type",
        "description": "Type text into the active window.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING"},
                "interval": {"type": "NUMBER"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "keyboard_press",
        "description": "Press a specific key (e.g. 'enter', 'esc').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {"type": "STRING"}
            },
            "required": ["key"]
        }
    }
]

def get_all_declarations():
    """Return all active function declarations for the Gemini setup message."""
    return (
        EMAIL_TOOLS +
        GDRIVE_TOOLS +
        WHATSAPP_TOOLS +
        ARCA_TOOLS +
        OPENCODE_TOOLS +
        CORE_RELAY_TOOLS +
        PROJECT_MGMT_TOOLS +
        HITL_TOOLS +
        COMPUTER_USE_TOOLS
    )
