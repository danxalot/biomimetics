#!/usr/bin/env python3
"""
Copaw Omni MCP Server - Consolidated Gateway for BiOS
Assimilates Gmail, GDrive, WhatsApp (Green API), and Memory Orchestrator.

Architecture:
- FastMCP framework for tool exposure.
- Credentials Server (8089) for runtime secret injection.
- Gmail/Proton for email operations.
- GDrive for file/vault operations.
- Green API for WhatsApp messaging.
- GCP Gateway for memory operations.
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.error
import imaplib
import smtplib
import ssl
import email
import re
import io
import datetime
from email.message import EmailMessage
from email.header import decode_header
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from mcp.server.fastmcp import FastMCP
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.credentials import Credentials

# =============================================================================
# Configuration & Constants
# =============================================================================

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("copaw_omni")

# Credentials Server
CREDENTIALS_API_KEY_PATH = "/Users/danexall/biomimetics/secrets/credentials_api_key"
CREDENTIALS_SERVER_URL = "http://localhost:8089"

# Email Configuration
PROTON_IMAP_HOST = "127.0.0.1"
PROTON_IMAP_PORT = 1143
PROTON_SMTP_HOST = "127.0.0.1"
PROTON_SMTP_PORT = 1025
GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587

EMAIL_ACCOUNTS = {
    "dan.exall@pm.me": {"type": "proton", "secret": "proton-bridge-password"},
    "dan@arca-vsa.tech": {"type": "proton", "secret": "proton-bridge-password"},
    "arca@arca-vsa.tech": {"type": "proton", "secret": "proton-bridge-password"},
    "dan.exall@gmail.com": {"type": "gmail", "secret": "gmail-app-password"},
}

# GDrive Configuration
VAULT_FOLDER_ID = "1odK6HEvTqdP8SX9h42EZKPLeQZFeXze7" # Obsidian-life

# Green API (WhatsApp)
GREEN_API_BASE_URL = "https://api.green-api.com"

# =============================================================================
# MCP Server Setup
# =============================================================================

mcp = FastMCP(
    "Copaw Omni Server",
    instructions="""
    Consolidated BiOS Gateway for Email, Google Drive, WhatsApp, and Memory.

    Capabilities:
    - Email: Read/Send via ProtonMail and Gmail.
    - Google Drive: Search, Read, Create, and Update files in 'Obsidian-life' vault.
    - WhatsApp: Send messages via Green API.
    - Memory: Query and Store semantic context via GCP Memory Orchestrator.

    All secrets are fetched securely from the Credentials Server at runtime.
    """,
)

# =============================================================================
# Secret Management
# =============================================================================

_api_key_cache = None

def get_credentials_api_key() -> str:
    global _api_key_cache
    if _api_key_cache:
        return _api_key_cache
    
    path = Path(CREDENTIALS_API_KEY_PATH)
    if path.exists():
        _api_key_cache = path.read_text().strip()
        return _api_key_cache
    raise FileNotFoundError(f"Credentials API key not found at {path}")

def fetch_secret(secret_name: str) -> str:
    """Fetch a secret from the Credentials Server."""
    api_key = get_credentials_api_key()
    
    req = urllib.request.Request(f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}")
    req.add_header("X-API-Key", api_key)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("value")
    except Exception as e:
        logger.error(f"Failed to fetch secret '{secret_name}': {e}")
        raise

# =============================================================================
# Email Tools
# =============================================================================

def decode_header_value(header_value: str) -> str:
    if not header_value: return ""
    decoded_parts = decode_header(header_value)
    result = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8", errors="ignore")
        else:
            result += str(part)
    return result

def extract_body(msg: email.message.Message) -> str:
    plain_text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                try:
                    charset = part.get_content_charset() or "utf-8"
                    plain_text += part.get_payload(decode=True).decode(charset, errors="replace")
                except: pass
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            plain_text = msg.get_payload(decode=True).decode(charset, errors="replace")
        except:
            plain_text = str(msg.get_payload())
    return plain_text.strip()

@mcp.tool()
def read_recent_emails(account: str, limit: int = 5) -> str:
    """Read recent emails from a ProtonMail or Gmail account."""
    if account not in EMAIL_ACCOUNTS:
        return f"Error: Unknown account {account}"
    
    try:
        password = fetch_secret(EMAIL_ACCOUNTS[account]["secret"])
        acc_type = EMAIL_ACCOUNTS[account]["type"]
        
        if acc_type == "gmail":
            mail = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
        else:
            mail = imaplib.IMAP4(PROTON_IMAP_HOST, PROTON_IMAP_PORT)
            mail.starttls()
            
        mail.login(account, password)
        mail.select("INBOX")
        
        status, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()
        recent_ids = email_ids[-limit:]
        
        results = []
        for eid in reversed(recent_ids):
            _, data = mail.fetch(eid, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            results.append(f"Subject: {decode_header_value(msg.get('Subject'))}\nFrom: {decode_header_value(msg.get('From'))}\nBody: {extract_body(msg)[:200]}...")
            
        mail.logout()
        return "\n---\n".join(results) or "No emails found."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def send_email(account: str, to: str, subject: str, body: str) -> str:
    """Send an email via ProtonMail or Gmail."""
    if account not in EMAIL_ACCOUNTS:
        return f"Error: Unknown account {account}"
    
    try:
        password = fetch_secret(EMAIL_ACCOUNTS[account]["secret"])
        acc_type = EMAIL_ACCOUNTS[account]["type"]
        
        msg = EmailMessage()
        msg["From"] = account
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        
        if acc_type == "gmail":
            server = smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT)
            server.starttls()
        else:
            server = smtplib.SMTP(PROTON_SMTP_HOST, PROTON_SMTP_PORT)
            server.starttls()
            
        server.login(account, password)
        server.send_message(msg)
        server.quit()
        return f"Email sent to {to}"
    except Exception as e:
        return f"Error: {e}"

# =============================================================================
# Google Drive Tools
# =============================================================================

def get_drive_service():
    token_json = fetch_secret("gdrive-oauth-token")
    token_data = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(token_data, scopes=['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=creds)

@mcp.tool()
def search_gdrive(query: str) -> str:
    """Search for files in the Obsidian-life vault on Google Drive."""
    try:
        service = get_drive_service()
        q = f"name contains '{query}' and '{VAULT_FOLDER_ID}' in parents and trashed = false"
        results = service.files().list(q=q, fields='files(id, name)').execute()
        files = results.get('files', [])
        if not files: return "No files found."
        return "\n".join([f"{f['name']} (ID: {f['id']})" for f in files])
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def read_gdrive_file(file_id: str) -> str:
    """Read content of a Google Drive file."""
    try:
        service = get_drive_service()
        meta = service.files().get(fileId=file_id, fields='name, mimeType').execute()
        if meta['mimeType'] == 'application/vnd.google-apps.document':
            request = service.files().export_media(fileId=file_id, mimeType='text/plain')
        else:
            request = service.files().get_media(fileId=file_id)
            
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return fh.getvalue().decode('utf-8')
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def write_gdrive_file(name: str, content: str, parent_id: str = VAULT_FOLDER_ID) -> str:
    """Create or update a file in Google Drive vault."""
    try:
        service = get_drive_service()
        media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/plain')
        
        # Check if exists
        q = f"name = '{name}' and '{parent_id}' in parents and trashed = false"
        results = service.files().list(q=q, fields='files(id)').execute()
        files = results.get('files', [])
        
        if files:
            fid = files[0]['id']
            service.files().update(fileId=fid, media_body=media).execute()
            return f"Updated file {name} (ID: {fid})"
        else:
            meta = {'name': name, 'parents': [parent_id]}
            res = service.files().create(body=meta, media_body=media, fields='id').execute()
            return f"Created file {name} (ID: {res.get('id')})"
    except Exception as e:
        return f"Error: {e}"

# =============================================================================
# WhatsApp Tools (Green API)
# =============================================================================

@mcp.tool()
def send_whatsapp(to_phone: str, message: str) -> str:
    """Send a WhatsApp message via Green API. Phone format: 1234567890 (no +)"""
    try:
        inst_id = fetch_secret("green-api-id")
        token = fetch_secret("green-api-token")
        
        # Format phone for Green API (must end with @c.us for numbers)
        if "@" not in to_phone:
            to_phone = f"{to_phone}@c.us"
            
        url = f"{GREEN_API_BASE_URL}/waInstance{inst_id}/sendMessage/{token}"
        payload = json.dumps({
            "chatId": to_phone,
            "message": message
        }).encode("utf-8")
        
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode())
            return f"WhatsApp sent. ID: {res_data.get('idMessage')}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def send_whatsapp_approval(approval_id: str, tool_name: str, arguments: str, context: str, risk: str = "high", to_phone: str = None) -> str:
    """Send a formatted WhatsApp approval request (HITL)."""
    # Use default phone if not provided
    if not to_phone:
        to_phone = "447517144170" # Default from project context if available, or fetch from secret
        # I'll try to fetch USER_WHATSAPP_NUMBER if it exists
        try:
            to_phone = fetch_secret("user-whatsapp-number")
        except:
            pass

    message = (
        f"🔒 *Tool Approval Required*\n\n"
        f"*Tool:* `{tool_name}`\n"
        f"*Arguments:* `{arguments}`\n"
        f"*Context:* {context}\n\n"
        f"{'🔴' if risk == 'high' else '🟡'} *Risk Level:* {risk}\n\n"
        f"*Approval ID:* `{approval_id}`\n\n"
        f"*Reply with:*\n"
        f"✅ APPROVE {approval_id}\n"
        f"❌ DENY {approval_id}"
    )
    return send_whatsapp(to_phone, message)

@mcp.tool()
def download_whatsapp_media(file_id: str) -> bytes:
    """Download media from WhatsApp via Green API using a fileId."""
    try:
        inst_id = fetch_secret("green-api-id")
        token = fetch_secret("green-api-token")
        
        url = f"{GREEN_API_BASE_URL}/waInstance{inst_id}/downloadFile/{token}"
        payload = json.dumps({"fileId": file_id}).encode("utf-8")
        
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req) as response:
            return response.read()
    except Exception as e:
        logger.error(f"Media download failed: {e}")
        return b""

@mcp.tool()
def analyze_whatsapp_image(file_id: str, prompt: str = "Describe this image in detail for a project management context.") -> str:
    """Download a WhatsApp image and analyze it using Gemini Vision."""
    try:
        # 1. Download image
        image_bytes = download_whatsapp_media(file_id)
        if not image_bytes:
            return "Error: Could not download image from WhatsApp."
        
        # 2. Setup Gemini
        gemini_key = fetch_secret("gemini-api-key")
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=gemini_key)
        
        # 3. Analyze
        import base64
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                prompt,
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
            ]
        )
        
        description = response.text
        
        # 4. Optional: Store in memory automatically
        memorize(f"Image Analysis (fileId: {file_id}):\n{description}", source="whatsapp_vision", tags=["vision", "whatsapp"])
        
        return f"### Image Analysis Result\n\n{description}"
    except Exception as e:
        return f"Error during image analysis: {e}"

# =============================================================================
# Memory Tools (GCP Gateway)
# =============================================================================

@mcp.tool()
def query_memory(query: str, limit: int = 3) -> str:
    """Query semantic memory via GCP Memory Orchestrator."""
    try:
        gateway_url = fetch_secret("gcp-gateway-url")
        payload = json.dumps({
            "operation": "query",
            "query": query,
            "limit": limit
        }).encode("utf-8")
        
        req = urllib.request.Request(gateway_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode())
            results = res_data.get("results", [])
            output = []
            for r in results:
                meta = r.get("metadata", {})
                output.append(f"Memory (Score: {r.get('score', 0):.2f})\nSource: {meta.get('source')}\nContent: {r.get('content')}")
            return "\n---\n".join(output) or "No relevant memories found."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def memorize(content: str, source: str = "omni_mcp", tags: List[str] = None) -> str:
    """Store content in long-term memory."""
    try:
        gateway_url = fetch_secret("gcp-gateway-url")
        payload = json.dumps({
            "operation": "memorize",
            "content": content,
            "metadata": {
                "source": source,
                "tags": tags or [],
                "timestamp": datetime.datetime.now().isoformat()
            }
        }).encode("utf-8")
        
        req = urllib.request.Request(gateway_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode())
            return f"Memorized successfully. ID: {res_data.get('id')}"
    except Exception as e:
        return f"Error: {e}"

# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    mcp.run()
