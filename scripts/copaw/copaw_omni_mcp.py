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

# CA bundle for HTTPS verify (GCP Cloud Functions / memory-orchestrator etc).
# Prefer certifi (carries Google's CA roots); fall back to the macOS system
# bundle. The framework Python build ships without its own cert.pem, so an
# explicit context is required to avoid CERTIFICATE_VERIFY_FAILED.
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context(cafile="/private/etc/ssl/cert.pem")
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
from google.auth.transport.requests import Request as GoogleAuthRequest

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

# ARCA MCP Server
ARCA_MCP_URL = "http://localhost:8086"

# =============================================================================
# MCP Server Setup
# =============================================================================

mcp = FastMCP(
    "Copaw Omni Server",
    instructions="""
    Consolidated BiOS Gateway for Email, Google Drive, WhatsApp, Memory, and ARCA Ecosystem.

    Capabilities:
    - Email: Read/Send via ProtonMail and Gmail.
    - Google Drive: Search, Read, Create, and Update files in 'Obsidian-life' vault.
    - WhatsApp: Send messages via Green API.
    - Memory: Query and Store semantic context via GCP Memory Orchestrator.
    - ARCA: Access Serena (reasoning) and ARCA Knowledge Base.

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

def fetch_secret(secret_name: str) -> Optional[str]:
    """Fetch a secret from the Credentials Server with a local filesystem fallback."""
    # 1. Try Credentials Server (Priority)
    try:
        api_key = get_credentials_api_key()
        req = urllib.request.Request(f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}")
        req.add_header("X-API-Key", api_key)
        
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            val = data.get("value")
            if val:
                return val
    except Exception as e:
        logger.warning(f"Credentials server fetch failed for '{secret_name}': {e}")

    logger.error(f"Secret '{secret_name}' not found in server.")
    return None

# =============================================================================
# Cloudflare DNS Management
# =============================================================================

@mcp.tool()
def update_arca_portal_dns(token: Optional[str] = None) -> str:
    """
    Updates the DNS record for arca-vsa.tech to point to the Cloud Run portal.
    
    Args:
        token: Optional Cloudflare API token. If not provided, it will be fetched from the Credentials Server.
    """
    import requests
    
    if not token:
        try:
            token = fetch_secret("cloudflare-dns-token")
        except Exception as e:
            return f"❌ Error: Failed to fetch cloudflare-dns-token from Credentials Server: {e}"
    
    if not token:
        return "❌ Error: Token is empty."
    
    zone_id = "22300411fc34d5337bfd96f60bd27218"
    root_domain = "arca-vsa.tech"
    target = "arca-portal-757330161781.us-central1.run.app"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 1. Find record
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    try:
        resp = requests.get(url, headers=headers, params={"name": root_domain})
        if not resp.ok:
            return f"❌ Failed to fetch records: {resp.text}"
        
        records = resp.json().get("result", [])
        if not records:
            # Create
            payload = {"type": "CNAME", "name": root_domain, "content": target, "proxied": True}
            create_resp = requests.post(url, headers=headers, json=payload)
            if create_resp.ok:
                return f"✅ Created DNS: {root_domain} -> {target}"
            return f"❌ Create failed: {create_resp.text}"
            
        record_id = records[0]["id"]
        # Update
        payload = {"type": "CNAME", "name": root_domain, "content": target, "proxied": True}
        update_resp = requests.put(f"{url}/{record_id}", headers=headers, json=payload)
        if update_resp.ok:
            return f"✅ Updated DNS: {root_domain} -> {target}"
        return f"❌ Update failed: {update_resp.text}"
        
    except Exception as e:
        return f"❌ Error: {str(e)}"

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
    html_body = ""
    plain_body = ""
    
    try:
        from bs4 import BeautifulSoup
        bs4_available = True
    except ImportError:
        bs4_available = False

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            if "attachment" in content_disposition:
                continue

            if content_type == "text/html" and not html_body:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    raw_html = part.get_payload(decode=True).decode(charset, errors="replace")
                    if bs4_available:
                        soup = BeautifulSoup(raw_html, "html.parser")
                        for element in soup(["script", "style", "head", "title", "meta", "[document]"]):
                            element.decompose()
                        text = soup.get_text(separator=" ", strip=True)
                        html_body = " ".join(text.split())
                    else:
                        html_body = re.sub(r"<[^>]+>", "", raw_html).strip()
                except: pass

            elif content_type == "text/plain" and not plain_body:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    plain_body = part.get_payload(decode=True).decode(charset, errors="replace")
                except: pass
        body = html_body if html_body else plain_body
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                plain_body = payload.decode(charset, errors="replace")
        except:
            plain_body = str(msg.get_payload())
        body = plain_body

    return body.strip()

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
            body_text = extract_body(msg)
            body_snippet = body_text[:2000]
            if len(body_text) > 2000:
                body_snippet += "..."
            results.append(f"ID: {eid.decode()}\nSubject: {decode_header_value(msg.get('Subject'))}\nFrom: {decode_header_value(msg.get('From'))}\nBody: {body_snippet}")
            
        mail.logout()
        return "\n---\n".join(results) or "No emails found."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def read_email(account: str, email_id: str) -> str:
    """Read a specific email's full body by its ID.
    
    Args:
        account: The email address to check.
        email_id: The IMAP message ID of the email.
    """
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
        
        status, data = mail.fetch(email_id.encode(), "(RFC822)")
        if status != "OK" or not data or not data[0]:
            mail.logout()
            return f"Error: Could not fetch email with ID {email_id}"
            
        msg = email.message_from_bytes(data[0][1])
        subject = decode_header_value(msg.get('Subject'))
        sender = decode_header_value(msg.get('From'))
        date_str = msg.get('Date')
        body = extract_body(msg)
        
        mail.logout()
        return f"ID: {email_id}\nSubject: {subject}\nFrom: {sender}\nDate: {date_str}\nBody:\n{body}"
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

GDRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']


def _persist_gdrive_token(creds: Credentials) -> None:
    """Write a refreshed OAuth token back to Azure Key Vault so it doesn't drift.

    The Credentials Server HTTP API is read-only by design, so the write goes
    straight to Key Vault via the `az` CLI (already authenticated on this host).
    After this, POST /cache/rotate is hit so the server re-reads the fresh value
    instead of serving the stale cached one for up to its 300s TTL.

    Best-effort: a failure here is logged but NOT fatal — the in-memory refreshed
    creds still work for this process; we just won't have persisted them.
    """
    import subprocess
    try:
        token_json = creds.to_json()  # includes the new access token + expiry
        vault = os.environ.get("AZURE_KEY_VAULT_NAME", "arca-mcp-kv-dae")
        proc = subprocess.run(
            ["az", "keyvault", "secret", "set",
             "--vault-name", vault,
             "--name", "gdrive-oauth-token",
             "--value", token_json],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            logger.warning("Could not persist refreshed gdrive token to Key Vault: %s",
                           proc.stderr.strip()[:200])
            return
        # Evict the server's cached copy so the next fetch sees the fresh token.
        try:
            api_key = get_credentials_api_key()
            req = urllib.request.Request(
                f"{CREDENTIALS_SERVER_URL}/cache/rotate?name=gdrive-oauth-token",
                method="POST", headers={"X-API-Key": api_key})
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.warning("Token persisted but cache rotate failed: %s", e)
        logger.info("🔄 Refreshed gdrive OAuth token persisted to Key Vault.")
    except Exception as e:
        logger.warning("Failed to persist refreshed gdrive token: %s", e)


def _load_json_secret(raw: str) -> Optional[dict]:
    """Parse a secret that may be raw JSON or base64-wrapped JSON.

    The `gcp-credentials-json` vault secret is stored base64-encoded, so a plain
    json.loads on it fails. Try direct JSON first, then base64.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        import base64
        return json.loads(base64.b64decode(raw))
    except Exception:
        return None


def get_drive_service(require_write: bool = False):
    """Retrieve a Drive service.

    PRIMARY = user OAuth (`gdrive-oauth-token`). A service account CANNOT create
    files on a personal @gmail.com Drive ("Service Accounts do not have storage
    quota" — confirmed 403), so all WRITES must use the user's own identity, and
    we use OAuth for reads too for one consistent permission model. OAuth access
    tokens expire hourly, so we refresh-on-load and persist the refreshed token
    back to Key Vault (_persist_gdrive_token). The refresh_token itself stays
    long-lived ONLY if the GCP consent screen is Published (Testing-mode tokens
    are revoked ~weekly → invalid_grant; re-run scripts/copaw/reauth_gdrive_oauth.py).

    FALLBACK = service account (`gcp-credentials-json`), READ-ONLY. It can read
    anything shared with arca-service-agent@… (incl. the vault), so it keeps
    search/read alive if OAuth is mid-re-auth — but it can't write, so callers
    that need to create files pass require_write=True to skip it.
    """
    from google.oauth2 import service_account

    # 1. User OAuth — primary; required for writes. Refresh + persist on load.
    token_json = fetch_secret("gdrive-oauth-token")
    if token_json:
        token_data = _load_json_secret(token_json)
        if token_data:
            creds = Credentials.from_authorized_user_info(token_data, scopes=GDRIVE_SCOPES)
            if (not creds.valid) and creds.refresh_token:
                try:
                    creds.refresh(GoogleAuthRequest())
                    _persist_gdrive_token(creds)
                except Exception as e:
                    logger.error("gdrive OAuth refresh failed (refresh_token likely "
                                 "revoked — publish consent screen + run "
                                 "reauth_gdrive_oauth.py): %s", e)
                    creds = None
            if creds is not None:
                return build('drive', 'v3', credentials=creds)

    # 2. Service account — READ-ONLY fallback. Skip when the caller needs to write.
    if not require_write:
        sa_data = _load_json_secret(fetch_secret("gcp-credentials-json"))
        if sa_data:
            try:
                creds = service_account.Credentials.from_service_account_info(
                    sa_data, scopes=GDRIVE_SCOPES
                )
                logger.warning("Using read-only service-account GDrive fallback "
                               "(OAuth unavailable — writes will fail until re-auth).")
                return build('drive', 'v3', credentials=creds)
            except Exception as e:
                logger.warning("Service-account fallback failed to load: %s", e)

    raise ValueError("❌ Error: No working GDrive credentials. For writes, OAuth is "
                     "required — publish the consent screen and run reauth_gdrive_oauth.py.")

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
        # require_write=True → never fall back to the SA (it can't write to a
        # personal Drive; it would 403 'no storage quota'). Surface the re-auth
        # message instead.
        service = get_drive_service(require_write=True)
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
        
        if not inst_id or not token:
            return "❌ Error: Missing Green API credentials in vault. Cannot send WhatsApp message."
        
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
        
        if not inst_id or not token:
            return "❌ Error: Missing Green API credentials in vault. Cannot send WhatsApp message."
        
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
# Credentials & Secret Management Tools
# =============================================================================

@mcp.tool()
def get_secret(secret_name: str) -> str:
    """Fetch a secret from the Credentials Server (port 8089) with local filesystem fallback.

    Available secrets:
    - notion-api-key: Notion integration token
    - gcp-gateway-url: Memory Orchestrator endpoint
    - muninndb-token: MuninnDB MCP auth token
    - arca-mcp-api-key: ARCA MCP authentication
    - gmail-app-password: Gmail SMTP/IMAP app password
    - proton-bridge-password: ProtonMail bridge password
    - cloudflare-dns-token: Cloudflare API token
    - And others configured in Azure Key Vault
    """
    secret = fetch_secret(secret_name)
    if secret:
        # Don't leak full secret in response, just confirm retrieval
        return f"✅ Secret '{secret_name}' retrieved ({len(secret)} chars)"
    return f"❌ Secret '{secret_name}' not found"

@mcp.tool()
def list_available_secrets() -> str:
    """List all secrets configured in the Credentials Server."""
    return """
    Available secrets (fetch via get_secret):

    [ARCA Infrastructure]
    - arca-mcp-api-key: ARCA MCP token for knowledge graph
    - gcp-gateway-url: Memory Orchestrator (MemU) endpoint
    - muninndb-token: Local MuninnDB MCP token
    - notion-api-key: Notion database integration

    [Email & Communications]
    - gmail-app-password: Gmail SMTP/IMAP auth
    - proton-bridge-password: ProtonMail local bridge
    - greenapi-token: Green API (WhatsApp) auth

    [Infrastructure]
    - cloudflare-dns-token: DNS updates for arca-vsa.tech
    - oracle-26ai-connection: Oracle 26AI database URI
    - tailscale-auth-key: Tailscale VPN authentication

    [Credentials Server Info]
    Endpoint: http://localhost:8089
    Auth: X-API-Key header (read from /Users/danexall/biomimetics/secrets/credentials_api_key)
    Fallback: DISABLED (Azure Key Vault ONLY)
    """

# =============================================================================
# Memory Tools (GCP Gateway)
# =============================================================================

@mcp.tool()
def query_memory(query: str, limit: int = 3, include_local: bool = True) -> str:
    """Query semantic memory across GCP Memory Orchestrator + MuninnDB (local).

    Args:
        query: Search term
        limit: Results per source
        include_local: Also query MuninnDB (local Hebbian memory)
    """
    output = []

    # 1. Query GCS Memory Orchestrator (long-term, wide-scope)
    try:
        gateway_url = fetch_secret("gcp-gateway-url")
        payload = json.dumps({
            "operation": "query",
            "query": query,
            "limit": limit
        }).encode("utf-8")

        req = urllib.request.Request(gateway_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

        # Retry logic for cold-start Cloud Functions
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as response:
                    res_data = json.loads(response.read().decode())
                    results = res_data.get("results", [])
                    if results:
                        output.append("[GCS Memory Orchestrator]")
                        for r in results:
                            meta = r.get("metadata", {})
                            output.append(f"  • (Score: {r.get('score', 0):.2f}) {r.get('content', '')[:150]}")
                    break  # Success, exit retry loop
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"GCS query attempt {attempt+1} failed: {e}, retrying...")
                    continue
                logger.warning(f"GCS query failed after {attempt+1} attempts: {e}")
    except Exception as e:
        logger.warning(f"GCS query setup failed: {e}")

    # 2. Query MuninnDB (local, agentic, transient)
    if include_local:
        try:
            import subprocess
            muninn_token = os.environ.get("MUNINN_MCP_TOKEN") or fetch_secret("muninndb-token") or "mdb_248e19f39cc1db20ffbb88d987fc351f9841038702cee471"

            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {
                    "name": "muninn_recall",
                    "arguments": {
                        "context": [query],
                        "limit": limit,
                        "threshold": 0.5
                    }
                }
            }

            result = subprocess.run(
                ["curl", "-sf", "http://127.0.0.1:8750/mcp",
                 "-H", "Content-Type: application/json",
                 "-H", f"Authorization: Bearer {muninn_token}",
                 "-d", json.dumps(payload)],
                capture_output=True,
                text=True,
                timeout=3
            )

            if result.stdout:
                resp = json.loads(result.stdout)
                items = resp.get("result", {}).get("content", [])
                if items and "memories" in items[0].get("text", "{}"):
                    mems = json.loads(items[0].get("text", "{}")).get("memories", [])
                    if mems:
                        output.append("\n[MuninnDB — Local Agentic Memory]")
                        for mem in mems[:limit]:
                            output.append(f"  • {mem.get('concept', '')[:80]}")
        except Exception as e:
            logger.warning(f"MuninnDB query failed: {e}")

    if not output:
        return "No relevant memories found across systems."

    return "\n".join(output)


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
        
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as response:
            res_data = json.loads(response.read().decode())
            return f"Memorized successfully. ID: {res_data.get('id')}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def get_universal_context(subject: str, radius: int = 4) -> str:
    """
    Retrieve specialized context frame around a subject (Service, Code, Workflow) from the Holographic Context Graph.
    This fetches a 4-layer 4-hop radius of semantic memory.
    """
    import requests
    try:
        api_key = fetch_secret("arca-mcp-api-key")
        if not api_key:
            logger.warning("arca-mcp-api-key not found. Proceeding with dummy key.")
            api_key = "dev-key-bypass"
        
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "get_universal_context",
                "arguments": {
                    "subject": subject,
                    "radius": radius
                }
            },
            "id": 1
        }
        headers = {
            "X-API-Key": api_key,
            "X-Genesis-X-Chain": "true",
            "X-Genesis-Chain": "true"
        }
        resp = requests.post(f"{ARCA_MCP_URL}/mcp", headers=headers, json=payload, timeout=20)
        return resp.text
    except Exception as e:
        return f"Error retrieving universal context: {e}"

@mcp.tool()
def serena_analyze_code(code: str, context: str = "") -> str:
    """Analyze code for semantic meaning and potential refactoring via Serena."""
    import requests
    try:
        api_key = fetch_secret("arca-mcp-api-key")
        if not api_key:
            logger.warning("arca-mcp-api-key not found. Proceeding with dummy key.")
            api_key = "dev-key-bypass"
        
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "serena_analyze_code", "arguments": {"code": code, "context": context}},
            "id": 1
        }
        headers = {
            "X-API-Key": api_key,
            "X-Genesis-X-Chain": "true",
            "X-Genesis-Chain": "true"
        }
        resp = requests.post(f"{ARCA_MCP_URL}/mcp", headers=headers, json=payload, timeout=60)
        return resp.text
    except Exception as e:
        return f"Error calling Serena: {e}"

@mcp.tool()
def serena_refactor_suggestion(code: str, goal: str) -> str:
    """Suggest refactoring for a specific goal via Serena."""
    import requests
    try:
        api_key = fetch_secret("arca-mcp-api-key")
        if not api_key:
            logger.warning("arca-mcp-api-key not found. Proceeding with dummy key.")
            api_key = "dev-key-bypass"
        
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "serena_refactor_suggestion", "arguments": {"code": code, "goal": goal}},
            "id": 1
        }
        headers = {
            "X-API-Key": api_key,
            "X-Genesis-X-Chain": "true",
            "X-Genesis-Chain": "true"
        }
        resp = requests.post(f"{ARCA_MCP_URL}/mcp", headers=headers, json=payload, timeout=60)
        return resp.text
    except Exception as e:
        return f"Error calling Serena: {e}"

@mcp.tool()
def serena_semantic_diff(diff_content: str, context: str = "") -> str:
    """Analyze the semantic impact of code changes (diff) via Serena."""
    import requests
    try:
        api_key = fetch_secret("arca-mcp-api-key")
        if not api_key:
            logger.warning("arca-mcp-api-key not found. Proceeding with dummy key.")
            api_key = "dev-key-bypass"
        
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "serena_semantic_diff", "arguments": {"diff_content": diff_content, "context": context}},
            "id": 1
        }
        headers = {
            "X-API-Key": api_key,
            "X-Genesis-X-Chain": "true",
            "X-Genesis-Chain": "true"
        }
        resp = requests.post(f"{ARCA_MCP_URL}/mcp", headers=headers, json=payload, timeout=60)
        return resp.text
    except Exception as e:
        return f"Error calling Serena: {e}"

@mcp.tool()
def serena_security_scan(content: str, context: str = "") -> str:
    """Scan code or config for security vulnerabilities via Serena."""
    import requests
    try:
        api_key = fetch_secret("arca-mcp-api-key")
        if not api_key:
            logger.warning("arca-mcp-api-key not found. Proceeding with dummy key.")
            api_key = "dev-key-bypass"
        
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "serena_security_scan", "arguments": {"content": content, "context": context}},
            "id": 1
        }
        headers = {
            "X-API-Key": api_key,
            "X-Genesis-X-Chain": "true",
            "X-Genesis-Chain": "true"
        }
        resp = requests.post(f"{ARCA_MCP_URL}/mcp", headers=headers, json=payload, timeout=60)
        return resp.text
    except Exception as e:
        return f"Error calling Serena: {e}"

@mcp.tool()
def serena_chat(prompt: str, context: str = "") -> str:
    """General interaction with Serena for architectural reasoning and task dispatch."""
    import requests
    try:
        api_key = fetch_secret("arca-mcp-api-key")
        if not api_key:
            logger.warning("arca-mcp-api-key not found. Proceeding with dummy key.")
            api_key = "dev-key-bypass"
        
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "serena_chat", "arguments": {"prompt": prompt, "context": context}},
            "id": 1
        }
        headers = {
            "X-API-Key": api_key,
            "X-Genesis-X-Chain": "true",
            "X-Genesis-Chain": "true"
        }
        resp = requests.post(f"{ARCA_MCP_URL}/mcp", headers=headers, json=payload, timeout=60)
        return resp.text
    except Exception as e:
        return f"Error calling Serena: {e}"

@mcp.tool()
def search_arca(query: str) -> str:
    """
    Search the ARCA semantic knowledge base and holographic memory for technical documentation and system history.
    """
    import requests
    try:
        api_key = fetch_secret("arca-mcp-api-key")
        if not api_key:
            logger.warning("arca-mcp-api-key not found. Proceeding with dummy key.")
            api_key = "dev-key-bypass"
        
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "recall_memory",
                "arguments": {
                    "query": query,
                    "session_id": "default",
                    "top_k": 5
                }
            },
            "id": 1
        }
        headers = {
            "X-API-Key": api_key,
            "X-Genesis-X-Chain": "true",
            "X-Genesis-Chain": "true"
        }
        resp = requests.post(f"{ARCA_MCP_URL}/mcp", headers=headers, json=payload, timeout=20)
        return resp.text
    except Exception as e:
        return f"Error searching ARCA: {e}"

# =============================================================================
# Notion Tools
# =============================================================================

NOTION_API_VERSION = "2022-06-28"

def _notion_request(method: str, endpoint: str, payload: dict = None) -> dict:
    token = fetch_secret("notion-api-key")
    if not token:
        raise ValueError("notion-api-key not found in Credentials Server")
    
    url = f"https://api.notion.com/v1{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json"
    }
    
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))

@mcp.tool()
def search_notion_tasks(query: str = "", database_id: str = None) -> str:
    """Search for tasks in Notion database.
    
    Args:
        query: Search text to filter by title
        database_id: Optional specific database ID (defaults to main BiOS tasks DB)
    """
    try:
        if not database_id:
            database_id = fetch_secret("notion-bios-database-id") or "default"
        
        filter_obj = {}
        if query:
            filter_obj = {
                "property": "Name",
                "title": {"contains": query}
            }
        
        payload = {"page_size": 20}
        if filter_obj:
            payload["filter"] = filter_obj
        
        result = _notion_request("POST", f"/databases/{database_id}/query", payload)
        
        pages = result.get("results", [])
        if not pages:
            return "No tasks found."
        
        output = []
        for page in pages:
            props = page.get("properties", {})
            title = ""
            if "Name" in props and props["Name"].get("title"):
                title = props["Name"]["title"][0].get("plain_text", "")
            
            status = ""
            if "Status" in props:
                status_obj = props["Status"]
                if "status" in status_obj and status_obj["status"]:
                    status = status_obj["status"].get("name", "")
            
            page_id = page.get("id", "")
            output.append(f"• {title} [{status}] (ID: {page_id})")
        
        return "\n".join(output)
    except Exception as e:
        return f"Error searching Notion: {e}"

@mcp.tool()
def update_notion_task_status(task_id: str, status: str) -> str:
    """Update the status of a Notion task.
    
    Args:
        task_id: The Notion page ID of the task
        status: New status value (e.g., 'Ready for Dev', 'In Progress', 'Done')
    """
    try:
        payload = {
            "properties": {
                "Status": {
                    "status": {"name": status}
                }
            }
        }
        
        result = _notion_request("PATCH", f"/pages/{task_id}", payload)
        return f"Updated task {task_id} to status: {status}"
    except Exception as e:
        return f"Error updating Notion task: {e}"

@mcp.tool()
def create_notion_task(title: str, description: str = "", database_id: str = None) -> str:
    """Create a new task in Notion.
    
    Args:
        title: Task title
        description: Optional task description
        database_id: Optional database ID (defaults to main BiOS tasks DB)
    """
    try:
        if not database_id:
            database_id = fetch_secret("notion-bios-database-id") or "default"
        
        payload = {
            "parent": {"database_id": database_id},
            "properties": {
                "Name": {
                    "title": [{"text": {"content": title}}]
                }
            }
        }
        
        if description:
            payload["properties"]["Description"] = {
                "rich_text": [{"text": {"content": description[:2000]}}]
            }
        
        result = _notion_request("POST", "/pages", payload)
        page_id = result.get("id", "unknown")
        return f"Created Notion task: {title} (ID: {page_id})"
    except Exception as e:
        return f"Error creating Notion task: {e}"

# =============================================================================
# GitHub Integration Tools
# =============================================================================

@mcp.tool()
def create_github_issue(title: str, body: str, repo: str = "danexall/biomimetics") -> str:
    """Create a GitHub issue.
    
    Args:
        title: Issue title
        body: Issue body/description
        repo: GitHub repository (owner/repo format)
    """
    try:
        token = fetch_secret("github-api-key")
        if not token:
            return "Error: github-api-key not found in Credentials Server"
        
        url = f"https://api.github.com/repos/{repo}/issues"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        
        payload = json.dumps({"title": title, "body": body}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
        
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
            issue_num = result.get("number", "?")
            issue_url = result.get("html_url", "")
            return f"Created GitHub issue #{issue_num}: {issue_url}"
    except Exception as e:
        return f"Error creating GitHub issue: {e}"

@mcp.tool()
def dispatch_pm_brief(title: str, description: str, repo: str = "danexall/biomimetics") -> str:
    """Record a new engineering requirement. Creates both GitHub issue and Notion task.
    
    Args:
        title: Clear title for the issue/task
        description: Detailed engineering brief
        repo: GitHub repository (owner/repo format)
    """
    results = []
    
    gh_result = create_github_issue(title, description, repo)
    results.append(f"GitHub: {gh_result}")
    
    notion_result = create_notion_task(title, description)
    results.append(f"Notion: {notion_result}")
    
    return "\n".join(results)

# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    mcp.run()
