#!/usr/bin/env python3
"""
MCP Email Server - Proton Bridge + Gmail Integration
Exposes secure IMAP reading and SMTP sending capabilities via FastMCP.

Uses local Proton Mail Bridge + Gmail IMAP:
- Proton IMAP: 127.0.0.1:1143 (STARTTLS)
- Proton SMTP: 127.0.0.1:1025 (STARTTLS)
- Gmail IMAP: imap.gmail.com:993 (SSL)
- Gmail SMTP: smtp.gmail.com:587 (STARTTLS)

Secure credential loading from Credentials Server.
"""

import imaplib
import smtplib
import ssl
import email
import urllib.request
import urllib.error
import json
import re
from email.message import EmailMessage
from email.header import decode_header
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from mcp.server.fastmcp import FastMCP

# =============================================================================
# Configuration
# =============================================================================

CREDENTIALS_FILE = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
CREDENTIALS_SERVER_URL = "http://localhost:8089"

# Proton Bridge Configuration
PROTON_IMAP_HOST = "127.0.0.1"
PROTON_IMAP_PORT = 1143
PROTON_SMTP_HOST = "127.0.0.1"
PROTON_SMTP_PORT = 1025

# Gmail Configuration
GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587

# SSL Contexts
SSL_CONTEXT = ssl._create_unverified_context()  # For Proton Bridge (localhost)
# Gmail SSL Context - disable verification for compatibility
GMAIL_SSL_CONTEXT = ssl._create_unverified_context()  # For Gmail

# Email Accounts Configuration
EMAIL_ACCOUNTS = {
    # ProtonMail accounts (via Bridge)
    "dan.exall@pm.me": {"type": "proton", "secret": "proton-bridge-password"},
    "dan@arca-vsa.tech": {"type": "proton", "secret": "proton-bridge-password"},
    "arca@arca-vsa.tech": {"type": "proton", "secret": "proton-bridge-password"},
    "info@arca-vsa.tech": {"type": "proton", "secret": "proton-bridge-password"},
    "claws@arca-vsa.tech": {"type": "proton", "secret": "proton-bridge-password"},
    # Gmail account
    "dan.exall@gmail.com": {"type": "gmail", "secret": "gmail-app-password"},
}

# =============================================================================
# FastMCP Server Setup
# =============================================================================

mcp = FastMCP(
    "Email Server",
    instructions="""
    Proton Mail Bridge + Gmail MCP Server - Secure email reading and sending.

    Available accounts:
    ProtonMail (via Bridge):
    - dan.exall@pm.me
    - dan@arca-vsa.tech
    - arca@arca-vsa.tech
    - info@arca-vsa.tech
    - claws@arca-vsa.tech
    
    Gmail:
    - dan.exall@gmail.com

    Proton connections use local Bridge with STARTTLS encryption.
    Gmail uses standard IMAP/SMTP with SSL/STARTTLS.
    Credentials are fetched securely from Credentials Server at runtime.
    """,
)

# =============================================================================
# Credential Loading
# =============================================================================


def get_credentials_api_key() -> str:
    """Load Credentials API key from secure file."""
    if CREDENTIALS_FILE.exists():
        return CREDENTIALS_FILE.read_text().strip()
    raise FileNotFoundError(f"Credentials API key not found: {CREDENTIALS_FILE}")


def fetch_secret(secret_name: str) -> str:
    """Fetch a secret from the Credentials Server using urllib."""
    api_key = get_credentials_api_key()

    req = urllib.request.Request(f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}")
    req.add_header("X-API-Key", api_key)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("value")
    except urllib.error.HTTPError as e:
        raise Exception(f"Failed to fetch {secret_name}: HTTP {e.code}")
    except Exception as e:
        raise Exception(f"Failed to fetch {secret_name}: {e}")


def get_account_password(account: str) -> Tuple[str, str]:
    """
    Fetch password for an email account from Credentials Server.
    Returns (password, account_type) tuple.
    """
    if account not in EMAIL_ACCOUNTS:
        raise ValueError(f"Unknown account: {account}")
    
    config = EMAIL_ACCOUNTS[account]
    password = fetch_secret(config["secret"])
    return password, config["type"]


# =============================================================================
# Email Helpers
# =============================================================================


def decode_header_value(header_value: str) -> str:
    """Safely decode email header with multiple encodings."""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    result = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8", errors="ignore")
        else:
            result += str(part)
    return result


def extract_plain_text_body(msg: email.message.Message) -> str:
    """Extract plain text body from email, stripping HTML if needed."""
    plain_text = ""
    html_text = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            if "attachment" in content_disposition:
                continue

            try:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    decoded = payload.decode(charset, errors="replace")

                    if content_type == "text/plain":
                        plain_text += decoded
                    elif content_type == "text/html":
                        html_text += decoded
            except Exception:
                pass
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                plain_text = payload.decode(charset, errors="replace")
        except Exception:
            plain_text = str(msg.get_payload())

    # Prefer plain text, otherwise strip HTML
    if plain_text:
        return plain_text.strip()
    elif html_text:
        return re.sub(r"<[^>]+>", "", html_text).strip()
    else:
        return ""


def connect_imap(email_addr: str, password: str, account_type: str) -> imaplib.IMAP4:
    """Connect to IMAP server (Proton Bridge or Gmail)."""
    if account_type == "gmail":
        # Gmail uses IMAP SSL on port 993
        mail = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT, ssl_context=GMAIL_SSL_CONTEXT)
    else:
        # Proton Bridge uses STARTTLS on port 1143
        mail = imaplib.IMAP4(PROTON_IMAP_HOST, PROTON_IMAP_PORT)
        mail.starttls(ssl_context=SSL_CONTEXT)
    
    mail.login(email_addr, password)
    return mail


def connect_smtp(email_addr: str, password: str, account_type: str) -> smtplib.SMTP:
    """Connect to SMTP server (Proton Bridge or Gmail)."""
    if account_type == "gmail":
        # Gmail uses STARTTLS on port 587
        server = smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT)
        server.starttls(context=GMAIL_SSL_CONTEXT)
    else:
        # Proton Bridge uses STARTTLS on port 1025
        server = smtplib.SMTP(PROTON_SMTP_HOST, PROTON_SMTP_PORT)
        server.starttls(context=SSL_CONTEXT)

    server.login(email_addr, password)
    return server


# =============================================================================
# MCP Tools
# =============================================================================


@mcp.tool()
def read_recent_emails(account: str, limit: int = 5) -> str:
    """
    Read recent emails from a ProtonMail or Gmail account.

    Args:
        account: Email address (must be one of the configured accounts)
        limit: Number of recent emails to fetch (default: 5, max: 50)

    Returns:
        Formatted string with email details (Subject, Sender, Date, Body snippet)
    """
    # Validate account
    if account not in EMAIL_ACCOUNTS:
        return f"❌ Invalid account. Must be one of: {', '.join(EMAIL_ACCOUNTS.keys())}"

    # Validate limit
    limit = min(max(1, limit), 50)  # Clamp between 1 and 50

    try:
        # Fetch password and account type
        password, account_type = get_account_password(account)

        # Connect to IMAP
        mail = connect_imap(account, password, account_type)
        mail.select("INBOX")

        # Search for all emails
        status, messages = mail.search(None, "ALL")
        if status != "OK":
            mail.close()
            mail.logout()
            return "❌ Failed to search INBOX"

        email_ids = messages[0].split()
        if not email_ids:
            mail.close()
            mail.logout()
            return f"📬 No emails found in {account}"

        # Get most recent emails
        recent_ids = email_ids[-limit:]
        results = []

        for email_id in reversed(recent_ids):
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Extract headers
            subject = decode_header_value(msg.get("Subject", "No Subject"))
            sender = decode_header_value(msg.get("From", "Unknown"))
            date = decode_header_value(msg.get("Date", ""))

            # Extract body snippet (first 200 chars)
            body = extract_plain_text_body(msg)
            body_snippet = body[:200].replace("\n", " ").strip()
            if len(body) > 200:
                body_snippet += "..."

            results.append({
                "subject": subject,
                "from": sender,
                "date": date,
                "body": body_snippet,
            })

        mail.close()
        mail.logout()

        # Format output
        output = [f"📧 Recent Emails for {account} ({len(results)} emails):\n"]
        for i, email_data in enumerate(results, 1):
            output.append(f"\n{i}. Subject: {email_data['subject']}")
            output.append(f"   From: {email_data['from']}")
            output.append(f"   Date: {email_data['date']}")
            output.append(f"   Body: {email_data['body']}")

        return "\n".join(output)

    except Exception as e:
        return f"❌ Error reading emails: {e}"


@mcp.tool()
def send_email(account: str, to_address: str, subject: str, body: str) -> str:
    """
    Send an email from a ProtonMail or Gmail account.

    Args:
        account: Sender email address (must be one of the configured accounts)
        to_address: Recipient email address
        subject: Email subject line
        body: Email body text

    Returns:
        Success confirmation string
    """
    # Validate account
    if account not in EMAIL_ACCOUNTS:
        return f"❌ Invalid account. Must be one of: {', '.join(EMAIL_ACCOUNTS.keys())}"

    try:
        # Fetch password and account type
        password, account_type = get_account_password(account)

        # Create email message
        msg = EmailMessage()
        msg["From"] = account
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.set_content(body)

        # Connect to SMTP and send
        server = connect_smtp(account, password, account_type)
        server.send_message(msg)
        server.quit()

        return f"✅ Email sent successfully from {account} to {to_address}\n   Subject: {subject}"

    except Exception as e:
        return f"❌ Failed to send email: {e}"


@mcp.tool()
def list_accounts() -> str:
    """
    List all configured email accounts available for email operations.

    Returns:
        Formatted list of available email accounts
    """
    output = ["📧 Configured Email Accounts:\n"]
    output.append("  ProtonMail (via Bridge):")
    for account, config in EMAIL_ACCOUNTS.items():
        if config["type"] == "proton":
            output.append(f"    - {account}")
    output.append("\n  Gmail:")
    for account, config in EMAIL_ACCOUNTS.items():
        if config["type"] == "gmail":
            output.append(f"    - {account}")
    return "\n".join(output)


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
