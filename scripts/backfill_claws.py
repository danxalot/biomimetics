#!/usr/bin/env python3
"""
ARCA ProtonMail Backfill & Sync - Refactored for Phase 1 & 2
Fetches emails since 25-Dec-2025 via IMAP Bridge
Filters with local LLM before cloud transmission
Transmits to GCP Gateway with Obsidian link preparation
"""

import imaplib
import email
from email.header import decode_header
import openai
import os
import time
import json
import logging
import requests
from typing import Generator, Tuple, Optional
from urllib.parse import quote

# Configuration
IMAP_HOST = "127.0.0.1"  # Proton Bridge localhost
IMAP_PORT = 1143
LOCAL_LLM_BASE_URL = "http://localhost:11435/v1"
LOCAL_LLM_MODEL = "qwen3.5-2b-instruct"
SINCE_DATE = "25-Dec-2025"  # Format: DD-Mon-YYYY

# GCP Gateway Configuration
GCP_GATEWAY_URL = (
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
)
NOTION_TRIAGE_DB_ID = "3254d2d9fc7c81228daefc564e912546"

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def decode_mime_words(s):
    """Decode MIME encoded words in email headers."""
    if s is None:
        return ""
    decoded_parts = []
    for part, encoding in decode_header(s):
        if isinstance(part, bytes):
            if encoding:
                decoded_parts.append(part.decode(encoding))
            else:
                decoded_parts.append(part.decode("utf-8", errors="ignore"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


def get_imap_connection(username: str, password: str) -> imaplib.IMAP4:
    """Establish an IMAP connection with STARTTLS (not IMAP4_SSL)."""
    conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
    conn.starttls()  # Upgrade to secure connection
    conn.login(username, password)
    return conn


def fetch_emails_since(
    username: str, password: str, mailbox: str = "INBOX"
) -> Generator[Tuple[str, str, str], None, None]:
    """
    Fetch emails since SINCE_DATE from the specified mailbox.
    Yields tuples of (subject, sender, body_snippet).
    """
    try:
        conn = get_imap_connection(username, password)
        conn.select(mailbox)

        # Search for emails since the given date
        status, messages = conn.search(None, f'SINCE "{SINCE_DATE}"')
        if status != "OK":
            logger.error("Failed to search emails")
            return

        email_ids = messages[0].split()
        logger.info(f"Found {len(email_ids)} emails since {SINCE_DATE}")

        for eid in email_ids:
            status, msg_data = conn.fetch(eid, "(RFC822)")
            if status != "OK":
                logger.error(f"Failed to fetch email {eid}")
                continue

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = decode_mime_words(msg["Subject"])
                    sender = decode_mime_words(msg["From"])

                    # Extract a snippet of the body (first 500 characters of plain text)
                    body_snippet = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type == "text/plain":
                                charset = part.get_content_charset() or "utf-8"
                                payload = part.get_payload(decode=True)
                                if payload is not None:
                                    if isinstance(payload, bytes):
                                        body = payload.decode(charset, errors="ignore")
                                    else:
                                        body = str(payload)
                                    body_snippet = body[:500]
                                    break
                    else:
                        charset = msg.get_content_charset() or "utf-8"
                        payload = msg.get_payload(decode=True)
                        if payload is not None:
                            if isinstance(payload, bytes):
                                body = payload.decode(charset, errors="ignore")
                            else:
                                body = str(payload)
                            body_snippet = body[:500]

                    yield subject, sender, body_snippet

        conn.close()
        conn.logout()
    except Exception as e:
        logger.error(f"Error in fetch_emails_since: {e}")
        raise


def is_email_significant(subject: str, sender: str) -> bool:
    """
    Use local LLM to determine if an email is significant (human communication, actionable task, or important alert).
    Returns True if significant (LLM responds YES), False otherwise.
    """
    try:
        client = openai.OpenAI(
            base_url=LOCAL_LLM_BASE_URL,
            api_key="not-needed",  # Local server doesn't require a real API key
        )

        # Handle None values for subject and sender
        subject_str = subject if subject is not None else ""
        sender_str = sender if sender is not None else ""

        prompt = f"""Is this email a human communication, an actionable task, or an important alert? 
Subject: {subject_str}
Sender: {sender_str}
Reply exactly with YES or NO."""

        response = client.chat.completions.create(
            model=LOCAL_LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise email classifier. Respond only with YES or NO.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=10,
        )

        # Handle potential None response from LLM
        message_content = response.choices[0].message.content
        if message_content is None:
            logger.warning("LLM returned None response, treating as insignificant")
            return False

        result = message_content.strip().upper()
        return result == "YES"
    except Exception as e:
        logger.error(f"Error in LLM significance check: {e}")
        # Fail safe: treat as not significant if LLM fails to avoid false positives
        return False


def create_obsidian_uri(subject: str) -> str:
    """Create a standardized Obsidian URI string from email subject."""
    # Handle None subject
    if subject is None:
        subject = ""
    # Sanitize subject for use in file path: remove/replace problematic characters
    subject_slug = "".join(c if c.isalnum() or c in " ._-" else "_" for c in subject)
    subject_slug = subject_slug.strip().replace(" ", "_")
    # Limit length to avoid filesystem issues
    if len(subject_slug) > 100:
        subject_slug = subject_slug[:100]
    return f"[Obsidian Note](obsidian://open?vault=Obsidian%20Vault&file=Email_Triage/{subject_slug})"


def create_gcp_payload(subject: str, sender: str, body_snippet: str) -> dict:
    """
    Construct JSON payload for GCP Memory Gateway.
    Maps to Notion Life OS Triage DB.
    """
    # Handle None values
    subject_str = subject if subject is not None else ""
    sender_str = sender if sender is not None else "Unknown Sender"

    # Truncate body snippet to 500 characters
    content = body_snippet[:500] if body_snippet is not None else ""
    # Add sender info
    content = f"From: {sender_str}\n\n{content}"
    # Add Obsidian link placeholder
    obsidian_link = create_obsidian_uri(subject_str)
    content = f"{content}\n\n{obsidian_link}"

    payload = {
        "database_id": NOTION_TRIAGE_DB_ID,
        "properties": {
            "Title": {"title": [{"text": {"content": subject_str}}]},
            "Status": {"select": {"name": "Triage"}},
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                },
            }
        ],
    }
    return payload


def send_to_gcp_gateway(payload: dict, max_retries: int = 5) -> bool:
    """
    Send payload to GCP Gateway with exponential backoff.
    Returns True if successful, False otherwise.
    """
    for attempt in range(max_retries):
        try:
            response = requests.post(GCP_GATEWAY_URL, json=payload, timeout=30)

            if response.status_code == 200:
                title_content = payload["properties"]["Title"]["title"][0]["text"][
                    "content"
                ]
                logger.info(
                    f"Successfully sent to GCP Gateway: {title_content[:50]}..."
                )
                return True
            else:
                logger.warning(
                    f"GCP Gateway returned status {response.status_code}: {response.text}"
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"Request to GCP Gateway failed (attempt {attempt + 1}): {e}")

        # Exponential backoff: wait 2^attempt seconds before retrying
        if attempt < max_retries - 1:  # Don't wait after the last attempt
            wait_time = 2**attempt
            logger.info(f"Waiting {wait_time} seconds before retry...")
            time.sleep(wait_time)

    logger.error(f"Failed to send to GCP Gateway after {max_retries} attempts")
    return False


# Example usage (not part of the requested functions, but for context)
if __name__ == "__main__":
    # This would be replaced by actual credential handling
    username = "user@protonmail.com"
    # In practice, retrieve password securely:
    # password = open(os.path.expanduser("~/biomimetics/secrets/proton_bridge_password")).read().strip()
    password = "example_password"  # Placeholder

    for subject, sender, snippet in fetch_emails_since(username, password):
        if is_email_significant(subject, sender):
            logger.info(f"Significant email: {subject} from {sender}")
            # Phase 2: Create payload and send to GCP Gateway
            payload = create_gcp_payload(subject, sender, snippet)
            success = send_to_gcp_gateway(payload)
            if success:
                logger.info(f"Email routed to Triage: {subject}")
            else:
                logger.error(f"Failed to route email to Triage: {subject}")
        else:
            logger.info(f"Insignificant email skipped: {subject} from {sender}")
