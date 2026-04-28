#!/usr/bin/env python3
"""
Hybrid Triage Tester - Rule-Based + LLM Filtering
Production-ready with strict regex, header-only matching, and multi-account support.

All secrets fetched from Credentials Server only.
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

# --- CONFIGURATION ---
CREDENTIALS_FILE = "/Users/danexall/biomimetics/secrets/credentials_api_key"
CRED_SERVER_URL = "http://localhost:8089/secrets"
LLM_URL = "http://localhost:11435/v1/chat/completions"
TEST_BATCH_SIZE = 10  # Per account

# The strict deterministic net (Word boundaries applied automatically)
KEEP_KEYWORDS = [
    "invoice",
    "receipt",
    "you sent",
    "payment",
    "octopus",
    "vultr",
    "azure",
    "ticket",
    "order",
    "document",
    "citizens advice",
    "cab",
    "debt",
    "arrears",
    "collection",
    "bailiff",
    "stepchange",
    "credit",
    "complaint",
    "appeal",
    "ombudsman",
    "watchdog",
    "legal",
    "solicitor",
    "police",
    "council",
    "security alert",
    "breach",
    "pwned",
    "unauthorized",
    "login",
]

# Build regex pattern for exact word boundaries
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
    """Fetch API key from local file (bootstraps credentials server access)."""
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Master key file missing: {CREDENTIALS_FILE}")
        print("   Run: echo -n 'YOUR_KEY' > {CREDENTIALS_FILE}")
        return None
    with open(CREDENTIALS_FILE, "r") as f:
        return f.read().strip()


def fetch_secret(secret_name, master_key):
    """Fetch secret from Credentials Server only - no local fallbacks."""
    req = urllib.request.Request(f"{CRED_SERVER_URL}/{secret_name}")
    req.add_header("X-API-Key", master_key)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("value")
    except urllib.error.HTTPError as e:
        print(f"❌ Credentials Server error for {secret_name}: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"❌ Failed to fetch secret {secret_name}: {e}")
        return None


def decode_header_value(header_value):
    """Safely decode email header with multiple encodings."""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    result = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8", errors="ignore")
        else:
            result += str(part)
    return result


def query_llm(subject, sender):
    """Query local Qwen3.5-2b model for email classification."""
    prompt = f"""You are a ruthless, precision email triage agent. Your ONLY job is to identify emails directly related to the personal, financial, legal, or business affairs of 'Daniel Exall' or 'Sheila Tilmouth'. You must be highly skeptical. 

Evaluate this email based on its sender and subject:
Sender: {sender}
Subject: {subject}

Reply STRICTLY with the word 'KEEP' or 'SKIP'. Do not output any other text."""

    data = {
        "model": "qwen3.5-2b-q8_0",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 10,
    }

    req = urllib.request.Request(
        LLM_URL, data=json.dumps(data).encode("utf-8")
    )
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            reply = result["choices"][0]["message"]["content"].strip().upper()
            return "KEEP" if "KEEP" in reply else "SKIP"
    except Exception:
        return "SKIP"  # Default to skip on LLM failure


# --- MAIN LOGIC ---
def run_triage():
    """Main triage function - processes all accounts sequentially."""
    master_key = get_master_key()
    if not master_key:
        return

    print("=" * 70)
    print("📧 Hybrid Triage Tester - Credentials Server Only")
    print("=" * 70)
    print(f"Credentials Server: {CRED_SERVER_URL}")
    print(f"LLM Endpoint: {LLM_URL}")
    print(f"Batch Size: {TEST_BATCH_SIZE} emails per account")
    print(f"Accounts: {len(ACCOUNTS)}")
    print("=" * 70)

    # Cache secrets so we don't spam the credentials server
    secrets_cache = {}

    for acc in ACCOUNTS:
        print(f"\n{'=' * 70}")
        print(f"📧 Scanning: {acc['email']} ({acc['type'].upper()})")
        print(f"{'=' * 70}")

        if acc["secret"] not in secrets_cache:
            pw = fetch_secret(acc["secret"], master_key)
            if not pw:
                print(f"  ⚠️  Skipping - could not fetch secret: {acc['secret']}")
                continue
            secrets_cache[acc["secret"]] = pw

        password = secrets_cache[acc["secret"]]
        mail = None

        try:
            if acc["type"] == "proton":
                # Proton Bridge: plain IMAP -> STARTTLS upgrade
                mail = imaplib.IMAP4("127.0.0.1", 1143)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                mail.starttls(ssl_context=ctx)
            else:
                # Gmail uses standard SSL
                mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)

            mail.login(acc["email"], password)
            mail.select("INBOX")

            status, messages = mail.search(None, "ALL")
            if status != "OK":
                print(f"  ⚠️  IMAP search failed")
                continue

            email_ids = messages[0].split()
            # Get latest N emails
            latest_ids = email_ids[-TEST_BATCH_SIZE:]

            if not latest_ids:
                print("  📬 Found 0 emails.")
                continue

            print(f"  📥 Processing {len(latest_ids)} emails...\n")

            for e_id in reversed(latest_ids):
                status, msg_data = mail.fetch(e_id, "(RFC822.HEADER)")
                if status != "OK":
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                raw_subject = msg.get("Subject", "")
                raw_from = msg.get("From", "")

                subject = decode_header_value(raw_subject)
                sender = decode_header_value(raw_from)

                combined_header_text = f"{subject} {sender}"

                # 1. Deterministic Net (Regex on Headers ONLY)
                if PATTERN.search(combined_header_text):
                    print(f"  ✅ [Rule] - [KEEP] - {subject[:60]}...")
                else:
                    # 2. LLM Fallback
                    llm_decision = query_llm(subject, sender)
                    if llm_decision == "KEEP":
                        print(f"  🧠 [LLM] - [KEEP] - {subject[:60]}...")
                    else:
                        print(f"  🚫 [LLM] - [SKIP] - {subject[:60]}...")

        except imaplib.IMAP4.error as e:
            print(f"  ❌ IMAP error for {acc['email']}: {e}")
        except Exception as e:
            print(f"  ❌ Error processing {acc['email']}: {e}")
        finally:
            if mail:
                try:
                    mail.close()
                    mail.logout()
                except Exception:
                    pass

    print(f"\n{'=' * 70}")
    print("✅ Triage complete")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    run_triage()
