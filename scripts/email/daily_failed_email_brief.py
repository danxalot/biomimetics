#!/usr/bin/env python3
"""
Daily Failed Email & Life Brief (LLM Augmented)
Summarizes:
1. Truly Free Audio Offers (LLM extracted)
2. Response-Worthy Emails from Failed Triage (LLM extracted)
3. Important Life Updates (billing, recycling, security)
4. Failed Email Imports (General list)
"""

import os
import json
import httpx
import re
import openai
from datetime import datetime, date
from pathlib import Path
import email.utils

# Configuration
JUNK_CACHE_FILE = Path.home() / ".arca" / "junk_cache.json"
CONFIG_FILE = Path.home() / "biomimetics" / "config" / "omni_sync_config.json"
BRIEFINGS_DIR = Path("/Users/danexall/Google Drive/My Drive/Obsidian-life/Personal/Emails/Vault")
STAGING_DIR = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "staging"
WEBHOOK_URL = "http://localhost:8000/email"

# LLM Configuration
LOCAL_LLM_BASE_URL = "http://localhost:11435/v1"
LOCAL_LLM_MODEL = "gemini-1.5-flash-8b-001" # Representing gemini-3.1-flash-lite-preview

# Keywords for "Important" life updates
IMPORTANT_KEYWORDS = [
    "billing", "payment", "declined", "missed", "defaulted", "invoice", "receipt",
    "recycling", "waste", "collection", "security", "alert", "login", "verify",
    "important", "urgent", "action required", "document attached", "delivered"
]

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def get_primary_email(config):
    identity = config.get("IDENTITY", {})
    return identity.get("PRIMARY_EMAIL", "claws@arca-vsa.tech")

def parse_email_date(date_str):
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.date()
    except Exception:
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.date()
        except Exception:
            return None

def get_staged_updates(today):
    updates = []
    if not STAGING_DIR.exists():
        return updates
        
    date_str = today.isoformat()
    for file in STAGING_DIR.glob(f"{date_str}_*.md"):
        subject = file.name.replace(f"{date_str}_", "").replace(".md", "").replace("_", " ")
        
        # Determine importance
        is_important = any(kw in subject.lower() for kw in IMPORTANT_KEYWORDS)
        
        updates.append({
            "subject": subject,
            "file": file.name,
            "is_important": is_important
        })
    return updates

def process_with_llm(emails):
    """
    Process a batch of emails using LLM to find free audio and response-worthy items.
    """
    if not emails:
        return {"free_audio": [], "needs_response": []}

    client = openai.OpenAI(base_url=LOCAL_LLM_BASE_URL, api_key="not-needed")
    
    email_list_text = ""
    for idx, e in enumerate(emails):
        email_list_text += f"ID: {idx}\nSubject: {e.get('subject')}\nSender: {e.get('sender')}\nTriage Reason: {e.get('reason', 'N/A')}\nSnippet: {e.get('snippet', '')[:300]}\n---\n"

    prompt = f"""You are an expert personal assistant for Daniel Exall. 
I am providing a list of emails that were caught in a 'junk' filter or flagged for review. 
Your task is to identify two specific types of content from this list:

1. 'FREE_AUDIO': Identify any "truly free" audio software, plugins, libraries, or downloads. 
   - EXCLUDE "special offers", "discounts", "introductory pricing", or "free with purchase". 
   - INCLUDE only items that are completely free to keep.

2. 'NEEDS_RESPONSE': Identify any emails that appear to be genuine messages or alerts that require a direct response or action from Daniel. 
   Specifically: "Is there anything in here that dan needs to action that could impact his living situation?" 
   (e.g., utility bills, housing information, security alerts like GitGuardian, or legal notices).

List of Emails:
{email_list_text}

Return your findings in JSON format with two lists: 'free_audio' and 'needs_response'. 
Each list item should include the 'ID' and a brief 'reason' for your choice.
Example: {{"free_audio": [{{"id": 5, "reason": "Completely free VST synth plugin"}}], "needs_response": [{{"id": 12, "reason": "GitGuardian alert about exposed secret"}}]}}
"""

    try:
        response = client.chat.completions.create(
            model=LOCAL_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        
        # Map IDs back to original email objects
        final_result = {"free_audio": [], "needs_response": []}
        
        for item in result.get("free_audio", []):
            try:
                idx = int(item["id"])
                if 0 <= idx < len(emails):
                    email_item = emails[idx].copy()
                    email_item["llm_reason"] = item["reason"]
                    final_result["free_audio"].append(email_item)
            except: pass

        for item in result.get("needs_response", []):
            try:
                idx = int(item["id"])
                if 0 <= idx < len(emails):
                    email_item = emails[idx].copy()
                    email_item["llm_reason"] = item["reason"]
                    final_result["needs_response"].append(email_item)
            except: pass

        return final_result
    except Exception as e:
        print(f"❌ LLM Processing Error: {e}")
        return {"free_audio": [], "needs_response": []}

def generate_brief(target_date=None, batch_emails=None):
    """
    Generates a daily briefing. 
    Can be used for the current day or for a batch of historical emails (backfill mode).
    """
    config = load_config()
    primary_email = get_primary_email(config)
    
    if target_date is None:
        target_date = date.today()
    
    if batch_emails is None:
        # Standard daily mode: load from junk cache
        junk_data = []
        if JUNK_CACHE_FILE.exists():
            with open(JUNK_CACHE_FILE, "r") as f:
                try:
                    junk_data = json.load(f)
                except:
                    pass
        
        # Filter for today
        emails_to_process = [e for e in junk_data if parse_email_date(e.get("date", "")) == target_date]
    else:
        # Backfill/Practice mode
        emails_to_process = batch_emails

    # LLM Processing in batches of 15
    llm_free_audio = []
    llm_needs_response = []
    
    for i in range(0, len(emails_to_process), 15):
        batch = emails_to_process[i:i+15]
        print(f"🧠 Processing batch of {len(batch)} emails with LLM...")
        batch_result = process_with_llm(batch)
        llm_free_audio.extend(batch_result["free_audio"])
        llm_needs_response.extend(batch_result["needs_response"])

    # 2. Important Life Updates (from staging - only for current day mode)
    important_updates = []
    if batch_emails is None:
        staged_updates = get_staged_updates(target_date)
        important_updates = [u for u in staged_updates if u["is_important"]]

    if not llm_free_audio and not llm_needs_response and not important_updates and not emails_to_process:
        print(f"ℹ️ No significant updates found for {target_date}")
        return

    # Create briefing content
    subject = f"[Daily Briefing] Life & Email Summary - {target_date.isoformat()}"
    if batch_emails:
        # Determine range for historical batch
        dates = [parse_email_date(e.get("date", "")) for e in batch_emails if parse_email_date(e.get("date", ""))]
        if dates:
            subject = f"[Batch Briefing] Email Summary - {min(dates).isoformat()} to {max(dates).isoformat()}"

    content = f"# {subject}\n\n"
    content += f"**Date:** {datetime.now().isoformat()}\n\n"

    if llm_needs_response:
        content += "## 📩 Response Required (Failed Triage)\n"
        for entry in llm_needs_response:
            content += f"- **{entry.get('subject', 'No Subject')}**\n"
            content += f"  - Sender: {entry.get('sender', 'Unknown')}\n"
            content += f"  - Reason: {entry.get('llm_reason', 'N/A')}\n"
            content += f"  - Snippet: {entry.get('snippet', 'No snippet')[:150]}...\n\n"

    if llm_free_audio:
        content += "## 🎁 Truly FREE Audio Offers\n"
        for entry in llm_free_audio:
            content += f"- **{entry.get('subject', 'No Subject')}**\n"
            content += f"  - Sender: {entry.get('sender', 'Unknown')}\n"
            content += f"  - Reason: {entry.get('llm_reason', 'N/A')}\n"
            content += f"  - Snippet: {entry.get('snippet', 'No snippet')[:150]}...\n\n"
    
    if important_updates:
        content += "## ⚡ Important Life Updates\n"
        for u in important_updates:
            content += f"- **{u['subject']}** (Saved as: {u['file']})\n"
        content += "\n"

    if emails_to_process:
        content += f"## ⚠️ General Failed Triage Count: {len(emails_to_process)}\n\n"

    # Save to local file
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    safe_subject = re.sub(r'[^\w\s-]', '', subject).strip().replace(" ", "_")[:50]
    filename = f"{datetime.now().strftime('%H%M%S')}_{safe_subject}.md"
    filepath = BRIEFINGS_DIR / filename
    
    md_with_frontmatter = f"""---
privacy: strict
type: personal
source: email
date: {datetime.now().isoformat()}
sender: BiOS Daemon
recipient: {primary_email}
subject: {subject}
status: Read
---

{content}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md_with_frontmatter)
    
    print(f"💾 Saved summary to: {filepath}")

    # Send to Notion
    notion_metadata = {
        "type": "email",
        "subject": subject,
        "from": "BiOS Daemon",
        "recipient": primary_email,
        "received_at": datetime.now().isoformat(),
        "body": content,
        "local_file": filename,
        "status": "Read"
    }
    
    try:
        response = httpx.post(WEBHOOK_URL, json=notion_metadata, timeout=15.0)
        if response.status_code == 200:
            print("🔔 Briefing sent to Notion successfully.")
        else:
            print(f"⚠️ Failed to send to Notion: {response.status_code} {response.text}")
    except Exception as e:
        print(f"❌ Error sending to Notion: {e}")

if __name__ == "__main__":
    generate_brief()
