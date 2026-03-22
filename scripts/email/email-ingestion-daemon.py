#!/usr/bin/env python3
"""
Email Ingestion Daemon - Dual-Protocol Edition
Polls ProtonMail (STARTTLS:1143) and Gmail (IMAP4_SSL:993) accounts
Forwards to Cloud Function Gateway for memory storage

Usage:
    python3 email-ingestion-daemon.py              # Continuous daemon mode
    python3 email-ingestion-daemon.py --once       # Single poll then exit
"""

import os
import sys
import json
import time
import imaplib
import email
import ssl
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import httpx

# Configuration paths
CONFIG_FILE = Path.home() / "biomimetics" / "config" / "omni_sync_config.json"
SECRETS_DIR = Path.home() / "biomimetics" / "secrets"
PROTON_BRIDGE_PASSWORD_FILE = SECRETS_DIR / "proton_bridge_password"

# Load configuration from file
def load_config() -> Dict:
    """Load configuration from omni_sync_config.json"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

CONFIG = load_config()

# GCP Gateway configuration
GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    CONFIG.get("GCP_GATEWAY_URL", "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator")
)

WEBHOOK_RECEIVER_URL = os.environ.get(
    "WEBHOOK_RECEIVER_URL",
    "http://localhost:8000/email"
)

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", CONFIG.get("NOTION_API_KEY", ""))
NOTION_EMAIL_DB_ID = os.environ.get("NOTION_EMAIL_DB_ID", "")

# Polling interval (seconds)
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", str(CONFIG.get("EMAIL_POLL_INTERVAL", 300))))

# State file for tracking processed emails
STATE_FILE = Path.home() / ".arca" / "email_state.json"

# SSL context for Proton Bridge (self-signed cert)
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Gmail SSL context
GMAIL_SSL_CONTEXT = ssl.create_default_context()


def load_proton_password() -> str:
    """Load Proton Bridge password from secrets file."""
    if PROTON_BRIDGE_PASSWORD_FILE.exists():
        return PROTON_BRIDGE_PASSWORD_FILE.read_text().strip()
    return os.environ.get("PROTON_BRIDGE_PASSWORD", "")


def load_accounts() -> Tuple[List[Dict], List[Dict]]:
    """
    Load ProtonMail and Gmail accounts from config.
    Returns: (proton_accounts, gmail_accounts)
    """
    proton_accounts = []
    gmail_accounts = []
    
    # Load ProtonMail accounts
    proton_accounts_config = CONFIG.get("PROTONMAIL_ACCOUNTS", [])
    proton_password = load_proton_password()
    
    for acct in proton_accounts_config:
        proton_accounts.append({
            "email": acct.get("email", ""),
            "password": acct.get("password", proton_password),
            "protocol": "proton"
        })
    
    # Load Gmail account(s)
    if CONFIG.get("GMAIL_ENABLED", False):
        gmail_accounts.append({
            "email": CONFIG.get("GMAIL_USER", ""),
            "password": CONFIG.get("GMAIL_APP_PASSWORD", ""),
            "host": CONFIG.get("GMAIL_IMAP_HOST", "imap.gmail.com"),
            "port": CONFIG.get("GMAIL_IMAP_PORT", 993),
            "protocol": "gmail"
        })
    
    return proton_accounts, gmail_accounts


class EmailState:
    """Track processed email IDs to avoid duplicates"""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.processed_ids = set()
        self.load()

    def load(self):
        try:
            with open(self.state_file) as f:
                data = json.load(f)
                self.processed_ids = set(data.get("processed_ids", []))
        except:
            self.processed_ids = set()

    def save(self):
        # Keep only last 10000 IDs to prevent unbounded growth
        ids_list = list(self.processed_ids)[-10000:]
        with open(self.state_file, "w") as f:
            json.dump({"processed_ids": ids_list}, f)

    def is_processed(self, email_id: str) -> bool:
        return email_id in self.processed_ids

    def mark_processed(self, email_id: str):
        self.processed_ids.add(email_id)
        self.save()


def extract_email_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message, stripping HTML"""
    body = ""

    if msg.is_multipart():
        # Prefer plain text over HTML
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            # Skip attachments
            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                try:
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                except:
                    pass
            elif content_type == "text/html" and not body:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    # Strip HTML tags
                    body = re.sub(r"<[^>]+>", "", body)
                except:
                    pass
    else:
        # Single part message
        try:
            charset = msg.get_content_charset() or "utf-8"
            body = msg.get_payload(decode=True).decode(charset, errors="replace")
        except:
            body = str(msg.get_payload())

    return body.strip()


def send_to_webhook_receiver(email_data: dict) -> dict:
    """Send email to local webhook receiver"""
    try:
        response = httpx.post(
            WEBHOOK_RECEIVER_URL,
            json=email_data,
            headers={"Content-Type": "application/json"},
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def send_to_notion(email_data: dict) -> dict:
    """Send email tracking to Notion database"""
    if not NOTION_API_KEY or not NOTION_EMAIL_DB_ID:
        return {"skipped": "Notion not configured"}

    try:
        response = httpx.post(
            "https://api.notion.com/v1/pages",
            headers={
                "Authorization": f"Bearer {NOTION_API_KEY}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            },
            json={
                "parent": {"database_id": NOTION_EMAIL_DB_ID},
                "properties": {
                    "Type": {"title": [{"text": {"content": "Email"}}]},
                    "From": {"rich_text": [{"text": {"content": email_data.get("from", "")}}]},
                    "Subject": {"rich_text": [{"text": {"content": email_data.get("subject", "")}}]},
                    "Received": {"date": {"start": email_data.get("received_at", "")}},
                    "Message-ID": {"rich_text": [{"text": {"content": email_data.get("message_id", "")}}]}
                }
            },
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def connect_imap(account: Dict) -> Optional[imaplib.IMAP4]:
    """
    Dual-protocol IMAP connection factory.
    
    - ProtonMail: Uses IMAP4 + STARTTLS on port 1143
    - Gmail: Uses IMAP4_SSL on port 993
    
    Returns: IMAP connection object or None on failure
    """
    protocol = account.get("protocol", "proton")
    email_addr = account.get("email", "")
    password = account.get("password", "")
    
    try:
        if protocol == "gmail":
            # Gmail: Implicit SSL via IMAP4_SSL
            host = account.get("host", "imap.gmail.com")
            port = account.get("port", 993)
            
            mail = imaplib.IMAP4_SSL(host, port, ssl_context=GMAIL_SSL_CONTEXT)
            mail.login(email_addr, password)
            
        else:  # proton or default
            # ProtonMail: STARTTLS upgrade
            host = CONFIG.get("PROTONMAIL_IMAP_HOST", "127.0.0.1")
            port = CONFIG.get("PROTONMAIL_IMAP_PORT", 1143)
            
            mail = imaplib.IMAP4(host, port)
            mail.starttls(ssl_context=SSL_CONTEXT)
            mail.login(email_addr, password)
        
        return mail
        
    except imaplib.IMAP4.error as e:
        print(f"❌ [{protocol.upper()}] IMAP error for {email_addr}: {e}")
        return None
    except Exception as e:
        print(f"❌ [{protocol.upper()}] Connection error for {email_addr}: {e}")
        return None


def poll_account(account: Dict, state: EmailState, lookback_minutes: int = 5) -> List[dict]:
    """
    Poll a single email account (ProtonMail or Gmail) for new emails.
    Uses dual-protocol connection factory.
    """
    email_addr = account["email"]
    password = account["password"]
    protocol = account.get("protocol", "proton")
    emails_processed = []

    # Connect using dual-protocol factory
    mail = connect_imap(account)
    if not mail:
        return []

    try:
        mail.select("INBOX")

        # Search for unread emails from last poll
        since_date = (datetime.now() - timedelta(minutes=lookback_minutes * 2)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(UNSEEN SINCE {since_date})')

        if status != "OK":
            mail.close()
            mail.logout()
            return []

        email_ids = messages[0].split()

        for email_id in email_ids:
            email_id_str = email_id.decode()

            # Skip if already processed
            if state.is_processed(f"{email_addr}:{email_id_str}"):
                continue

            # Fetch email
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue

            # Parse email
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Extract data
            subject = msg.get("Subject", "No Subject")
            sender = msg.get("From", "Unknown")
            message_id = msg.get("Message-ID", "")
            date_str = msg.get("Date", "")

            # Extract body (strips HTML for both Proton and Gmail)
            body = extract_email_body(msg)

            if not body:
                state.mark_processed(f"{email_addr}:{email_id_str}")
                continue

            # Create email data
            email_data = {
                "subject": subject,
                "from": sender,
                "message_id": message_id,
                "received_at": date_str,
                "body": body,
                "source": protocol,
                "account": email_addr
            }

            # Send to webhook receiver
            result = send_to_webhook_receiver(email_data)

            # Also send to Notion if configured
            if NOTION_API_KEY:
                notion_result = send_to_notion(email_data)

            # Mark as processed
            state.mark_processed(f"{email_addr}:{email_id_str}")

            emails_processed.append({
                "id": email_id_str,
                "account": email_addr,
                "protocol": protocol,
                "subject": subject,
                "from": sender,
                "result": result
            })

            print(f"✅ [{protocol.upper()}] {email_addr}: {subject[:50]}...")

        mail.close()
        mail.logout()

    except Exception as e:
        print(f"❌ [{protocol.upper()}] Error processing emails for {email_addr}: {e}")
        try:
            mail.logout()
        except:
            pass

    return emails_processed


def poll_all_accounts(state: EmailState, lookback_minutes: int = 5) -> List[dict]:
    """Poll all ProtonMail and Gmail accounts"""
    all_results = []
    
    proton_accounts, gmail_accounts = load_accounts()
    
    print(f"\n📧 Polling {len(proton_accounts)} ProtonMail account(s)...")
    for account in proton_accounts:
        results = poll_account(account, state, lookback_minutes)
        all_results.extend(results)
    
    if gmail_accounts:
        print(f"\n📧 Polling {len(gmail_accounts)} Gmail account(s)...")
        for account in gmail_accounts:
            results = poll_account(account, state, lookback_minutes)
            all_results.extend(results)
    
    return all_results


def main():
    """Main daemon loop"""
    parser = argparse.ArgumentParser(description="Email Ingestion Daemon - Dual Protocol")
    parser.add_argument("--once", action="store_true", help="Run single poll then exit")
    parser.add_argument("--lookback", type=int, default=5, help="Look back minutes for unread emails")
    args = parser.parse_args()

    # Load accounts
    proton_accounts, gmail_accounts = load_accounts()

    print("=" * 60)
    print("📧 Email Ingestion Daemon - Dual Protocol")
    print("=" * 60)
    print(f"Gateway: {GCP_GATEWAY_URL}")
    print(f"Webhook Receiver: {WEBHOOK_RECEIVER_URL}")
    print(f"Poll Interval: {POLL_INTERVAL}s")
    print(f"ProtonMail: {CONFIG.get('PROTONMAIL_IMAP_HOST', '127.0.0.1')}:{CONFIG.get('PROTONMAIL_IMAP_PORT', 1143)} (STARTTLS)")
    print(f"Gmail: {CONFIG.get('GMAIL_IMAP_HOST', 'imap.gmail.com')}:{CONFIG.get('GMAIL_IMAP_PORT', 993)} (SSL)")
    print(f"\nAccounts:")
    print(f"  ProtonMail: {len(proton_accounts)}")
    for acct in proton_accounts:
        print(f"    - {acct['email']}")
    print(f"  Gmail: {len(gmail_accounts)}")
    for acct in gmail_accounts:
        print(f"    - {acct['email']}")
    print(f"\nNotion: {'configured' if NOTION_API_KEY else 'not configured'}")
    print(f"Mode: {'single poll' if args.once else 'continuous daemon'}")
    print("=" * 60)

    # Initialize state
    state = EmailState(STATE_FILE)
    print(f"Loaded {len(state.processed_ids)} processed email IDs from state")

    # Main loop
    iteration = 0
    while True:
        iteration += 1
        print(f"\n--- Poll iteration {iteration} at {datetime.now().isoformat()} ---")

        # Poll all accounts
        all_results = poll_all_accounts(state, lookback_minutes=args.lookback)
        
        # Summary by protocol
        proton_count = len([r for r in all_results if r.get('protocol') == 'proton'])
        gmail_count = len([r for r in all_results if r.get('protocol') == 'gmail'])
        
        print(f"\n📊 Summary:")
        print(f"  ProtonMail: {proton_count} new emails")
        print(f"  Gmail: {gmail_count} new emails")
        print(f"  Total: {len(all_results)}")

        if args.once:
            print("\n👋 Single poll mode - exiting")
            break

        # Wait for next poll
        print(f"\n⏱️  Sleeping for {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Daemon stopped by user")
        sys.exit(0)
