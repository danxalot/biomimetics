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
import certifi
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from email_utils import apply_filtering_rules, update_sent_whitelist, extract_email_body, send_to_notion, process_and_save_email

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
JUNK_CACHE_FILE = Path.home() / ".arca" / "junk_cache.json"

# SSL context for Proton Bridge (self-signed cert)
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Gmail SSL context - Use certifi for macOS compatibility
GMAIL_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

def add_to_junk_cache(email_data: dict, reason: str):
    """Save rejected email metadata to a local JSON cache for later review"""
    try:
        cache_data = []
        if JUNK_CACHE_FILE.exists():
            with open(JUNK_CACHE_FILE, "r") as f:
                try:
                    cache_data = json.load(f)
                except:
                    cache_data = []
        
        # Create snippet (first 200 chars)
        snippet = email_data.get("body", "")[:200].replace("\n", " ")
        
        entry = {
            "date": email_data.get("received_at", datetime.now().isoformat()),
            "sender": email_data.get("from", "Unknown"),
            "subject": email_data.get("subject", "No Subject"),
            "reason": reason,
            "snippet": snippet
        }
        
        cache_data.append(entry)
        
        # Keep only last 1000 rejected emails
        cache_data = cache_data[-1000:]
        
        with open(JUNK_CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)
            
    except Exception as e:
        print(f"  ⚠️  Failed to update junk cache: {e}")

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
        self.data = {}
        self.processed_ids = set()
        self.load()

    def load(self):
        try:
            with open(self.state_file) as f:
                self.data = json.load(f)
                self.processed_ids = set(self.data.get("processed_ids", []))
        except:
            self.data = {}
            self.processed_ids = set()

    def save(self):
        # Keep only last 10000 IDs to prevent unbounded growth
        ids_list = list(self.processed_ids)[-10000:]
        self.data["processed_ids"] = ids_list
        with open(self.state_file, "w") as f:
            json.dump(self.data, f)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def is_processed(self, email_id: str) -> bool:
        return email_id in self.processed_ids

    def mark_processed(self, email_id: str):
        self.processed_ids.add(email_id)
        self.save()


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
        else:
            # ProtonMail: Attempt STARTTLS upgrade on 1143
            host = CONFIG.get("PROTONMAIL_IMAP_HOST", "127.0.0.1")
            port = CONFIG.get("PROTONMAIL_IMAP_PORT", 1143)
            try:
                mail = imaplib.IMAP4(host, port)
                mail.starttls(ssl_context=SSL_CONTEXT)
            except Exception as e:
                print(f"  ⚠️  STARTTLS on {port} failed, trying IMAP4_SSL on 993: {e}")
                # Fallback to IMAP4_SSL on port 993
                mail = imaplib.IMAP4_SSL(host, 993, ssl_context=SSL_CONTEXT)

        # IMAP Login Backoff / Retry Block
        for attempt in range(3):
            try:
                mail.login(email_addr, password)
                return mail
            except imaplib.IMAP4.error as e:
                if b"too many login attempts" in str(e).lower().encode():
                    print(f"  ⏳ Too many login attempts for {email_addr}. Backing off 15s (Attempt {attempt+1}/3)...")
                    time.sleep(15)
                else:
                    raise e
        
        return None
        
    except imaplib.IMAP4.error as e:
        print(f"❌ [{protocol.upper()}] IMAP error for {email_addr}: {e}")
        return None
    except Exception as e:
        print(f"❌ [{protocol.upper()}] Connection error for {email_addr}: {e}")
        return None


def poll_account(account: Dict, state: EmailState, lookback_minutes: int = 5, start_date: str = None, end_date: str = None) -> List[dict]:
    """
    Poll a single email account (ProtonMail or Gmail) for new emails.
    Uses dual-protocol connection factory.
    """
    email_addr = account["email"]
    protocol = account.get("protocol", "proton")
    emails_processed = []

    # Connect using dual-protocol factory
    mail = connect_imap(account)
    if not mail:
        return []

    # Update Sent Whitelist before polling Inbox
    update_sent_whitelist(mail, email_addr, state.data)
    state.save()

    try:
        mail.select("INBOX")

        # Determine Search Query
        if start_date and end_date:
            # Batch mode: YYYY-MM-DD -> DD-Mon-YYYY
            sd = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d-%b-%Y")
            ed = datetime.strptime(end_date, "%Y-%m-%d").strftime("%d-%b-%Y")
            search_query = f'(SINCE {sd} BEFORE {ed})'
        else:
            # Default: incremental poll
            since_date = (datetime.now() - timedelta(minutes=lookback_minutes * 2)).strftime("%d-%b-%Y")
            search_query = f'(UNSEEN SINCE {since_date})'

        status, messages = mail.search(None, search_query)

        if status != "OK":
            mail.close()
            mail.logout()
            return []

        email_ids = messages[0].split()

        for email_id in email_ids:
            email_id_str = email_id.decode()

            if state.is_processed(f"{email_addr}:{email_id_str}"):
                continue

            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = str(msg.get("Subject", "No Subject"))
            sender = str(msg.get("From", "Unknown"))
            message_id = str(msg.get("Message-ID", ""))
            date_str = str(msg.get("Date", ""))
            list_unsubscribe = str(msg.get("List-Unsubscribe", ""))
            body = extract_email_body(msg)

            action, reason = apply_filtering_rules(subject, sender, list_unsubscribe, body)

            if action == "hard_refuse":
                print(f"  🛑 [HARD REFUSE] {subject[:50]}...")
                state.mark_processed(f"{email_addr}:{email_id_str}")
                continue
            
            if action in ["reject", "review"]:
                print(f"  🔴 [{action.upper()}] {reason}: {subject[:50]}...")
                add_to_junk_cache({
                    "from": sender, "subject": subject, "received_at": date_str, "body": body
                }, reason)
                state.mark_processed(f"{email_addr}:{email_id_str}")
                continue

            print(f"  🟢 [PASS - {reason}] {subject[:50]}...")

            if not body:
                state.mark_processed(f"{email_addr}:{email_id_str}")
                continue

            # --- AUTO-READ ROUTING LOGIC ---
            subject_lower = subject.lower()
            is_auto_read = (
                "recycling collection" in subject_lower
                or "security alert" in subject_lower
                or "login from a new device" in subject_lower
                or ("new" in subject_lower and "login" in subject_lower)
                or ("verify" in subject_lower and "login" in subject_lower)
                or ("delivered" in subject_lower and "items" in subject_lower)
            )
            notion_status = "Read" if is_auto_read else "New"

            # Use centralized processing and saving
            output_dir = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "staging"
            notion_metadata, filepath = process_and_save_email(
                raw_email, 
                email_id_str, 
                output_dir, 
                email_addr, 
                notion_status
            )

            print(f"💾 Saved to Staging: {filepath.name}")
            send_to_notion(notion_metadata)
            print(f"🔔 Triage notification sent ({'Read (auto-routed)' if is_auto_read else 'New'})")
            time.sleep(0.5)

            state.mark_processed(f"{email_addr}:{email_id_str}")

            emails_processed.append({
                "id": email_id_str,
                "account": email_addr,
                "protocol": protocol,
                "subject": subject,
                "from": sender
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


def poll_all_accounts(state: EmailState, lookback_minutes: int = 5, start_date: str = None, end_date: str = None) -> List[dict]:
    """Poll all ProtonMail and Gmail accounts"""
    all_results = []
    
    proton_accounts, gmail_accounts = load_accounts()
    
    print(f"\n📧 Polling {len(proton_accounts)} ProtonMail account(s)...")
    for account in proton_accounts:
        results = poll_account(account, state, lookback_minutes, start_date, end_date)
        all_results.extend(results)
        time.sleep(5)
    
    if gmail_accounts:
        print(f"\n📧 Polling {len(gmail_accounts)} Gmail account(s)...")
        for account in gmail_accounts:
            results = poll_account(account, state, lookback_minutes, start_date, end_date)
            all_results.extend(results)
            time.sleep(5)
    
    return all_results


def main():
    """Main daemon loop"""
    parser = argparse.ArgumentParser(description="Email Ingestion Daemon - Dual Protocol")
    parser.add_argument("--once", action="store_true", help="Run single poll then exit")
    parser.add_argument("--lookback", type=int, default=5, help="Look back minutes for unread emails")
    parser.add_argument("--start-date", type=str, help="Batch start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="Batch end date (YYYY-MM-DD)")
    args = parser.parse_args()

    proton_accounts, gmail_accounts = load_accounts()

    print("=" * 60)
    print("📧 Email Ingestion Daemon - Dual Protocol")
    print("=" * 60)
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

    state = EmailState(STATE_FILE)
    print(f"Loaded {len(state.processed_ids)} processed email IDs from state")

    iteration = 0
    while True:
        iteration += 1
        print(f"\n--- Poll iteration {iteration} at {datetime.now().isoformat()} ---")

        all_results = poll_all_accounts(
            state, 
            lookback_minutes=args.lookback,
            start_date=args.start_date,
            end_date=args.end_date
        )
        
        proton_count = len([r for r in all_results if r.get('protocol') == 'proton'])
        gmail_count = len([r for r in all_results if r.get('protocol') == 'gmail'])
        
        print(f"\n📊 Summary:")
        print(f"  ProtonMail: {proton_count} new emails")
        print(f"  Gmail: {gmail_count} new emails")
        print(f"  Total: {len(all_results)}")

        if args.once:
            print("\n👋 Single poll mode - exiting")
            break

        print(f"\n⏱️  Sleeping for {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Daemon stopped by user")
        sys.exit(0)
