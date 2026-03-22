#!/usr/bin/env python3
"""
Copaw Webhook Receiver - Local API for Cloudflare Tunnel
Receives webhooks from Cloudflare, email daemon, and Obsidian sync
Forwards to GCP Cloud Function Gateway for memory storage

Tri-Factor Architecture:
- Voice: Gemini Live (frontend)
- Brain: MiniMax m2.7 via Kilo Code (complex reasoning)
- Hands/Vision: Local Qwen3.5-2B (UI actions, vision checks)
"""

import os
import json
import asyncio
import aiohttp
import httpx
from datetime import datetime
from aiohttp import web

# Configuration
GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
)
PORT = int(os.environ.get("PORT", "8000"))

# Tri-Factor Architecture Endpoints
BRAIN_URL = "https://api.kilo.ai/v1"
BRAIN_MODEL = "minimax-m2.7"
BRAIN_API_KEY = os.environ.get("KILO_CODE_API_KEY", "")

EXECUTION_URL = "http://localhost:11435/v1"
EXECUTION_MODEL = "qwen3.5-2b-instruct"

# Gmail API Configuration
GMAIL_CREDENTIALS_PATH = os.environ.get(
    "GMAIL_CREDENTIALS_PATH",
    os.path.expanduser("~/.copaw/gmail/credentials.json")
)
GMAIL_TOKEN_PATH = os.environ.get(
    "GMAIL_TOKEN_PATH",
    os.path.expanduser("~/.copaw/gmail/token.json")
)

# In-memory request log
request_log = []


async def route_to_brain(task: str, context: str = "") -> dict:
    """Route complex reasoning task to MiniMax m2.7 via Kilo Code
    
    This is the "Brain" component of the Tri-Factor architecture.
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BRAIN_API_KEY}"
        }
        
        payload = {
            "model": BRAIN_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are the reasoning engine of the CoPaw Tri-Factor system. Analyze the task and determine if local UI action or vision check is required. If so, include a special marker [LOCAL_ACTION_REQUIRED] with instructions."
                },
                {
                    "role": "user",
                    "content": f"Context: {context}\n\nTask: {task}"
                }
            ],
            "max_tokens": 2048,
            "temperature": 0.7
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                BRAIN_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                result = await resp.json()
                return {
                    "source": "brain",
                    "model": BRAIN_MODEL,
                    "response": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                    "raw": result
                }
    except Exception as e:
        return {
            "source": "brain",
            "error": str(e),
            "status": "brain_error"
        }


async def route_to_execution(prompt: str, image_base64: str = None) -> dict:
    """Route vision/UI action to local Qwen3.5-2B via Vulkan llama.cpp
    
    This is the "Hands/Vision" component of the Tri-Factor architecture.
    """
    try:
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "model": EXECUTION_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are the execution engine for local UI actions and vision tasks. Provide concise, actionable responses."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.3
        }
        
        # Add image if provided (for vision tasks)
        if image_base64:
            payload["messages"][1]["content"] = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
            ]
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{EXECUTION_URL}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                result = await resp.json()
                return {
                    "source": "execution",
                    "model": EXECUTION_MODEL,
                    "response": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                    "raw": result
                }
    except Exception as e:
        return {
            "source": "execution",
            "error": str(e),
            "status": "execution_error"
        }


async def process_tri_factor_request(task: str, context: str = "") -> dict:
    """Process a Tri-Factor routing request
    
    1. Send to Brain (MiniMax) for reasoning
    2. If Brain indicates local action needed, route to Execution (Qwen)
    3. Return final result
    """
    # Step 1: Route to Brain for complex reasoning
    brain_result = await route_to_brain(task, context)
    
    if "error" in brain_result:
        return brain_result
    
    brain_response = brain_result.get("response", "")
    
    # Step 2: Check if local action/vision is required
    if "[LOCAL_ACTION_REQUIRED]" in brain_response:
        # Extract instructions for local execution
        instructions = brain_response.split("[LOCAL_ACTION_REQUIRED]")[1].split("[/LOCAL_ACTION_REQUIRED]")[0] if "[/LOCAL_ACTION_REQUIRED]" in brain_response else brain_response
        
        # Step 3: Route to local execution
        execution_result = await route_to_execution(instructions)
        
        return {
            "status": "completed",
            "brain_response": brain_response,
            "execution_response": execution_result.get("response", ""),
            "tri_factor": True
        }
    
    # No local action needed - return brain response
    return {
        "status": "completed",
        "brain_response": brain_response,
        "tri_factor": True
    }


# ============================================================
# GMAIL INTEGRATION
# ============================================================

def get_gmail_service():
    """Get Gmail API service with OAuth2 authentication
    
    Setup Instructions for User:
    1. Go to https://console.cloud.google.com/
    2. Create a new project or select existing
    3. Enable Gmail API
    4. Create OAuth2 credentials (Desktop app)
    5. Download credentials.json to ~/.copaw/gmail/
    6. Run this script once to authorize (will open browser)
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.oauth2 import flow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        import os.path
        
        creds = None
        
        # Load existing token
        if os.path.exists(GMAIL_TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH)
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Need to run OAuth flow - return None to indicate auth needed
                return None, "OAuth authorization required. Run: python3 -m scripts.copaw.gmail_auth"
        
        # Build Gmail service
        service = build('gmail', 'v1', credentials=creds)
        return service, None
        
    except ImportError as e:
        return None, f"Missing Gmail dependencies: {e}. Run: pip3 install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client"
    except Exception as e:
        return None, f"Gmail API error: {str(e)}"


async def gmail_search(query: str, max_results: int = 5) -> dict:
    """Search Gmail for messages
    
    Args:
        query: Gmail search query (e.g., 'from:boss subject:meeting')
        max_results: Maximum number of results to return
    """
    service, error = get_gmail_service()
    if error:
        return {"error": error, "messages": []}
    
    try:
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        results_list = []
        
        for msg in messages:
            msg_detail = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'To', 'Subject', 'Date']
            ).execute()
            
            headers = msg_detail.get('payload', {}).get('headers', [])
            results_list.append({
                'id': msg['id'],
                'from': next((h['value'] for h in headers if h['name'] == 'From'), ''),
                'to': next((h['value'] for h in headers if h['name'] == 'To'), ''),
                'subject': next((h['value'] for h in headers if h['name'] == 'Subject'), ''),
                'date': next((h['value'] for h in headers if h['name'] == 'Date'), ''),
                'snippet': msg_detail.get('snippet', '')
            })
        
        return {"status": "success", "messages": results_list, "count": len(results_list)}
        
    except Exception as e:
        return {"error": str(e), "messages": []}


async def gmail_summarize(message_id: str) -> dict:
    """Get and summarize a Gmail message"""
    service, error = get_gmail_service()
    if error:
        return {"error": error}
    
    try:
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
        
        # Extract headers
        headers = message.get('payload', {}).get('headers', [])
        email_data = {
            'from': next((h['value'] for h in headers if h['name'] == 'From'), ''),
            'to': next((h['value'] for h in headers if h['name'] == 'To'), ''),
            'subject': next((h['value'] for h in headers if h['name'] == 'Subject'), ''),
            'date': next((h['value'] for h in headers if h['name'] == 'Date'), ''),
        }
        
        # Extract body
        body = ""
        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part:
                    import base64
                    body = base64.urlsafe_b64decode(part['data']).decode('utf-8')
                    break
        elif 'body' in message['payload'] and 'data' in message['payload']['body']:
            import base64
            body = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')
        
        # Route to MiniMax for summarization
        summary_result = await route_to_brain(
            task=f"Summarize this email concisely in 2-3 sentences:\n\nFrom: {email_data['from']}\nSubject: {email_data['subject']}\n\n{body}",
            context="Email summarization task"
        )
        
        return {
            "status": "success",
            "email": email_data,
            "body": body[:500] + "..." if len(body) > 500 else body,
            "summary": summary_result.get("response", "Summary unavailable")
        }
        
    except Exception as e:
        return {"error": str(e)}


async def gmail_draft(to: str, subject: str, body: str) -> dict:
    """Create a Gmail draft
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text
    """
    service, error = get_gmail_service()
    if error:
        return {"error": error}
    
    try:
        import base64
        from email.mime.text import MIMEText
        
        # Create message
        message = MIMEText(body)
        message['to'] = to
        message['from'] = 'me'
        message['subject'] = subject
        
        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        # Create draft
        draft = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw_message}}
        ).execute()
        
        return {
            "status": "success",
            "draft_id": draft['id'],
            "message": f"Draft created. Open Gmail to review and send.",
            "to": to,
            "subject": subject
        }
        
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# WHATSAPP INTEGRATION (AppleScript Bridge)
# ============================================================

async def whatsapp_send_message(contact: str, message: str) -> dict:
    """Send WhatsApp message via AppleScript (macOS only)
    
    Requires WhatsApp Desktop app to be installed and logged in.
    
    Args:
        contact: Contact name or phone number
        message: Message text to send
    """
    try:
        import subprocess
        
        # Escape quotes in message
        escaped_message = message.replace('"', '\\"')
        
        # AppleScript to send WhatsApp message
        applescript = f'''
        tell application "System Events"
            tell process "WhatsApp"
                activate
                delay 0.5
                
                -- Click new chat button
                click button 1 of group 1 of scroll area 1 of splitter group 1 of splitter group 1 of window 1
                
                delay 0.5
                
                -- Type contact name
                keystroke "{contact}"
                delay 0.5
                
                -- Press Enter to select contact
                key code 36
                
                delay 0.5
                
                -- Type message
                keystroke "{escaped_message}"
                
                -- Press Enter to send
                key code 36
            end tell
        end tell
        '''
        
        result = subprocess.run(
            ['osascript', '-e', applescript],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return {
                "status": "success",
                "message": f"WhatsApp message sent to {contact}",
                "contact": contact
            }
        else:
            return {
                "status": "error",
                "error": result.stderr,
                "message": "Failed to send WhatsApp message"
            }
            
    except subprocess.TimeoutExpired:
        return {"error": "AppleScript timeout - WhatsApp may not be responsive"}
    except FileNotFoundError:
        return {"error": "osascript not found - macOS only"}
    except Exception as e:
        return {"error": str(e)}


async def whatsapp_get_recent_messages(contact: str = None, limit: int = 5) -> dict:
    """Get recent WhatsApp messages via AppleScript
    
    Note: This is limited by what WhatsApp Desktop exposes via accessibility.
    For full message history, use WhatsApp's export feature.
    
    Args:
        contact: Optional contact name to filter
        limit: Maximum number of messages to retrieve
    """
    try:
        import subprocess
        
        applescript = '''
        tell application "System Events"
            tell process "WhatsApp"
                activate
                delay 0.5
                
                -- Try to get messages from current chat
                try
                    set messages_text to ""
                    tell scroll area 1 of splitter group 1 of splitter group 1 of window 1
                        set visible_elements to every static text
                        repeat with elem in visible_elements
                            set messages_text to messages_text & (value of elem) & "
"
                        end repeat
                    end tell
                    return messages_text
                on error
                    return "No messages accessible"
                end try
            end tell
        end tell
        '''
        
        result = subprocess.run(
            ['osascript', '-e', applescript],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode == 0:
            messages = result.stdout.strip().split('\n')[-limit:]
            return {
                "status": "success",
                "messages": messages,
                "count": len(messages)
            }
        else:
            return {
                "status": "error",
                "error": result.stderr,
                "messages": []
            }
            
    except subprocess.TimeoutExpired:
        return {"error": "AppleScript timeout", "messages": []}
    except Exception as e:
        return {"error": str(e), "messages": []}


async def handle_gmail_request(action: str, params: dict) -> dict:
    """Handle Gmail-related requests
    
    Actions: search, summarize, draft
    """
    if action == "search":
        query = params.get("query", "")
        max_results = params.get("max_results", 5)
        return await gmail_search(query, max_results)
    
    elif action == "summarize":
        message_id = params.get("message_id")
        if not message_id:
            return {"error": "message_id required"}
        return await gmail_summarize(message_id)
    
    elif action == "draft":
        to = params.get("to", "")
        subject = params.get("subject", "")
        body = params.get("body", "")
        if not all([to, subject, body]):
            return {"error": "Missing required fields: to, subject, body"}
        return await gmail_draft(to, subject, body)
    
    else:
        return {"error": f"Unknown Gmail action: {action}"}


async def handle_whatsapp_request(action: str, params: dict) -> dict:
    """Handle WhatsApp-related requests
    
    Actions: send, get_recent
    """
    if action == "send":
        contact = params.get("contact", "")
        message = params.get("message", "")
        if not all([contact, message]):
            return {"error": "Missing required fields: contact, message"}
        return await whatsapp_send_message(contact, message)
    
    elif action == "get_recent":
        contact = params.get("contact")
        limit = params.get("limit", 5)
        return await whatsapp_get_recent_messages(contact, limit)
    
    else:
        return {"error": f"Unknown WhatsApp action: {action}"}


async def forward_to_gateway(payload: dict) -> dict:
    """Forward payload to GCP Cloud Function Gateway"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GCP_GATEWAY_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                return await resp.json()
    except Exception as e:
        return {"error": str(e), "status": "gateway_error"}


async def handle_webhook(request: web.Request) -> web.Response:
    """Handle generic webhook from Cloudflare/external sources

    Tri-Factor Routing:
    - type: 'brain_delegate' -> Route to MiniMax (Brain) -> Local Qwen (Execution) if needed
    - type: 'gmail' -> Handle Gmail actions (search, summarize, draft)
    - type: 'whatsapp' -> Handle WhatsApp actions (send, get_recent)
    - default -> Forward to GCP Gateway for memory storage
    """
    try:
        payload = await request.json()
    except:
        payload = await request.post()
        payload = dict(payload)

    # Check for Tri-Factor brain delegation
    if payload.get("type") == "brain_delegate":
        task = payload.get("task", "")
        context = payload.get("context", "")

        # Process through Tri-Factor routing
        result = await process_tri_factor_request(task, context)

        request_log.append({
            "type": "tri_factor_brain",
            "time": datetime.now().isoformat(),
            "task": task[:100] + "..." if len(task) > 100 else task,
            "result": result
        })

        return web.json_response({
            "status": "processed",
            "routing": "tri_factor",
            "result": result
        })

    # Handle Gmail actions
    if payload.get("type") == "gmail":
        action = payload.get("action", "")
        params = payload.get("params", {})
        
        result = await handle_gmail_request(action, params)
        
        request_log.append({
            "type": "gmail",
            "time": datetime.now().isoformat(),
            "action": action,
            "result": result
        })
        
        return web.json_response({
            "status": "processed",
            "service": "gmail",
            "result": result
        })

    # Handle WhatsApp actions
    if payload.get("type") == "whatsapp":
        action = payload.get("action", "")
        params = payload.get("params", {})
        
        result = await handle_whatsapp_request(action, params)
        
        request_log.append({
            "type": "whatsapp",
            "time": datetime.now().isoformat(),
            "action": action,
            "result": result
        })
        
        return web.json_response({
            "status": "processed",
            "service": "whatsapp",
            "result": result
        })

    # Add metadata for standard webhooks
    payload["metadata"] = payload.get("metadata", {})
    payload["metadata"]["source"] = "webhook"
    payload["metadata"]["received_at"] = datetime.now().isoformat()
    payload["metadata"]["remote_addr"] = request.remote

    # Forward to gateway
    result = await forward_to_gateway({
        "operation": "memorize",
        "content": json.dumps(payload),
        "metadata": payload["metadata"]
    })

    request_log.append({
        "type": "webhook",
        "time": datetime.now().isoformat(),
        "result": result
    })

    return web.json_response({"status": "received", "gateway_result": result})


async def handle_email(request: web.Request) -> web.Response:
    """Handle email ingestion from email daemon"""
    try:
        data = await request.json()
    except:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    # Extract email content
    subject = data.get("subject", "No Subject")
    body = data.get("body", "")
    sender = data.get("from", "unknown")
    
    # Format for memory storage
    email_content = f"Email from {sender}\nSubject: {subject}\n\n{body}"
    
    # Forward to gateway
    result = await forward_to_gateway({
        "operation": "memorize",
        "content": email_content,
        "metadata": {
            "source": "email",
            "from": sender,
            "subject": subject,
            "received_at": datetime.now().isoformat()
        }
    })
    
    # Also send to Notion tracking (if configured)
    notion_result = None
    if os.environ.get("NOTION_API_KEY"):
        notion_result = await send_to_notion({
            "type": "email",
            "from": sender,
            "subject": subject,
            "received_at": datetime.now().isoformat()
        })
    
    request_log.append({
        "type": "email",
        "time": datetime.now().isoformat(),
        "sender": sender,
        "subject": subject,
        "result": result
    })
    
    return web.json_response({
        "status": "received",
        "gateway_result": result,
        "notion_result": notion_result
    })


async def handle_obsidian(request: web.Request) -> web.Response:
    """Handle Obsidian markdown sync"""
    try:
        data = await request.json()
    except:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    filename = data.get("filename", "unknown.md")
    content = data.get("content", "")
    path = data.get("path", filename)
    
    # Format for memory storage
    markdown_content = f"# {filename}\n\nPath: {path}\n\n{content}"
    
    # Forward to gateway
    result = await forward_to_gateway({
        "operation": "memorize",
        "content": markdown_content,
        "metadata": {
            "source": "obsidian",
            "filename": filename,
            "path": path,
            "synced_at": datetime.now().isoformat()
        }
    })
    
    request_log.append({
        "type": "obsidian",
        "time": datetime.now().isoformat(),
        "filename": filename,
        "result": result
    })
    
    return web.json_response({"status": "synced", "gateway_result": result})


async def handle_notion(request: web.Request) -> web.Response:
    """Handle Notion webhook actions from Cloudflare Worker
    
    Routes specific Notion actions to Copaw Skills for multi-step workflows.
    """
    try:
        data = await request.json()
    except:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    # Extract action and data
    action = data.get("action", "")
    source_data = data.get("data", {})
    notion_payload = data.get("notion_payload", {})
    
    # Verify source
    source = data.get("source", "")
    if source != "notion":
        return web.json_response(
            {"error": "Invalid source - must be 'notion'"},
            status=400
        )
    
    # Route to appropriate Copaw Skill
    skill_result = None
    
    if action == "notion_page_updated":
        # Trigger: Page updated in Notion database
        # Skill: Analyze page content, extract action items, update memory
        skill_result = await trigger_copaw_skill(
            skill_name="analyze_notion_page",
            input_data={
                "page_id": source_data.get("page_id"),
                "title": source_data.get("title"),
                "properties": source_data.get("properties"),
                "url": source_data.get("url")
            }
        )
    
    elif action == "notion_comment_added":
        # Trigger: Comment added to Notion page/block
        # Skill: Process comment, check if requires action, add to memory
        skill_result = await trigger_copaw_skill(
            skill_name="process_notion_comment",
            input_data={
                "comment_id": source_data.get("comment_id"),
                "rich_text": source_data.get("rich_text"),
                "page_id": source_data.get("page_id"),
                "created_by": source_data.get("created_by")
            }
        )
    
    elif action == "notion_button_pressed":
        # Trigger: Database button pressed
        # Skill: Execute button-specific workflow
        button_action = source_data.get("button_action", "")
        skill_result = await trigger_copaw_skill(
            skill_name=f"button_{button_action}",
            input_data={
                "page_id": source_data.get("page_id"),
                "database_id": source_data.get("database_id"),
                "button_action": button_action
            }
        )
    
    elif action == "plan_feature":
        # Trigger: "Plan Feature" button pressed in Notion
        # Skill: Multi-step feature planning workflow
        skill_result = await trigger_copaw_skill(
            skill_name="plan_feature",
            input_data={
                "page_id": source_data.get("page_id"),
                "title": source_data.get("title"),
                "description": source_data.get("description"),
                "requirements": source_data.get("requirements", [])
            }
        )
    
    elif action == "review_code":
        # Trigger: "Review Code" button pressed
        # Skill: Code review workflow
        skill_result = await trigger_copaw_skill(
            skill_name="review_code",
            input_data={
                "page_id": source_data.get("page_id"),
                "code_snippet": source_data.get("code_snippet"),
                "review_criteria": source_data.get("review_criteria", [])
            }
        )
    
    elif action == "summarize_meeting":
        # Trigger: "Summarize Meeting" button pressed
        # Skill: Meeting notes summarization
        skill_result = await trigger_copaw_skill(
            skill_name="summarize_meeting",
            input_data={
                "page_id": source_data.get("page_id"),
                "meeting_notes": source_data.get("meeting_notes"),
                "attendees": source_data.get("attendees", [])
            }
        )
    
    else:
        # Unknown action - store in memory for later processing
        skill_result = await forward_to_gateway({
            "operation": "memorize",
            "content": f"Notion action: {action}\nData: {json.dumps(source_data)}",
            "metadata": {
                "source": "notion",
                "action": action,
                "received_at": datetime.now().isoformat()
            }
        })
    
    request_log.append({
        "type": "notion",
        "time": datetime.now().isoformat(),
        "action": action,
        "skill_result": skill_result
    })
    
    return web.json_response({
        "status": "processed",
        "action": action,
        "skill_result": skill_result
    })


async def trigger_copaw_skill(skill_name: str, input_data: dict) -> dict:
    """Trigger a Copaw Skill for processing
    
    This function would integrate with the actual Copaw/AgentScope framework.
    For now, it stores the request for later processing.
    """
    # In production, this would:
    # 1. Create a Copaw skill execution request
    # 2. Queue it for the agent to process
    # 3. Return a tracking ID
    
    # For now, store in memory and return acknowledgment
    skill_request = {
        "skill_name": skill_name,
        "input_data": input_data,
        "queued_at": datetime.now().isoformat(),
        "status": "queued"
    }
    
    # Store skill request for processing
    # (In production, this would use Copaw's skill queue)
    request_log.append({
        "type": "skill_request",
        "time": skill_request["queued_at"],
        "skill_name": skill_name,
        "input_data": input_data
    })
    
    # Also store in memory for context
    await forward_to_gateway({
        "operation": "memorize",
        "content": f"Skill triggered: {skill_name}\nInput: {json.dumps(input_data)}",
        "metadata": {
            "source": "notion_skill",
            "skill_name": skill_name,
            "triggered_at": skill_request["queued_at"]
        }
    })
    
    return {
        "status": "queued",
        "skill_name": skill_name,
        "message": f"Skill '{skill_name}' queued for execution"
    }


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint"""
    return web.json_response({
        "status": "healthy",
        "service": "copaw-webhook-receiver",
        "port": PORT,
        "gateway_url": GCP_GATEWAY_URL,
        "requests_logged": len(request_log)
    })


async def handle_logs(request: web.Request) -> web.Response:
    """Return recent request logs"""
    limit = int(request.query.get("limit", "50"))
    return web.json_response({
        "logs": request_log[-limit:],
        "total": len(request_log)
    })


async def send_to_notion(payload: dict) -> dict:
    """Send tracking entry to Notion database"""
    try:
        notion_api_key = os.environ.get("NOTION_API_KEY")
        notion_db_id = os.environ.get("NOTION_EMAIL_DB_ID")
        
        if not notion_api_key or not notion_db_id:
            return {"error": "Notion not configured"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {notion_api_key}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28"
                },
                json={
                    "parent": {"database_id": notion_db_id},
                    "properties": {
                        "Type": {"title": [{"text": {"content": payload.get("type", "email")}}]},
                        "From": {"rich_text": [{"text": {"content": payload.get("from", "")}}]},
                        "Subject": {"rich_text": [{"text": {"content": payload.get("subject", "")}}]},
                        "Received": {"date": {"start": payload.get("received_at", "")}}
                    }
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return await resp.json()
    except Exception as e:
        return {"error": str(e)}


def create_app() -> web.Application:
    """Create and configure the web application"""
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_post("/email", handle_email)
    app.router.add_post("/obsidian", handle_obsidian)
    app.router.add_post("/notion", handle_notion)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/logs", handle_logs)
    return app


if __name__ == "__main__":
    app = create_app()
    print(f"🚀 Copaw Webhook Receiver starting on port {PORT}")
    print(f"📡 Gateway: {GCP_GATEWAY_URL}")
    print(f"📧 Email endpoint: http://localhost:{PORT}/email")
    print(f"📝 Obsidian endpoint: http://localhost:{PORT}/obsidian")
    print(f"🔗 Webhook endpoint: http://localhost:{PORT}/webhook")
    web.run_app(app, host="0.0.0.0", port=PORT)
