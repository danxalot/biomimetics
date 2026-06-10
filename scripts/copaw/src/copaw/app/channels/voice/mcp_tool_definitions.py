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
        "name": "serena_analyze_code",
        "description": "Analyze code for semantic meaning and potential refactoring via Serena.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "code": {"type": "STRING", "description": "Code to analyze"},
                "context": {"type": "STRING", "description": "Optional context for analysis"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "serena_refactor_suggestion",
        "description": "Suggest refactoring for a specific goal via Serena.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "code": {"type": "STRING", "description": "Code to refactor"},
                "goal": {"type": "STRING", "description": "Refactoring goal"}
            },
            "required": ["code", "goal"]
        }
    },
    {
        "name": "serena_semantic_diff",
        "description": "Analyze the semantic impact of code changes (diff) via Serena.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "diff_content": {"type": "STRING", "description": "The git diff or code change"},
                "context": {"type": "STRING", "description": "Additional context (e.g. commit message)"}
            },
            "required": ["diff_content"]
        }
    },
    {
        "name": "serena_security_scan",
        "description": "Scan code or config for security vulnerabilities via Serena.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "content": {"type": "STRING", "description": "Code or config to scan"},
                "context": {"type": "STRING", "description": "Context (e.g. filename, environment)"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "serena_chat",
        "description": "General interaction with Serena for architectural reasoning and task dispatch.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt": {"type": "STRING", "description": "Message or instruction"},
                "context": {"type": "STRING", "description": "Context (JSON string or text)"}
            },
            "required": ["prompt"]
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

CORE_RELAY_TOOLS = [
    {
        "name": "render_canvas",
        "description": "Render visual components (HTML or Markdown) in the CoPaw HUD.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "view": {"type": "STRING", "description": "View type (email, research, task, status)."},
                "content": {"type": "STRING", "description": "HTML or Markdown content."}
            },
            "required": ["view", "content"]
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
                "repo": {"type": "STRING", "description": "GitHub repository."}
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
        CORE_RELAY_TOOLS + 
        PROJECT_MGMT_TOOLS + 
        HITL_TOOLS +
        COMPUTER_USE_TOOLS
    )
