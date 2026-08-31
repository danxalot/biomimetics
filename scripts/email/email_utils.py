#!/usr/bin/env python3
"""
Email utility functions for searching, fetching, and saving emails.
"""

import os
import json
import ssl
import imaplib
import email
import re
import urllib.request
import httpx
from pathlib import Path
from email.header import decode_header
from datetime import datetime, timedelta

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# --- Configuration ---
CREDENTIALS_FILE = "/Users/danexall/biomimetics/secrets/credentials_api_key"
CRED_SERVER_URL = "http://localhost:8089/secrets"
PROTON_HOST = "127.0.0.1"
PROTON_PORT = 1143
FILTER_RULES_FILE = Path("/Users/danexall/biomimetics/config/email_filtering_rules.json")
WHITELIST_FILE = Path("/Users/danexall/biomimetics/config/email_whitelist.json")
WEBHOOK_RECEIVER_URL = "http://localhost:8090/email"

def get_master_key():
    if not os.path.exists(CREDENTIALS_FILE): return None
    with open(CREDENTIALS_FILE, "r") as f: return f.read().strip()

def fetch_secret(secret_name, master_key):
    req = urllib.request.Request(f"{CRED_SERVER_URL}/{secret_name}")
    req.add_header("X-API-Key", master_key)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
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

def save_email_to_markdown(subject, sender, recipient, date_str, body, output_dir, status="New"):
    """Saves email content to a localized Markdown file with frontmatter."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize filename: YYYY-MM-DD_Sanitized_Subject.md
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        date_prefix = dt.strftime("%Y-%m-%d")
    except:
        date_prefix = datetime.now().strftime("%Y-%m-%d")

    safe_subject = re.sub(r'[^\w\s-]', '', subject).strip().replace(" ", "_")[:50]
    filename = f"{date_prefix}_{safe_subject}.md"
    filepath = output_dir / filename

    md_content = f"""---
privacy: strict
type: personal
source: email
date: {date_str}
sender: {sender}
recipient: {recipient}
subject: {subject}
status: {status}
---

# {subject}

{body}
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    return filename, filepath


def process_and_save_email(raw_content, e_id, output_dir, recipient, status="New"):
    """
    Full pipeline for processing a raw email:
    1. Parse headers
    2. Extract and cleanse body (BeautifulSoup)
    3. Save raw .eml
    4. Save cleansed .md
    5. Return data for Notion
    """
    msg = email.message_from_bytes(raw_content)
    subject = decode_header_value(msg.get("Subject"))
    sender = decode_header_value(msg.get("From"))
    date_str = msg.get("Date")
    
    body = extract_email_body(msg)
    
    # Save raw
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"email_{e_id}.eml"
    with open(raw_path, "wb") as f:
        f.write(raw_content)
    
    # Save markdown
    filename, filepath = save_email_to_markdown(subject, sender, recipient, date_str, body, output_dir, status)
    
    notion_metadata = {
        "type": "email",
        "subject": subject,
        "from": sender,
        "recipient": recipient,
        "received_at": date_str,
        "body": body,
        "local_file": filename,
        "status": status
    }
    
    return notion_metadata, filepath


def save_email(raw_content, e_id, output_dir):
    """Legacy wrapper for save_email, now uses the standard pipeline."""
    # Note: recipient is unknown here, defaulting to 'unknown'
    metadata, filepath = process_and_save_email(raw_content, e_id, output_dir, "unknown")
    return [output_dir / f"email_{e_id}.eml", filepath]

def search_emails(email_address, folder, from_date=None, to_date=None, subject=None, sender=None, content=None, output_dir=None):
    master_key = get_master_key()
    if not master_key:
        print("❌ Master key missing.")
        return

    password = fetch_secret("proton-bridge-password", master_key)
    if not password:
        print("❌ Could not fetch password.")
        return

    print(f"🔍 Searching in {email_address}/{folder}...")

    try:
        mail = imaplib.IMAP4(PROTON_HOST, PROTON_PORT)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        mail.starttls(ssl_context=ctx)
        mail.login(email_address, password)
        mail.select(folder)

        search_criteria = []
        if from_date:
            search_criteria.append(f'(SINCE "{from_date.strftime("%d-%b-%Y")}")')
        if to_date:
            search_criteria.append(f'(BEFORE "{to_date.strftime("%d-%b-%Y")}")')
        if subject:
            safe_subject = subject.replace('"', '\\"')
            search_criteria.append(f'(SUBJECT "{safe_subject}")')
        if sender:
            search_criteria.append(f'(FROM "{sender}")')
        if content:
             search_criteria.append(f'(BODY "{content}")')

        search_query = " ".join(search_criteria)
        print(f"Executing search: {search_query}")

        status, messages = mail.search(None, search_query)
        
        if status != "OK":
            print(f"❌ Search failed for query: '{search_query}'. Server response: {messages}")
            return

        email_ids = messages[0].split()
        if not email_ids:
            print(f"⚠️  No matching emails found for query: '{search_query}'")
            return

        print(f"✅ Found {len(email_ids)} matching email(s).")

        email_data = []
        if output_dir:
            for e_id in email_ids:
                print(f"📥 Fetching email ID: {e_id.decode()}")
                status, msg_data = mail.fetch(e_id, "(RFC822)")
                if status != "OK":
                    print(f"❌ Failed to fetch email {e_id.decode()}")
                    continue
                
                raw_email = msg_data[0][1]
                email_data.append(raw_email)
                saved_paths = save_email(raw_email, e_id.decode(), output_dir)
                print(f"💾 Saved to:")
                for path in saved_paths:
                    print(f"   - {path}")
        
            if not BS4_AVAILABLE:
                print("\n⚠️  Warning: `beautifulsoup4` is not installed. HTML emails were saved as raw files.")
                print("   To get formatted HTML output, please run: pip install beautifulsoup4")

        mail.close()
        mail.logout()
        return email_data


    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def load_filtering_rules():
    """Loads email filtering rules from the JSON config file."""
    if not os.path.exists(FILTER_RULES_FILE):
        return []
    with open(FILTER_RULES_FILE, "r") as f:
        return json.load(f)

def load_whitelist() -> set:
    if WHITELIST_FILE.exists():
        with open(WHITELIST_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_whitelist(whitelist: set):
    with open(WHITELIST_FILE, "w") as f:
        json.dump(list(whitelist), f)

def update_sent_whitelist(mail_client, account_email, state):
    """Scan Sent folder and add recipients to whitelist"""
    try:
        sent_folder = None
        status, folder_list = mail_client.list()
        if status == 'OK':
            for line in folder_list:
                line_str = line.decode('utf-8')
                if '\\\\sent' in line_str.lower():
                    match = re.search(r'\(.*\) "/" "(.*)"', line_str)
                    if not match:
                        match = re.search(r'\(.*\) "." "(.*)"', line_str)
                    if match:
                        sent_folder = f'"{match.group(1)}"'
                        break
        
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

        status, data = mail_client.select(sent_folder, readonly=True)
        if status != 'OK':
            print(f"  ⚠️  Failed to select {sent_folder}: {data}")
            return

        last_check = state.get(f"last_sent_check_{account_email}")
        since_date = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
        if last_check:
            since_date = datetime.strptime(last_check, "%Y-%m-%d").strftime("%d-%b-%Y")
        
        status, messages = mail_client.search(None, f'(SINCE {since_date})')
        if status != "OK": return
        
        whitelist = load_whitelist()
        new_entries = 0
        
        for e_id in messages[0].split():
            status, msg_data = mail_client.fetch(e_id, "(RFC822.HEADER)")
            if status != "OK": continue
            msg = email.message_from_bytes(msg_data[0][1])
            to_addr = msg.get("To", "")
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
                    if BS4_AVAILABLE:
                        # Ensure we clean the HTML thoroughly
                        soup = BeautifulSoup(raw_html, "html.parser")
                        # Remove styling and script elements
                        for element in soup(["script", "style", "head", "title", "meta", "[document]"]):
                            element.decompose()
                        # Get text with clean spacing
                        text = soup.get_text(separator=" ", strip=True)
                        # Remove redundant whitespace
                        html_body = " ".join(text.split())
                    else:
                        html_body = raw_html
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
            if content_type == "text/html" and BS4_AVAILABLE:
                soup = BeautifulSoup(raw, "html.parser")
                for tag in soup.find_all(["style", "script"]):
                    tag.decompose()
                body = soup.get_text(separator="\n", strip=True)
            else:
                body = raw
        except Exception:
            body = str(msg.get_payload())

    return body.strip()


def markdown_to_notion_children(body: str, limit: int = 80) -> list:
    """Turn briefing markdown into Notion page body blocks (page create children)."""
    children = []
    if not body:
        return children
    for raw_line in body.splitlines():
        text = raw_line.strip()
        if not text:
            continue
        content = text[:2000]
        if text.startswith("## "):
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": content[3:]}}]},
            })
        elif text.startswith("# "):
            children.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": content[2:]}}]},
            })
        elif text.startswith("- "):
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": content[2:]}}]},
            })
        else:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]},
            })
        if len(children) >= limit:
            break
    return children


def send_to_notion(payload: dict) -> dict:
    """Send tracking entry to Notion database directly."""
    try:
        notion_api_key = os.environ.get("NOTION_API_KEY")
        # Default to BiOS Authorisation DB ID
        notion_db_id = os.environ.get("NOTION_EMAIL_DB_ID", "3284d2d9fc7c81bd9a91e865511e642f")
        
        # JIT Secret Fetching if not in environment
        if not notion_api_key:
            master_key = get_master_key()
            if master_key:
                notion_api_key = fetch_secret("notion-api-key", master_key)
        
        if not notion_api_key:
            return {"error": "NOTION_API_KEY not set and could not be fetched"}
        
        body_text = payload.get("body", json.dumps(payload, indent=2))
        notion_data = {
            "parent": {"database_id": notion_db_id},
            "properties": {
                "Name": {"title": [{"text": {"content": f"[{payload.get('type', 'email').upper()}] {payload.get('subject', 'No Subject')}"}}]},
                "Source": {"select": {"name": payload.get("type", "Email").capitalize()}},
                "Status": {"select": {"name": payload.get("status", "Triage")}},
                "Local File": {"rich_text": [{"text": {"content": payload.get("local_file", "")}}]},
                "Payload": {"rich_text": [{"text": {"content": body_text[:2000]}}]}
            }
        }
        children = markdown_to_notion_children(body_text)
        if children:
            notion_data["children"] = children

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {notion_api_key}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28"
                },
                json=notion_data
            )
            if resp.status_code != 200:
                print(f"  ❌ Notion API Error: {resp.status_code} {resp.text}")
                return {"error": resp.text}
            return resp.json()

    except Exception as e:
        print(f"  ❌ Direct Notion push failed: {e}")
        return {"error": str(e)}


def apply_filtering_rules(subject, sender, list_unsubscribe, body):
    """
    Applies filtering rules from the config file to an email.
    Returns a tuple of (action, reason).
    """
    rules = load_filtering_rules()
    whitelist = load_whitelist()
    sender_addr_list = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', sender)
    sender_addr = sender_addr_list[0].lower() if sender_addr_list else ""
    sender_domain = sender_addr.split('@')[-1] if sender_addr else ""

    # Triage hierarchy is implemented by the order of checks here
    for rule in rules:
        action = rule.get("action")
        reason = rule.get("reason", action)
        
        # Hard Refuse
        if action == "hard_refuse":
            if "subject_contains" in rule and rule["subject_contains"].lower() in subject.lower():
                return "hard_refuse", reason

        # Institutional Pass
        if action == "pass" and reason == "Institutional":
            if "sender_domain_in" in rule and sender_domain in rule["sender_domain_in"]:
                return "pass", reason
            if "sender_keyword_in" in rule and any(kw.lower() in sender.lower() for kw in rule["sender_keyword_in"]):
                 return "pass", reason

        # Review Flags (Higher priority than normal reject/pass)
        if action == "review":
            if "sender_domain_in" in rule and sender_domain in rule["sender_domain_in"]:
                return "review", reason
            if "subject_contains" in rule and rule["subject_contains"].lower() in subject.lower():
                return "review", reason
            if "sender_keyword_in" in rule and any(kw.lower() in sender.lower() for kw in rule["sender_keyword_in"]):
                return "review", reason

    # Whitelist Pass (checked after institutional and review)
    if sender_addr in whitelist:
        return "pass", "Whitelisted"

    for rule in rules:
        action = rule.get("action")
        reason = rule.get("reason", action)

        # Newsletter Reject
        if action == "reject" and rule.get("has_list_unsubscribe"):
            if list_unsubscribe:
                return "reject", reason
        
        # Legacy Keyword Pass
        if action == "pass" and reason == "Legacy Filter":
             if "subject_or_sender_matches_regex" in rule:
                 pattern = re.compile(rule["subject_or_sender_matches_regex"], re.IGNORECASE)
                 if pattern.search(f"{subject} {sender}"):
                     return "pass", reason

    return "reject", "Triage Failure"
