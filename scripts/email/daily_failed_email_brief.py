#!/usr/bin/env python3
"""
Daily Failed Email & Life Brief (LLM Augmented)
Summarizes:
1. Truly Free Audio Offers (LLM extracted)
2. Response-Worthy Emails from Failed Triage (LLM extracted)
3. Important Life Updates (billing, recycling, security)
4. Failed Email Imports (full inventory — never an empty count-only draft)
"""

import os
import sys
import json
import re
import ssl
import urllib.request
import argparse
from datetime import datetime, date
from pathlib import Path
import email.utils
from email.header import decode_header

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

# Configuration
JUNK_CACHE_FILE = Path.home() / ".arca" / "junk_cache.json"
CONFIG_FILE = Path.home() / "biomimetics" / "config" / "omni_sync_config.json"
BRIEFINGS_DIR = Path("/Users/danexall/Google Drive/My Drive/Obsidian-life/Personal/Emails/Vault")
STAGING_DIR = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "staging"

# High-volume email classification — 3.1 Flash Lite free quota.
from lib.gemini import MODEL_VOLUME as GEMINI_MODEL  # noqa: E402
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
LLM_BATCH_SIZE = 12
SNIPPET_CHARS = 280

IMPORTANT_KEYWORDS = [
    "billing", "payment", "declined", "missed", "defaulted", "invoice", "receipt",
    "recycling", "waste", "collection", "security", "alert", "login", "verify",
    "important", "urgent", "action required", "document attached", "delivered"
]

ACTION_KEYWORDS = [
    "billing", "payment failed", "payment declined", "invoice", "receipt",
    "action required", "security", "alert", "login", "verify", "password",
    "council", "ombudsman", "legal", "court", "evict", "arrears", "housing",
    "universal credit", "citizens advice", "urgent", "final notice",
    "collection", "recycling", "waste"
]

AUDIO_FREE_HINTS = [
    "free vst", "free plugin", "free sample", "free preset", "free kontakt",
    "free wav", "free library", "free instrument", "giveaway", "freeware"
]
AUDIO_PAID_HINTS = [
    "sale", "discount", "% off", "intro price", "with purchase", "free trial",
    "subscription", "starting at", "from $"
]


def _ssl_context():
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def get_primary_email(config):
    identity = config.get("IDENTITY", {})
    return identity.get("PRIMARY_EMAIL", "claws@arca-vsa.tech")


def decode_mime_text(value):
    if not value:
        return ""
    if not isinstance(value, str):
        value = str(value)
    try:
        parts = decode_header(value)
        out = ""
        for part, enc in parts:
            if isinstance(part, bytes):
                out += part.decode(enc or "utf-8", errors="replace")
            else:
                out += part
        return " ".join(out.split())
    except Exception:
        return " ".join(str(value).split())


def parse_email_date(date_str):
    """Return the local calendar date for an RFC2822 / ISO timestamp."""
    if not date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.date()
    except Exception:
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is not None:
                dt = dt.astimezone()
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
        is_important = any(kw in subject.lower() for kw in IMPORTANT_KEYWORDS)
        updates.append({
            "subject": subject,
            "file": file.name,
            "is_important": is_important
        })
    return updates


def get_email_body_from_staging(filename):
    """Retrieves and cleans the email body from a staged markdown file."""
    path = STAGING_DIR / filename
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else content.strip()
        return body[:SNIPPET_CHARS]
    except Exception as e:
        print(f"  ⚠️ Error reading staging file {filename}: {e}")
        return ""


def _fetch_gemini_key():
    try:
        from lib.creds import get_first
        return get_first("gemini-api-key", prefer=("gemini-api-key", "google-ai-studio-key", "google-api-key"))
    except Exception as e:
        print(f"⚠️ Credentials fetch failed: {e}")
        return None


def _extract_json_object(text):
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def invoke_gemini_json(prompt):
    from lib.gemini import MODEL_VOLUME, invoke

    text = invoke(prompt, model=MODEL_VOLUME, temperature=0.1, json_mode=True, timeout=90)
    if not text:
        raise RuntimeError("gemini-api-key unavailable from credentials server or empty model response")
    parsed = _extract_json_object(text)
    if not parsed:
        raise RuntimeError(f"Gemini returned non-JSON: {text[:200]}")
    return parsed


def _compact_email_line(idx, entry):
    subject = decode_mime_text(entry.get("subject") or "No Subject")
    sender = decode_mime_text(entry.get("sender") or "Unknown")
    reason = (entry.get("reason") or "N/A")[:160]
    snippet = entry.get("snippet") or ""
    if entry.get("local_file") and not snippet:
        snippet = get_email_body_from_staging(entry["local_file"])
    snippet = " ".join(str(snippet).split())[:SNIPPET_CHARS]
    return (
        f"ID: {idx}\n"
        f"Subject: {subject}\n"
        f"Sender: {sender}\n"
        f"Triage Reason: {reason}\n"
        f"Snippet: {snippet}\n---\n"
    )


def heuristic_classify(emails):
    """Keyword fallback so a brief is never empty when the LLM is down."""
    free_audio = []
    needs_response = []
    for entry in emails:
        hay = " ".join([
            decode_mime_text(entry.get("subject") or ""),
            decode_mime_text(entry.get("sender") or ""),
            str(entry.get("reason") or ""),
            str(entry.get("snippet") or ""),
        ]).lower()
        item = entry.copy()
        if any(h in hay for h in AUDIO_FREE_HINTS) and not any(h in hay for h in AUDIO_PAID_HINTS):
            item["llm_reason"] = "Heuristic: looks like a free audio giveaway (LLM unavailable or skipped)."
            free_audio.append(item)
        if any(h in hay for h in ACTION_KEYWORDS):
            item = entry.copy()
            item["llm_reason"] = "Heuristic: subject/body matches billing, housing, security, or action-required language."
            needs_response.append(item)
    return {"free_audio": free_audio, "needs_response": needs_response}


def process_with_llm(emails):
    """
    Process a batch of emails using Gemini Flash Lite.
    Falls back to keyword heuristics if Gemini is unavailable.
    """
    if not emails:
        return {"free_audio": [], "needs_response": []}

    email_list_text = "".join(_compact_email_line(idx, e) for idx, e in enumerate(emails))
    prompt = f"""You are an expert personal assistant for Daniel Exall.
I am providing a list of emails that were caught in a junk filter or flagged for review.
Identify two types of content:

1. FREE_AUDIO: truly free audio software, plugins, libraries, or downloads.
   EXCLUDE special offers, discounts, introductory pricing, or free-with-purchase.
2. NEEDS_RESPONSE: genuine messages or alerts that require a direct response or action.
   Include anything that could impact living situation (utility bills, housing, security, legal).
   In your reason, mention the email content and the specific action required.

List of Emails:
{email_list_text}

Return JSON with two lists: free_audio and needs_response.
Each item: {{"id": <int>, "reason": "<detailed reason>"}}
"""

    try:
        result = invoke_gemini_json(prompt)
    except Exception as e:
        print(f"❌ LLM Processing Error: {e}")
        print("↪️ Falling back to keyword heuristics for this batch.")
        return heuristic_classify(emails)

    final_result = {"free_audio": [], "needs_response": []}
    for key in ("free_audio", "needs_response"):
        for item in result.get(key, []) or []:
            try:
                idx = int(item["id"])
                if 0 <= idx < len(emails):
                    email_item = emails[idx].copy()
                    email_item["llm_reason"] = item.get("reason", "N/A")
                    final_result[key].append(email_item)
            except (KeyError, TypeError, ValueError):
                continue
    return final_result


def _format_classified(title, entries):
    if not entries:
        return ""
    content = f"## {title}\n"
    for entry in entries:
        subject = decode_mime_text(entry.get("subject") or "No Subject")
        sender = decode_mime_text(entry.get("sender") or "Unknown")
        snippet = " ".join(str(entry.get("snippet") or "No snippet").split())[:150]
        content += f"- **{subject}**\n"
        content += f"  - Sender: {sender}\n"
        content += f"  - Reason: {entry.get('llm_reason', 'N/A')}\n"
        content += f"  - Snippet: {snippet}...\n\n"
    return content


def _format_inventory(emails):
    if not emails:
        return ""
    content = f"## ⚠️ Failed Triage Inventory ({len(emails)})\n\n"
    for entry in emails:
        subject = decode_mime_text(entry.get("subject") or "No Subject")
        sender = decode_mime_text(entry.get("sender") or "Unknown")
        reason = entry.get("reason") or "N/A"
        snippet = " ".join(str(entry.get("snippet") or "").split())[:180]
        content += f"- **{subject}** — {sender}\n"
        content += f"  - Filter: {reason}\n"
        if snippet:
            content += f"  - {snippet}\n"
        content += "\n"
    return content


def generate_brief(target_date=None, batch_emails=None, cleanup=True):
    """
    Generates a daily briefing.
    Can be used for the current day or for a batch of historical emails (backfill mode).
    """
    config = load_config()
    primary_email = get_primary_email(config)

    if target_date is None:
        target_date = date.today()

    if batch_emails is None:
        junk_data = []
        if JUNK_CACHE_FILE.exists():
            with open(JUNK_CACHE_FILE, "r") as f:
                try:
                    junk_data = json.load(f)
                except Exception:
                    pass
        emails_to_process = [
            e for e in junk_data if parse_email_date(e.get("date", "")) == target_date
        ]
    else:
        emails_to_process = batch_emails

    llm_free_audio = []
    llm_needs_response = []

    for i in range(0, len(emails_to_process), LLM_BATCH_SIZE):
        batch = emails_to_process[i:i + LLM_BATCH_SIZE]
        print(f"🧠 Processing batch of {len(batch)} emails with Gemini Flash Lite...")
        batch_result = process_with_llm(batch)
        llm_free_audio.extend(batch_result["free_audio"])
        llm_needs_response.extend(batch_result["needs_response"])

    important_updates = []
    if batch_emails is None:
        staged_updates = get_staged_updates(target_date)
        important_updates = [u for u in staged_updates if u["is_important"]]

    if not llm_free_audio and not llm_needs_response and not important_updates and not emails_to_process:
        print(f"ℹ️ No significant updates found for {target_date}")
        return

    subject = f"[Daily Briefing] Life & Email Summary - {target_date.isoformat()}"
    if batch_emails:
        dates = [parse_email_date(e.get("date", "")) for e in batch_emails if parse_email_date(e.get("date", ""))]
        if dates:
            subject = f"[Batch Briefing] Email Summary - {min(dates).isoformat()} to {max(dates).isoformat()}"

    content = f"# {subject}\n\n"
    content += f"**Date:** {datetime.now().isoformat()}\n\n"
    content += _format_classified("📩 Response Required (Failed Triage)", llm_needs_response)
    content += _format_classified("🎁 Truly FREE Audio Offers", llm_free_audio)

    if important_updates:
        content += "## ⚡ Important Life Updates\n"
        for u in important_updates:
            content += f"- **{u['subject']}** (Saved as: {u['file']})\n"
        content += "\n"

    content += _format_inventory(emails_to_process)

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

    if cleanup and batch_emails is None and JUNK_CACHE_FILE.exists():
        try:
            with open(JUNK_CACHE_FILE, "r") as f:
                current_junk = json.load(f)
            remaining_junk = [
                e for e in current_junk if parse_email_date(e.get("date", "")) != target_date
            ]
            with open(JUNK_CACHE_FILE, "w") as f:
                json.dump(remaining_junk, f, indent=2)
            print(f"🧹 Cleaned up {len(emails_to_process)} entries from junk cache.")
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

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

    print("📡 Sending briefing to Notion...")
    try:
        from email_utils import send_to_notion
        result = send_to_notion(notion_metadata)
        if "error" not in result:
            print("🔔 Briefing sent to Notion successfully.")
        else:
            print(f"⚠️ Failed to send to Notion: {result['error']}")
    except Exception as e:
        print(f"❌ Error sending to Notion: {e}")

    return filepath


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate the BiOS daily email/life briefing.")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--no-cleanup", action="store_true", help="Do not remove processed rows from junk cache")
    args = parser.parse_args()
    target = date.fromisoformat(args.date) if args.date else date.today()
    generate_brief(target_date=target, cleanup=not args.no_cleanup)
