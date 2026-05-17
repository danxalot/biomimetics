#!/usr/bin/env python3
"""
BiOS Email Triage Engine (v2.1.0)
================================
Advanced Hybrid Triage - Rule-Based + LLM Filtering + Search & Ingest

INSTRUCTIONS FOR FUTURE REFERENCE:
1. Search: Use --since, --before, or --days to define the search window.
2. Filters: Use --subject to search for specific keywords across accounts.
3. Ingestion: Use the --push flag to fetch full email bodies and save them to 
   ~/biomimetics/docs/personal/emails/staging/ for Notion processing.
4. Security: All passwords are fetched from http://localhost:8089. Ensure the 
   Credentials Server is running before execution.

Usage:
    python3 email_triage_engine.py [OPTIONS]

Options:
    --since DATE      Search emails since date (format: DD-Mon-YYYY, e.g. 01-Jan-2026)
    --before DATE     Search emails before date (format: DD-Mon-YYYY)
    --days N          Quick filter for emails from the last N days
    --subject TEXT    Search for specific keywords in the email subject
    --batch N         Override default batch size (default: 10 emails per account)
    --push            FETCH full body and save matching emails to staging/

Examples:
    # Scan last 7 days and push matches to staging
    python3 email_triage_engine.py --days 7 --push

    # Target specific legacy period with subject filter
    python3 email_triage_engine.py --since 01-Dec-2025 --before 31-Jan-2026 --subject "Citizens Advice" --push
"""

import imaplib
import email
from email.header import decode_header
import re
import json
import urllib.request
import urllib.error
import ssl
import os
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# --- CONFIGURATION ---
CREDENTIALS_FILE = "/Users/danexall/biomimetics/secrets/credentials_api_key"
CRED_SERVER_URL = "http://localhost:8089/secrets"
STAGING_DIR = Path("/Users/danexall/biomimetics/docs/personal/emails/staging")
TEST_BATCH_SIZE = 10  # Per account

# The strict deterministic net
KEEP_KEYWORDS = [
    "invoice", "receipt", "you sent", "payment", "octopus", "vultr", "azure",
    "ticket", "order", "document", "citizens advice", "cab", "debt",
    "arrears", "collection", "bailiff", "stepchange", "credit", "complaint",
    "appeal", "ombudsman", "watchdog", "legal", "solicitor", "police",
    "council", "security alert", "breach", "pwned", "unauthorized", "login",
]

INSTITUTIONAL_DOMAINS = ["nhs.net", "nhs.uk", "gov.uk", "police.uk", "lgo.org.uk"]
INSTITUTIONAL_KEYWORDS = ["citizens advice", "solicitor", "lawyer", "legal", "constabulary", "police"]

PATTERN = re.compile(
    r"\b(?:" + "|".join(map(re.escape, KEEP_KEYWORDS)) + r")\b", re.IGNORECASE
)

ACCOUNTS = [
    {"email": "dan.exall@pm.me", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "dan@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "arca@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "info@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "claws@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "dan.exall@gmail.com", "type": "gmail", "secret": "gmail-app-password"},
]

# --- HELPER FUNCTIONS ---
def get_master_key():
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    with open(CREDENTIALS_FILE, "r") as f:
        return f.read().strip()

def fetch_secret(secret_name, master_key):
    req = urllib.request.Request(f"{CRED_SERVER_URL}/{secret_name}")
    req.add_header("X-API-Key", master_key)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("value")
    except Exception:
        return None

def decode_header_value(header_value):
    if not header_value: return ""
    decoded_parts = decode_header(header_value)
    result = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8", errors="ignore")
        else:
            result += str(part)
    return result

def is_institutional(sender, subject):
    s_lower, sub_lower = sender.lower(), subject.lower()
    if any(dom in s_lower for dom in INSTITUTIONAL_DOMAINS): return True
    if any(kw in s_lower or kw in sub_lower for kw in INSTITUTIONAL_KEYWORDS): return True
    return False

def fetch_full_body(mail, e_id):
    status, msg_data = mail.fetch(e_id, "(RFC822)")
    if status != "OK": return ""
    msg = email.message_from_bytes(msg_data[0][1])
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors='ignore')
                break
    else:
        body = msg.get_payload(decode=True).decode(errors='ignore')
    return body

def save_to_staging(sender, subject, date_raw, body):
    clean_subject = re.sub(r'[^\w\s-]', '', subject).strip()
    clean_subject = re.sub(r'[-\s]+', '_', clean_subject)
    
    try:
        date_match = re.search(r'(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4})', date_raw)
        if date_match:
            d, m, y = date_match.groups()
            date_str = f"{y}-{datetime.strptime(m, '%b').month:02d}-{int(d):02d}"
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
    except:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    filename = f"{date_str}_{clean_subject[:50]}.md"
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    
    content = f"---\nfrom: {sender}\nsubject: {subject}\ndate: {date_raw}\n---\n\n{body}\n"
    (STAGING_DIR / filename).write_text(content)
    return filename

def run_triage():
    parser = argparse.ArgumentParser(description="BiOS Email Triage Engine")
    parser.add_argument("--since", help="Search emails since date (e.g. 01-Jan-2024)")
    parser.add_argument("--before", help="Search emails before date (e.g. 31-Dec-2024)")
    parser.add_argument("--subject", help="Search for specific text in subject")
    parser.add_argument("--days", type=int, help="Search emails from last N days")
    parser.add_argument("--batch", type=int, default=TEST_BATCH_SIZE)
    parser.add_argument("--push", action="store_true", help="Push results to staging/")
    args = parser.parse_args()

    master_key = get_master_key()
    if not master_key:
        print("❌ Master key missing.")
        return

    search_criteria = []
    if args.since: search_criteria.append(f'(SINCE "{args.since}")')
    elif args.days:
        since_date = (datetime.now() - timedelta(days=args.days)).strftime("%d-%b-%Y")
        search_criteria.append(f'(SINCE "{since_date}")')
    if args.before: search_criteria.append(f'(BEFORE "{args.before}")')
    if args.subject: search_criteria.append(f'(SUBJECT "{args.subject}")')
    query = " ".join(search_criteria) if search_criteria else "ALL"

    print("=" * 70)
    print(f"📧 BiOS Email Triage Engine v2.1.0 | Query: {query}")
    print("=" * 70)

    secrets_cache = {}
    for acc in ACCOUNTS:
        print(f"\n▶ Scanning: {acc['email']}")
        if acc["secret"] not in secrets_cache:
            pw = fetch_secret(acc["secret"], master_key)
            if not pw: continue
            secrets_cache[acc["secret"]] = pw

        password, mail = secrets_cache[acc["secret"]], None
        try:
            if acc["type"] == "proton":
                mail = imaplib.IMAP4("127.0.0.1", 1143)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                mail.starttls(ssl_context=ctx)
            else:
                mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)

            mail.login(acc["email"], password)
            mail.select("INBOX")
            status, messages = mail.search(None, query)
            if status != "OK": continue

            email_ids = messages[0].split()
            latest_ids = email_ids[-args.batch:]
            for e_id in reversed(latest_ids):
                status, msg_data = mail.fetch(e_id, "(RFC822.HEADER)")
                if status != "OK": continue
                msg = email.message_from_bytes(msg_data[0][1])
                subject, sender = decode_header_value(msg.get("Subject")), decode_header_value(msg.get("From"))
                date_raw = msg.get("Date", "")

                if is_institutional(sender, subject) or PATTERN.search(f"{subject} {sender}"):
                    print(f"  ✅ [KEEP] - {subject[:60]}")
                    if args.push:
                        body = fetch_full_body(mail, e_id)
                        fname = save_to_staging(sender, subject, date_raw, body)
                        print(f"     └─ Saved to staging: {fname}")
                else:
                    print(f"  🚫 [SKIP] - {subject[:60]}")

        except Exception as e: print(f"  ❌ Error: {e}")
        finally:
            if mail:
                try: mail.close(); mail.logout()
                except: pass

    print("\n" + "=" * 70 + "\n✅ Triage complete\n" + "=" * 70)

if __name__ == "__main__":
    run_triage()
