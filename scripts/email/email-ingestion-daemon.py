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
import certifi
from bs4 import BeautifulSoup

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


# --- Legacy Filter & Triage Logic ---
KEEP_KEYWORDS = [
    "invoice", "receipt", "you sent", "payment", "octopus", "vultr", "azure", "ticket",
    "order", "document", "citizens advice", "cab", "debt", "arrears", "collection",
    "bailiff", "stepchange", "credit", "complaint", "appeal", "ombudsman", "watchdog",
    "legal", "solicitor", "police", "council", "security alert", "breach", "pwned",
    "unauthorized", "login",
]
PATTERN = re.compile(r"\b(?:" + "|".join(map(re.escape, KEEP_KEYWORDS)) + r")\b", re.IGNORECASE)

INSTITUTIONAL_DOMAINS = ["nhs.net", "nhs.uk", "gov.uk", "police.uk", "lgo.org.uk"]
INSTITUTIONAL_KEYWORDS = ["citizens advice", "solicitor", "lawyer", "legal", "constabulary", "police"]
HARD_REFUSE_PHRASES = ["that you follow published a new idea"]

WHITELIST_FILE = Path.home() / "biomimetics" / "config" / "email_whitelist.json"

def load_whitelist() -> set:
    if WHITELIST_FILE.exists():
        with open(WHITELIST_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_whitelist(whitelist: set):
    with open(WHITELIST_FILE, "w") as f:
        json.dump(list(whitelist), f)

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

def update_sent_whitelist(mail_client, account_email, state):
    """Scan Sent folder and add recipients to whitelist"""
    try:
        # Task 1: Dynamic IMAP Sent Folder Discovery
        sent_folder = None
        
        # Method A: Use mail.list() to find folder with \Sent flag
        status, folder_list = mail_client.list()
        if status == 'OK':
            for line in folder_list:
                line_str = line.decode('utf-8')
                # Check for \Sent flag (case-insensitive)
                if '\\sent' in line_str.lower():
                    # Extract folder name (usually the last part after the delimiter)
                    import re
                    match = re.search(r'\(.*\) "/" "(.*)"', line_str)
                    if not match:
                        match = re.search(r'\(.*\) "." "(.*)"', line_str)
                    
                    if match:
                        sent_folder = f'"{match.group(1)}"'
                        break
        
        # Method B: Robust Fallback Loop
        if not sent_folder:
            fallbacks = ['"[Gmail]/Sent Mail"', '"[Google Mail]/Sent Mail"', '"Sent"', '"Sent Mail"']
            for fb in fallbacks:
                status, _ = mail_client.select(fb, readonly=True)
                if status == 'OK':
                    sent_folder = fb
                    break
        
        if not sent_folder:
            print(f"  ⚠️  Could not discover Sent folder for {account_email}")
            return

        # EXPLICIT SELECT & VERIFY
        status, data = mail_client.select(sent_folder, readonly=True)
        if status != 'OK':
            print(f"  ⚠️  Failed to select {sent_folder}: {data}")
            return


        
        last_check = state.get(f"last_sent_check_{account_email}")
        if last_check:
            since_date = datetime.strptime(last_check, "%Y-%m-%d").strftime("%d-%b-%Y")
        else:
            since_date = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
        
        status, messages = mail_client.search(None, f'(SINCE {since_date})')
        if status != "OK": return
        
        whitelist = load_whitelist()
        new_entries = 0
        
        for e_id in messages[0].split():
            status, msg_data = mail_client.fetch(e_id, "(RFC822.HEADER)")
            if status != "OK": continue
            msg = email.message_from_bytes(msg_data[0][1])
            to_addr = msg.get("To", "")
            # Extract email addresses using regex
            addrs = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', to_addr)
            for addr in addrs:
                if addr.lower() not in whitelist:
                    whitelist.add(addr.lower())
                    new_entries += 1
        
        if new_entries > 0:
            save_whitelist(whitelist)
            print(f"  📝 Whitelist updated: +{new_entries} new recipients")
            
        state[f"last_sent_check_{account_email}"] = datetime.now().strftime("%Y-%m-%d")
        
    except Exception as e:
        print(f"  ⚠️  Failed to update sent whitelist: {e}")

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


def extract_email_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message.
    
    Priority: text/html (with style/script stripping) > text/plain.
    Traverses multipart trees to find the best HTML part first.
    Falls back gracefully to text/plain if no HTML exists.
    """
    html_body = ""
    plain_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            # Skip attachments
            if "attachment" in content_disposition:
                continue

            if content_type == "text/html" and not html_body:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    raw_html = part.get_payload(decode=True).decode(charset, errors="replace")
                    soup = BeautifulSoup(raw_html, "html.parser")
                    # Deep cleanse: remove style and script tags to prevent code-clumping
                    for tag in soup.find_all(["style", "script"]):
                        tag.decompose()
                    html_body = soup.get_text(separator="\n", strip=True)
                except Exception:
                    pass

            elif content_type == "text/plain" and not plain_body:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    plain_body = part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    pass

        # Prefer HTML result; fall back to plain text
        body = html_body if html_body else plain_body

    else:
        # Single-part message — attempt decode directly
        content_type = msg.get_content_type()
        try:
            charset = msg.get_content_charset() or "utf-8"
            raw = msg.get_payload(decode=True).decode(charset, errors="replace")
            if content_type == "text/html":
                soup = BeautifulSoup(raw, "html.parser")
                for tag in soup.find_all(["style", "script"]):
                    tag.decompose()
                body = soup.get_text(separator="\n", strip=True)
            else:
                body = raw
        except Exception:
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
    """Rerouted: Send email metadata to local webhook translator for Notion dashboard"""
    try:
        response = httpx.post(
            WEBHOOK_RECEIVER_URL,
            json=email_data,
            headers={"Content-Type": "application/json"},
            timeout=15.0
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
    password = account["password"]
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
            # Enforce 15 RPM limit (4s heartbeat) for Notion API safety
            time.sleep(4)
            
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

            # Extract headers for triage
            subject = str(msg.get("Subject", "No Subject"))
            sender = str(msg.get("From", "Unknown"))
            message_id = str(msg.get("Message-ID", ""))
            date_str = str(msg.get("Date", ""))
            list_unsubscribe = str(msg.get("List-Unsubscribe", ""))

            # --- TRIAGE HIERARCHY ---
            pass_reason = None
            
            # 0. Hard Refusal (Silent Drop)
            if any(phrase.lower() in subject.lower() for phrase in HARD_REFUSE_PHRASES):
                print(f"  🛑 [HARD REFUSE] {subject[:50]}...")
                state.mark_processed(f"{email_addr}:{email_id_str}")
                continue

            # 1. Institutional Check
            sender_domain = sender.split("@")[-1].strip(">").lower()
            if any(dom in sender_domain for dom in INSTITUTIONAL_DOMAINS) or \
               any(kw.lower() in sender.lower() for kw in INSTITUTIONAL_KEYWORDS):
                pass_reason = "Institutional"
            
            # 2. Whitelist Check
            if not pass_reason:
                whitelist = load_whitelist()
                sender_addr = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', sender)
                if sender_addr and sender_addr[0].lower() in whitelist:
                    pass_reason = "Whitelisted"
            
            # 3. Newsletter Check (REJECT)
            if not pass_reason and list_unsubscribe:
                print(f"  🔴 [REJECT] Newsletter: {subject[:50]}...")
                add_to_junk_cache({
                    "from": sender, "subject": subject, "received_at": date_str, "body": extract_email_body(msg)
                }, "Newsletter")
                state.mark_processed(f"{email_addr}:{email_id_str}")
                continue
            
            # 4. Legacy Keyword Filter
            if not pass_reason:
                if PATTERN.search(f"{subject} {sender}"):
                    pass_reason = "Legacy Filter"
            
            if not pass_reason:
                print(f"  🔴 [REJECT] Failed Triage: {subject[:50]}...")
                add_to_junk_cache({
                    "from": sender, "subject": subject, "received_at": date_str, "body": extract_email_body(msg)
                }, "Triage Failure")
                state.mark_processed(f"{email_addr}:{email_id_str}")
                continue

            print(f"  🟢 [PASS - {pass_reason}] {subject[:50]}...")

            # Extract body (strips HTML for both Proton and Gmail)
            body = extract_email_body(msg)

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

            # Create email data
            email_data = {
                "subject": subject,
                "from": sender,
                "message_id": message_id,
                "received_at": date_str,
                "body": body,
                "source": protocol,
                "account": email_addr,
                "recipient": email_addr
            }

            # Local-First Markdown Drop (Enforce Local-First / Context-Lock)
            # Directed to STAGING for triage
            output_dir = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "staging"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize filename: YYYY-MM-DD_Sanitized_Subject.md
            # Extract date for filename (try to parse email date, fallback to now)
            try:
                dt = email.utils.parsedate_to_datetime(date_str)
                date_prefix = dt.strftime("%Y-%m-%d")
            except:
                date_prefix = datetime.now().strftime("%Y-%m-%d")

            safe_subject = re.sub(r'[^\w\s-]', '', subject).strip().replace(" ", "_")[:50]
            filename = f"{date_prefix}_{safe_subject}.md"
            filepath = output_dir / filename

            # Construct Markdown with Strict Frontmatter (Task 2: recipient injected)
            md_content = f"""---
privacy: strict
type: personal
source: email
date: {date_str}
sender: {sender}
recipient: {email_addr}
subject: {subject}
status: {notion_status}
---

# {subject}

{body}
"""

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

            print(f"💾 Saved to Staging: {filename}")

            # Notify Notion via local webhook receiver (Task 4: schema matches handle_email + send_to_notion)
            notion_metadata = {
                "type": "email",
                "subject": subject,
                "from": sender,
                "recipient": email_addr,
                "received_at": date_str,
                "body": body,
                "local_file": filename,
                "status": notion_status
            }
            send_to_notion(notion_metadata)
            print(f"🔔 Triage notification sent ({'Read (auto-routed)' if is_auto_read else 'New'})")

            # Mark as processed
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
        time.sleep(5)  # Stagger login requests
    
    if gmail_accounts:
        print(f"\n📧 Polling {len(gmail_accounts)} Gmail account(s)...")
        for account in gmail_accounts:
            results = poll_account(account, state, lookback_minutes, start_date, end_date)
            all_results.extend(results)
            time.sleep(5)  # Stagger login requests
    
    return all_results


def main():
    """Main daemon loop"""
    parser = argparse.ArgumentParser(description="Email Ingestion Daemon - Dual Protocol")
    parser.add_argument("--once", action="store_true", help="Run single poll then exit")
    parser.add_argument("--lookback", type=int, default=5, help="Look back minutes for unread emails")
    parser.add_argument("--start-date", type=str, help="Batch start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="Batch end date (YYYY-MM-DD)")
    args = parser.parse_args()

    # Load accounts
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

    # Initialize state
    state = EmailState(STATE_FILE)
    print(f"Loaded {len(state.processed_ids)} processed email IDs from state")

    # Main loop
    iteration = 0
    while True:
        iteration += 1
        print(f"\n--- Poll iteration {iteration} at {datetime.now().isoformat()} ---")

        # Poll all accounts
        all_results = poll_all_accounts(
            state, 
            lookback_minutes=args.lookback,
            start_date=args.start_date,
            end_date=args.end_date
        )
        
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
