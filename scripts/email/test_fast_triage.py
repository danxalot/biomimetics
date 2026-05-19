#!/usr/bin/env python3
"""
High-Speed Email Triage Test (Fixed)
Evaluates rule-based filtering effectiveness for dan.exall@pm.me (March 2026).
Bypasses LLM and Notion for maximum throughput and transparency.
Consolidated logic from scripts/email/email-ingestion-daemon.py.
"""

import os
import sys
import json
import ssl
import imaplib
import email
import re
import urllib.request
from pathlib import Path
from email.header import decode_header
from typing import List, Tuple, Dict, Optional
from bs4 import BeautifulSoup

# --- Configuration ---
CREDENTIALS_FILE = "/Users/danexall/biomimetics/secrets/credentials_api_key"
CRED_SERVER_URL = "http://localhost:8089/secrets"
TARGET_EMAIL = "dan.exall@pm.me"
PROTON_HOST = "127.0.0.1"
PROTON_PORT = 1143

# --- Legacy Filter & Triage Logic (From Daemon) ---
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
            try:
                return set(json.load(f))
            except:
                return set()
    return set()

def get_master_key():
    if not os.path.exists(CREDENTIALS_FILE): return None
    with open(CREDENTIALS_FILE, "r") as f: return f.read().strip()

def fetch_secret(secret_name, master_key):
    req = urllib.request.Request(f"{CRED_SERVER_URL}/{secret_name}")
    req.add_header("X-API-Key", master_key)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("value")
    except Exception as e: 
        print(f"Fetch error: {e}")
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

def extract_email_body(msg) -> str:
    """Extract and sanitize email body (from daemon)"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            elif content_type == "text/html" and not body and "attachment" not in content_disposition:
                # Use HTML if plain text isn't available
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    soup = BeautifulSoup(html, "html.parser")
                    for tag in soup.find_all(["style", "script"]):
                        tag.decompose()
                    body = soup.get_text(separator="\n", strip=True)
    else:
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

def run_fast_test():
    master_key = get_master_key()
    if not master_key:
        print("❌ Master key missing.")
        return

    password = fetch_secret("proton-bridge-password", master_key)
    if not password:
        print("❌ Could not fetch password.")
        return

    whitelist = load_whitelist()

    print("=" * 80)
    print(f"🚀 ENHANCED FAST TRIAGE TEST: {TARGET_EMAIL} (March 2026)")
    print("=" * 80)

    try:
        mail = imaplib.IMAP4(PROTON_HOST, PROTON_PORT)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        mail.starttls(ssl_context=ctx)
        mail.login(TARGET_EMAIL, password)
        mail.select("INBOX")

        # Search for March 2026
        status, messages = mail.search(None, '(SINCE "01-Mar-2026" BEFORE "01-Apr-2026")')
        if status != "OK":
            print("❌ Search failed.")
            return

        email_ids = messages[0].split()
        print(f"📬 Found {len(email_ids)} emails in March 2026.")
        print("-" * 80)

        results = {
            "Institutional": 0,
            "Whitelisted": 0,
            "Legacy Filter": 0,
            "Newsletter (Skip)": 0,
            "Hard Refuse (Skip)": 0,
            "Failed Triage (Skip)": 0
        }

        for e_id in reversed(email_ids):
            # Fetch HEADERS first for fast filtering
            status, msg_data = mail.fetch(e_id, "(RFC822.HEADER)")
            if status != "OK": continue
            
            msg = email.message_from_bytes(msg_data[0][1])
            subject = decode_header_value(msg.get("Subject"))
            sender = decode_header_value(msg.get("From"))
            list_unsubscribe = str(msg.get("List-Unsubscribe", ""))
            
            pass_reason = None
            
            # 0. Hard Refusal
            if any(phrase.lower() in subject.lower() for phrase in HARD_REFUSE_PHRASES):
                print(f"  🛑 [HARD REFUSE] {subject[:60]}")
                results["Hard Refuse (Skip)"] += 1
                continue

            # 1. Institutional Check
            sender_domain = sender.split("@")[-1].strip(">").lower()
            if any(dom in sender_domain for dom in INSTITUTIONAL_DOMAINS) or \
               any(kw.lower() in sender.lower() for kw in INSTITUTIONAL_KEYWORDS):
                pass_reason = "Institutional"
            
            # 2. Whitelist Check
            if not pass_reason:
                sender_addr_matches = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', sender)
                if sender_addr_matches and sender_addr_matches[0].lower() in whitelist:
                    pass_reason = "Whitelisted"
            
            # 3. Newsletter Check (REJECT)
            if not pass_reason and list_unsubscribe:
                print(f"  🔴 [NEWSLETTER] {subject[:60]}")
                results["Newsletter (Skip)"] += 1
                continue
            
            # 4. Legacy Keyword Filter
            if not pass_reason:
                if PATTERN.search(f"{subject} {sender}"):
                    pass_reason = "Legacy Filter"
            
            if pass_reason:
                # If matched, fetch full body for the snippet
                status, full_data = mail.fetch(e_id, "(BODY.PEEK[])")
                full_msg = email.message_from_bytes(full_data[0][1])
                body = extract_email_body(full_msg)
                snippet = " ".join(body.split()[:15]) + "..."
                
                print(f"✅ [KEEP - {pass_reason}] {subject[:60]}")
                print(f"   FROM: {sender[:60]}")
                print(f"   SNIP: {snippet}")
                print("-" * 40)
                results[pass_reason] += 1
            else:
                results["Failed Triage (Skip)"] += 1

        mail.close()
        mail.logout()

        print("\n" + "=" * 80)
        print("📊 TRIAGE SUMMARY")
        print("-" * 80)
        total_kept = results["Institutional"] + results["Whitelisted"] + results["Legacy Filter"]
        total_skipped = results["Newsletter (Skip)"] + results["Hard Refuse (Skip)"] + results["Failed Triage (Skip)"]
        
        for key, val in results.items():
            print(f"{key:25}: {val}")
        
        print("-" * 80)
        print(f"TOTAL KEPT   : {total_kept}")
        print(f"TOTAL SKIPPED: {total_skipped}")
        print("=" * 80)

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_fast_test()
