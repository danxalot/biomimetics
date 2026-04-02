#!/usr/bin/env python3
"""
Email Backfill Script - Hybrid Triage + Direct Notion API
Pulls historical emails from ProtonMail and Gmail accounts from Dec 25, 2025 to present.
Uses rule-based regex filtering + LLM fallback, routes KEEP emails to Notion API.

Secure Credential Loading:
- Reads CREDENTIALS_API_KEY from /Users/danexall/biomimetics/secrets/credentials_api_key
- Fetches all secrets (proton-bridge-password, gmail-app-password, notion-api-key) from Credentials Server
"""

import os
import sys
import json
import ssl
import imaplib
import email
import re
import time
import httpx
import openai
from datetime import datetime, timedelta
from pathlib import Path
from email.header import decode_header
from typing import List, Dict, Optional, Tuple

# ============================================================================
# Secure Credential Loading from Credentials Server
# ============================================================================

SECRETS_DIR = Path("/Users/danexall/biomimetics/secrets")
CREDENTIALS_API_KEY_FILE = SECRETS_DIR / "credentials_api_key"
CREDENTIALS_SERVER_URL = "http://localhost:8089"

# ============================================================================
# Configuration
# ============================================================================

START_DATE = "25-Dec-2025"  # Backfill from this date (IMAP enforced)
# No email limit - process ALL emails since START_DATE

# Proton Bridge Configuration
PROTON_HOST = "127.0.0.1"
PROTON_PORT = 1143

# Gmail Configuration
GMAIL_HOST = "imap.gmail.com"
GMAIL_PORT = 993

# LLM Configuration
LOCAL_LLM_BASE_URL = "http://localhost:11435/v1"
LOCAL_LLM_MODEL = "qwen3.5-2b-q8_0"

# Notion API Configuration
NOTION_TRIAGE_DB_ID = "3284d2d9fc7c81bd9a91e865511e642f"  # BiOS Triage
NOTION_API_URL = "https://api.notion.com/v1/pages"

# Test Mode Configuration (set to False for full production run)
TEST_MODE = True  # If True, only processes arca-vsa.tech accounts with limited batch
TEST_BATCH_SIZE = 50  # Number of emails to process per account in test mode

# Multi-Account Configuration
ACCOUNTS = [
    {"email": "dan.exall@pm.me", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "dan@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "arca@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "info@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "claws@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "dan.exall@gmail.com", "type": "gmail", "secret": "gmail-app-password"},
]

# Filter accounts for test mode
if TEST_MODE:
    ACCOUNTS = [acc for acc in ACCOUNTS if "arca-vsa.tech" in acc["email"]]

# The strict deterministic net (Word boundaries applied automatically)
KEEP_KEYWORDS = [
    "invoice",
    "receipt",
    "you sent",
    "payment",
    "octopus",
    "vultr",
    "azure",
    "ticket",
    "order",
    "document",
    "citizens advice",
    "cab",
    "debt",
    "arrears",
    "collection",
    "bailiff",
    "stepchange",
    "credit",
    "complaint",
    "appeal",
    "ombudsman",
    "watchdog",
    "legal",
    "solicitor",
    "police",
    "council",
    "security alert",
    "breach",
    "pwned",
    "unauthorized",
    "login",
]

# Build regex pattern for exact word boundaries
PATTERN = re.compile(
    r"\b(?:" + "|".join(map(re.escape, KEEP_KEYWORDS)) + r")\b", re.IGNORECASE
)

# SSL contexts
PROTON_SSL_CONTEXT = ssl.create_default_context()
PROTON_SSL_CONTEXT.check_hostname = False
PROTON_SSL_CONTEXT.verify_mode = ssl.CERT_NONE

GMAIL_SSL_CONTEXT = ssl.create_default_context()

# State tracking
STATE_FILE = Path.home() / ".arca" / "email_backfill_state.json"

# ============================================================================
# Helper Functions
# ============================================================================


def load_credentials_api_key() -> str:
    """Load Credentials API key from secure file."""
    if CREDENTIALS_API_KEY_FILE.exists():
        return CREDENTIALS_API_KEY_FILE.read_text().strip()
    return os.getenv("CREDENTIALS_API_KEY", "")


def fetch_secret(secret_name: str) -> Optional[str]:
    """Fetch a secret from the Credentials Server."""
    api_key = load_credentials_api_key()
    if not api_key:
        print(f"⚠️  No CREDENTIALS_API_KEY found for fetching {secret_name}")
        return None

    try:
        response = httpx.get(
            f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}",
            headers={"X-API-Key": api_key},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("value")
        else:
            print(f"⚠️  Failed to fetch {secret_name}: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"⚠️  Error fetching {secret_name}: {e}")
        return None


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


def extract_email_body(msg: email.message.Message) -> str:
    """
    Extract clean plain text body from email.
    Prioritizes text/plain, falls back to text/html with HTML stripped.
    Truncates to 1900 characters for Notion API compatibility.
    """
    plain_text = ""
    html_text = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            # Skip attachments
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

    # Prefer plain text, otherwise strip HTML from html_text
    if plain_text:
        body = plain_text.strip()
    elif html_text:
        # Strip HTML tags using regex
        body = re.sub(r"<[^>]+>", "", html_text).strip()
    else:
        body = ""

    # Truncate to 1900 characters for Notion API (limit is 2000)
    if len(body) > 1900:
        body = body[:1900] + "..."

    return body


# ============================================================================
# Hybrid Triage Logic
# ============================================================================


def check_rule_based_filter(subject: str, sender: str) -> bool:
    """
    Check if email matches rule-based filters.
    SCOPE: Only Subject and From headers are checked (NOT body)
    REGEX: Uses word boundaries to prevent false positives
    """
    combined_header_text = f"{subject} {sender}"
    return PATTERN.search(combined_header_text) is not None


def classify_with_llm(subject: str, sender: str, body: str = "") -> bool:
    """
    Use local Qwen3.5-2b LLM to classify email.
    Returns True if KEEP, False if SKIP.
    """
    try:
        client = openai.OpenAI(
            base_url=LOCAL_LLM_BASE_URL,
            api_key="not-needed",
        )

        prompt = f"""You are a ruthless, precision email triage agent. Your ONLY job is to identify emails directly related to the personal, financial, legal, or business affairs of 'Daniel Exall' or 'Sheila Tilmouth'. You must be highly skeptical. If an email is marketing, a newsletter, a generic automated alert, or spam, classify it as 'SKIP'. ONLY classify an email as 'KEEP' if you have high confidence it requires human review by Daniel or Sheila. When in doubt, default to 'SKIP'.

Subject: {subject[:100]}
From: {sender[:50]}

Reply with exactly one word: KEEP or SKIP"""

        response = client.chat.completions.create(
            model=LOCAL_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0.1
        )

        llm_result = response.choices[0].message.content.strip().upper() if response.choices[0].message.content else "SKIP"
        return "KEEP" in llm_result

    except Exception as e:
        print(f"  ⚠️  LLM error: {e}")
        return False  # Default to SKIP if LLM fails


def triage_email(subject: str, sender: str, body: str = "") -> Tuple[str, bool]:
    """
    Apply hybrid triage: rules first, then LLM fallback.
    Returns: (method, should_keep)
    """
    # Step 1: Check rule-based filters (header-only)
    rule_match = check_rule_based_filter(subject, sender)
    if rule_match:
        return ("Rule", True)

    # Step 2: Fall back to LLM
    llm_keep = classify_with_llm(subject, sender, body)
    return ("LLM", llm_keep)


# ============================================================================
# Notion Integration
# ============================================================================


def create_notion_payload(subject: str, sender: str, body: str, account: str, email_date: str = None) -> dict:
    """
    Create Notion API payload for new page.
    
    Args:
        subject: Email subject
        sender: Email from address
        body: Email body text (truncated to 1900 chars)
        account: Email account source
        email_date: ISO 8601 formatted date string (included in content, not as separate property)
    """
    name = subject[:100] if subject else "Email Triage"
    
    # Include date in content body (database doesn't have separate Date property)
    date_str = f"Date: {email_date[:10]}\n" if email_date else ""
    content = f"{date_str}From: {sender} ({account})\n\n{body}"

    return {
        "parent": {"database_id": NOTION_TRIAGE_DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": name}}]},
            "Payload": {"rich_text": [{"text": {"content": content}}]},
            "Source": {"select": {"name": "Email Backfill"}},
            "Status": {"select": {"name": "New"}},
        },
    }


def send_to_notion(payload: dict, notion_api_key: str) -> bool:
    """Send payload directly to Notion API."""
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    try:
        response = httpx.post(NOTION_API_URL, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            page_id = result.get("id", "unknown")
            print(f"     📬 → Notion (Page ID: {page_id})")
            return True
        else:
            print(f"     ⚠️  Notion API: {response.status_code} - {response.text[:100]}")
            return False
    except Exception as e:
        print(f"     ❌ Notion error: {e}")
        return False


# ============================================================================
# IMAP Connection Functions
# ============================================================================


def connect_proton(email_addr: str, password: str):
    """Connect to Proton Bridge (STARTTLS on port 1143)."""
    mail = imaplib.IMAP4(PROTON_HOST, PROTON_PORT)
    mail.starttls(ssl_context=PROTON_SSL_CONTEXT)
    mail.login(email_addr, password)
    return mail


def connect_gmail(email_addr: str, password: str):
    """Connect to Gmail (IMAP SSL on port 993)."""
    mail = imaplib.IMAP4_SSL(GMAIL_HOST, GMAIL_PORT, ssl_context=GMAIL_SSL_CONTEXT)
    mail.login(email_addr, password)
    return mail


# ============================================================================
# State Management
# ============================================================================


def load_state() -> Dict:
    """Load backfill state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {"processed_ids": [], "last_run": None}


def save_state(state: Dict):
    """Save backfill state."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ============================================================================
# Main Backfill Logic
# ============================================================================


def backfill_account(email_addr: str, password: str, mail, state: Dict, notion_api_key: str) -> Dict:
    """Backfill a single account."""
    stats = {"total": 0, "processed": 0, "skipped": 0, "notion": 0, "rule_keep": 0, "llm_keep": 0}

    try:
        mail.select("INBOX")

        # Search emails SINCE 25-Dec-2025 (IMAP-level date filtering)
        status, messages = mail.search(None, '(SINCE "25-Dec-2025")')
        if status != "OK":
            print(f"  ❌ Search failed")
            return stats

        email_ids = messages[0].split()
        stats["total"] = len(email_ids)

        print(f"  📬 Found {len(email_ids)} emails since 25-Dec-2025 in INBOX")

        # Apply test mode batch limit
        if TEST_MODE:
            email_ids = email_ids[-TEST_BATCH_SIZE:]
            print(f"  🧪 TEST MODE: Processing up to {TEST_BATCH_SIZE} emails")

        # Process emails (no limit in production, limited in test mode)
        processed_count = 0
        for email_id in reversed(email_ids):
            email_id_str = email_id.decode()
            state_key = f"{email_addr}:{email_id_str}"

            # Skip if already processed
            if state_key in state["processed_ids"]:
                stats["skipped"] += 1
                continue

            # Fetch full email with BODY.PEEK[] (doesn't mark as read)
            status, msg_data = mail.fetch(email_id, "(BODY.PEEK[])")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Extract headers
            raw_subject = msg.get("Subject", "")
            raw_from = msg.get("From", "")
            subject = decode_header_value(raw_subject)
            sender = decode_header_value(raw_from)

            # Extract and parse date
            raw_date = msg.get("Date", "")
            email_date_iso = None
            try:
                email_date = email.utils.parsedate_to_datetime(raw_date)
                email_date_iso = email_date.isoformat()
            except Exception:
                pass  # Date parsing failed, continue without date

            # Extract clean body (text/plain preferred, HTML stripped if needed)
            body = extract_email_body(msg)

            if not body:
                stats["skipped"] += 1
                state["processed_ids"].append(state_key)
                continue

            stats["processed"] += 1
            processed_count += 1

            # Hybrid Triage
            print(f"  🔍 [{processed_count}] {subject[:50]}...")
            method, should_keep = triage_email(subject, sender, body)

            if not should_keep:
                print(f"    🚫 Skipped by {method}")
                stats["skipped"] += 1
                state["processed_ids"].append(state_key)
                continue

            if method == "Rule":
                print(f"    ✅ [Rule] - KEEP")
                stats["rule_keep"] += 1
            else:
                print(f"    ✅ [LLM] - KEEP")
                stats["llm_keep"] += 1

            # Send to Notion with date
            payload = create_notion_payload(subject, sender, body, email_addr, email_date_iso)
            success = send_to_notion(payload, notion_api_key)

            if success:
                stats["notion"] += 1
            else:
                print(f"    ❌ Failed to send to Notion")

            state["processed_ids"].append(state_key)

            # Rate limiting (Notion allows ~3 requests/second)
            if processed_count % 10 == 0:
                print(f"  ⏱️  Rate limit pause...")
                time.sleep(1)

        mail.close()
        mail.logout()

    except Exception as e:
        print(f"  ❌ Error: {e}")

    return stats


def main():
    print("=" * 70)
    print("  ARCA Email Backfill - Hybrid Triage + Direct Notion API")
    print("  From: Dec 25, 2025 → Present")
    if TEST_MODE:
        print("  🧪 TEST MODE: arca-vsa.tech accounts only, 50 emails each")
    print("=" * 70)
    print()

    # Load Credentials API key
    api_key = load_credentials_api_key()
    if not api_key:
        print("❌ CREDENTIALS_API_KEY not found!")
        print(f"   Run: echo -n 'YOUR_KEY' > {CREDENTIALS_API_KEY_FILE}")
        return False
    print(f"✅ Credentials API key loaded")

    # Fetch Notion API key
    notion_api_key = fetch_secret("notion-api-key")
    if not notion_api_key:
        print("❌ Notion API key not found!")
        print("   Ensure Credentials Server is running and has 'notion-api-key'")
        return False
    print(f"✅ Notion API Key loaded: {notion_api_key[:10]}...")

    # Load state (fresh start for clean run)
    if STATE_FILE.exists():
        print(f"🗑️  Deleting existing state file for clean run...")
        STATE_FILE.unlink()

    state = load_state()
    print(f"✅ State initialized (clean run)")
    print()

    # Show test mode accounts
    if TEST_MODE:
        print(f"📧 Test Mode Accounts ({len(ACCOUNTS)}):")
        for acc in ACCOUNTS:
            print(f"   - {acc['email']}")
        print()

    # Check LLM
    print("📋 Checking LLM...")
    try:
        client = openai.OpenAI(base_url=LOCAL_LLM_BASE_URL, api_key="test")
        client.models.list()
        print(f"✅ LLM available at {LOCAL_LLM_BASE_URL}")
    except:
        print(f"⚠️  LLM not available, will use rule-based filtering only")
    print()

    # Backfill each account
    total_stats = {"total": 0, "processed": 0, "skipped": 0, "notion": 0, "rule_keep": 0, "llm_keep": 0}

    for acc in ACCOUNTS:
        email_addr = acc["email"]
        acc_type = acc["type"]
        secret_name = acc["secret"]

        print(f"\n{'='*70}")
        print(f"📧 Backfilling: {email_addr} ({acc_type.upper()})")
        print(f"{'='*70}")

        # Fetch password from Credentials Server
        password = fetch_secret(secret_name)
        if not password:
            print(f"  ⚠️  Skipping - could not fetch secret: {secret_name}")
            continue

        # Connect to IMAP
        try:
            if acc_type == "proton":
                mail = connect_proton(email_addr, password)
            else:
                mail = connect_gmail(email_addr, password)
            print(f"  ✅ Connected")
        except Exception as e:
            print(f"  ❌ Connection error: {e}")
            continue

        # Backfill account
        stats = backfill_account(email_addr, password, mail, state, notion_api_key)

        print(f"\n📊 Stats for {email_addr}:")
        print(f"   Total: {stats['total']}")
        print(f"   Processed: {stats['processed']}")
        print(f"   Skipped (old/empty): {stats['skipped']}")
        print(f"   ✅ Rule KEEP: {stats['rule_keep']}")
        print(f"   ✅ LLM KEEP: {stats['llm_keep']}")
        print(f"   📬 Sent to Notion: {stats['notion']}")

        for key in total_stats:
            total_stats[key] += stats[key]

        # Save state after each account
        state["last_run"] = datetime.now().isoformat()
        save_state(state)

    # Final summary
    print("\n" + "=" * 70)
    print("  BACKFILL COMPLETE")
    print("=" * 70)
    print(f"\n📊 Total Statistics:")
    print(f"   Total emails scanned: {total_stats['total']}")
    print(f"   Processed: {total_stats['processed']}")
    print(f"   Skipped (old/empty): {total_stats['skipped']}")
    print(f"   ✅ Rule KEEP: {total_stats['rule_keep']}")
    print(f"   ✅ LLM KEEP: {total_stats['llm_keep']}")
    print(f"   📬 Sent to Notion: {total_stats['notion']}")
    print()
    print(f"💾 State saved to: {STATE_FILE}")
    print()

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
