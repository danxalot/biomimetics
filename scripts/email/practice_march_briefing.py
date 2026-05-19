#!/usr/bin/env python3
"""
Practice March Briefing Script (Comprehensive & Robust)
1. Pulls ALL March 2026 emails.
2. Pushes ALL processed (pass) emails to Notion.
3. Saves first 60 review/junk emails to staging.
4. Generates LLM briefings in batches of 60.
"""

import os
import sys
import json
import ssl
import imaplib
import email
import time
import re
from datetime import datetime, timezone
from pathlib import Path
from email_utils import (
    apply_filtering_rules, get_master_key, fetch_secret, 
    decode_header_value, extract_email_body, send_to_notion,
    process_and_save_email
)
from daily_failed_email_brief import generate_brief

# Configuration
START_DATE = "01-Mar-2026"
END_DATE = "31-Mar-2026"
STAGING_DIR = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "staging"

# Multi-Account Configuration
ACCOUNTS = [
    {"email": "dan.exall@pm.me", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "dan@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "arca@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "info@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "claws@arca-vsa.tech", "type": "proton", "secret": "proton-bridge-password"},
    {"email": "dan.exall@gmail.com", "type": "gmail", "secret": "gmail-app-password"},
]

def connect_imap(acc):
    master_key = get_master_key()
    password = fetch_secret(acc["secret"], master_key)
    if not password:
        print(f"❌ Could not fetch password for {acc['email']}")
        return None

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
        return mail
    except Exception as e:
        print(f"❌ Connection error for {acc['email']}: {e}")
        return None

def get_date(e_date_str):
    try:
        dt = email.utils.parsedate_to_datetime(e_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except:
        return datetime.min.replace(tzinfo=timezone.utc)

def run_practice():
    print("🚀 Starting Practice March Briefing (Comprehensive)...")
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    
    all_junk_emails = []
    
    for acc in ACCOUNTS:
        print(f"\n📧 Processing {acc['email']}...")
        mail = connect_imap(acc)
        if not mail: continue
        
        try:
            mail.select("INBOX")
            # Correctly handle IMAP date format (DD-Mon-YYYY)
            search_query = f'(SINCE "{START_DATE}" BEFORE "01-Apr-2026")'
            status, messages = mail.search(None, search_query)
            
            if status != "OK":
                print(f"  ❌ Search failed for {acc['email']}")
                continue
            
            email_ids = messages[0].split()
            print(f"  📬 Found {len(email_ids)} emails.")
            
            for e_id in email_ids:
                e_id_str = e_id.decode()
                # Step 1: Fetch HEADERS first for triage
                status, header_data = mail.fetch(e_id, "(RFC822.HEADER)")
                if status != "OK": continue
                
                header_msg = email.message_from_bytes(header_data[0][1])
                subject = decode_header_value(header_msg.get("Subject"))
                sender = decode_header_value(header_msg.get("From"))
                date_str = header_msg.get("Date")
                list_unsubscribe = header_msg.get("List-Unsubscribe")
                
                # Triage
                action, reason = apply_filtering_rules(subject, sender, list_unsubscribe, "")
                
                # Step 2: Fetch full content
                status, body_data = mail.fetch(e_id, "(RFC822)")
                if status != "OK": continue
                raw_email = body_data[0][1]

                if action == "pass":
                    print(f"  🟢 [PASS] {subject[:50]}...")
                    # Use centralized processing and saving
                    notion_metadata, filepath = process_and_save_email(
                        raw_email, 
                        e_id_str, 
                        STAGING_DIR, 
                        acc['email'], 
                        "New"
                    )
                    send_to_notion(notion_metadata)
                
                elif action in ["reject", "review"]:
                    print(f"  🔴 [{action.upper()}] {reason}: {subject[:50]}...")
                    
                    # For junk/review, we still want to parse it for the snippet
                    # but only save to staging if it's in the first 60 for the first briefing batch
                    msg = email.message_from_bytes(raw_email)
                    body = extract_email_body(msg)
                    
                    filename = None
                    if len(all_junk_emails) < 60:
                        notion_metadata, filepath = process_and_save_email(
                            raw_email, 
                            e_id_str, 
                            STAGING_DIR, 
                            acc['email'], 
                            "Junk"
                        )
                        filename = filepath.name

                    all_junk_emails.append({
                        "subject": subject,
                        "sender": sender,
                        "date": date_str,
                        "snippet": body[:1000].replace("\n", " ").strip(),
                        "reason": reason,
                        "account": acc["email"],
                        "local_file": filename
                    })
            
            mail.close()
            mail.logout()
        except Exception as e:
            print(f"  ❌ Error processing {acc['email']}: {e}")

    print(f"\n📊 Total Junk/Review Emails: {len(all_junk_emails)}")
    
    # Sort by date
    all_junk_emails.sort(key=lambda e: get_date(e["date"]))

    # Process in batches of 60 for the briefing
    for i in range(0, len(all_junk_emails), 60):
        batch = all_junk_emails[i:i+60]
        print(f"\n📝 Generating briefing for batch {i//60 + 1} ({len(batch)} emails)...")
        generate_brief(batch_emails=batch)
        print("  ✅ Briefing generated.")

if __name__ == "__main__":
    run_practice()
