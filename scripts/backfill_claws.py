#!/usr/bin/env python3
"""
ARCA ProtonMail Backfill & Sync
Fetches emails from all 5 Proton accounts via IMAP Bridge
Summarizes with local Ollama model and sends to GCP Gateway
"""

import os
import sys
import email
import imaplib
import datetime
import requests
import json
import logging
from email import policy
from dateutil import parser

# Configuration
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
OLLAMA_API = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "deepseek-r1-1.5b"

# Proton Bridge Configuration
PROTON_BRIDGE_HOST = "127.0.0.1"
PROTON_BRIDGE_PORT = 1143

# 5 Proton Accounts
PROTON_ACCOUNTS = [
    {"email": "dan.exall@pm.me", "password": "ayaOq50DHJRuB1CsH2OoIA"},
    {"email": "dan@arca-vsa.tech", "password": "ayaOq50DHJRuB1CsH2OoIA"},
    {"email": "claws@pm.me", "password": "ayaOq50DHJRuB1CsH2OoIA"},
    {"email": "arca@pm.me", "password": "ayaOq50DHJRuB1CsH2OoIA"},
    {"email": "info@pm.me", "password": "ayaOq50DHJRuB1CsH2OoIA"},
]

# Time window: Last 3 months
CUTOFF_DATE = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)

# State tracking
STATE_FILE = os.path.expanduser("~/.arca/proton_sync_state.json")
LOG_FILE = os.path.expanduser("~/.arca/proton_sync.log")

# Setup logging
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_state():
    """Load processed email IDs from state file."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"processed_ids": set(), "last_sync": None}


def save_state(state):
    """Save processed email IDs to state file."""
    state["processed_ids"] = list(state["processed_ids"])
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    state["processed_ids"] = set(state["processed_ids"])  # Convert back for runtime


def summarize_with_local_model(text):
    """Generate 2-sentence summary using local Ollama model."""
    if not text or len(text.strip()) < 50:
        return "Email too short for meaningful summary."
    
    prompt = f"Summarize the following email thread in exactly two sentences, focusing on actionable decisions or project updates:\n\n{text[:2000]}"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_API, json=payload, timeout=60)
        return response.json().get("response", "Summary generation failed.")
    except Exception as e:
        logger.error(f"Local AI Error: {e}")
        return "Summary generation failed due to AI service unavailable."


def fetch_emails_from_account(account_config, state):
    """Fetch emails from a single Proton account via IMAP."""
    email_addr = account_config["email"]
    password = account_config["password"]
    processed_count = 0
    skipped_count = 0

    try:
        logger.info(f"Connecting to Proton Bridge for: {email_addr}")
        mail = imaplib.IMAP4_SSL(PROTON_BRIDGE_HOST, PROTON_BRIDGE_PORT)
        mail.login(email_addr, password)
        mail.select('INBOX')

        # Search for ALL emails, then filter by date
        status, messages = mail.search(None, 'ALL')

        if status != 'OK':
            logger.warning(f"No messages found for {email_addr}")
            mail.logout()
            return 0

        msg_ids = messages[0].split()
        logger.info(f"Found {len(msg_ids)} total emails for {email_addr}")

        # Process emails (newest first, limit to 100 per account per sync)
        for msg_id in reversed(msg_ids[-100:]):
            try:
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue

                msg = email.message_from_bytes(msg_data[0][1])

                # Get unique ID
                msg_uid = msg.get('Message-ID', f"{email_addr}-{msg_id.decode()}")
                if msg_uid in state["processed_ids"]:
                    skipped_count += 1
                    continue

                # Parse Date
                date_str = msg.get("Date")
                if not date_str:
                    continue

                try:
                    email_date = parser.parse(date_str)
                    if email_date.tzinfo is None:
                        email_date = email_date.replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    continue

                # Check cutoff date
                if email_date < CUTOFF_DATE:
                    continue  # Skip old emails

                # Extract metadata
                subject = msg.get("Subject", "No Subject")
                sender = msg.get("From", "Unknown Sender")

                # Extract plain text body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            try:
                                body += part.get_content()
                            except:
                                pass
                else:
                    try:
                        body = msg.get_content()
                    except:
                        pass

                if not body or len(body.strip()) < 10:
                    logger.info(f"Skipping empty email: {subject}")
                    continue

                logger.info(f"Processing: {subject} ({email_date.date()}) from {email_addr}")

                # Generate summary
                summary = summarize_with_local_model(body)

                # Build payload for GCP Gateway
                memory_payload = {
                    "source": email_addr,
                    "type": "email_archive",
                    "timestamp": email_date.isoformat(),
                    "metadata": {
                        "subject": subject,
                        "sender": sender,
                        "summary": summary,
                        "account": email_addr
                    },
                    "content": body[:5000]  # Limit content size
                }

                # Send to GCP Gateway
                try:
                    response = requests.post(GCP_GATEWAY_URL, json=memory_payload, timeout=30)
                    if response.status_code == 200:
                        logger.info(f"✓ Memorized: {subject[:50]}...")
                    else:
                        logger.warning(f"Gateway rejected: {response.status_code}")
                except Exception as e:
                    logger.error(f"Failed to send to gateway: {e}")

                # Mark as processed
                state["processed_ids"].add(msg_uid)
                processed_count += 1

            except Exception as e:
                logger.error(f"Error processing message {msg_id}: {e}")
                continue

        mail.logout()

    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP error for {email_addr}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error for {email_addr}: {e}")

    logger.info(f"Account {email_addr}: {processed_count} processed, {skipped_count} skipped")
    return processed_count


def sync_all_accounts():
    """Main sync function - fetches from all 5 Proton accounts."""
    logger.info("=" * 60)
    logger.info("ARCA ProtonMail Sync - Starting")
    logger.info(f"Cutoff Date: {CUTOFF_DATE.date()}")
    logger.info("=" * 60)

    state = load_state()
    total_processed = 0

    for account in PROTON_ACCOUNTS:
        count = fetch_emails_from_account(account, state)
        total_processed += count

    state["last_sync"] = datetime.datetime.now().isoformat()
    save_state(state)

    logger.info("=" * 60)
    logger.info(f"Sync Complete: {total_processed} new emails processed")
    logger.info(f"State saved to: {STATE_FILE}")
    logger.info("=" * 60)

    return total_processed


if __name__ == "__main__":
    sync_all_accounts()
