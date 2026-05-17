#!/usr/bin/env python3
"""
Staging Re-Push Utility
=======================
Iterates all .md files in the email staging directory, parses their
frontmatter, applies the new Auto-Read subject routing, and pushes
a corrected payload to localhost:8000/email to update Notion.

Usage:
    python3 scripts/email/repush_staging.py [--dry-run] [--limit N]

Options:
    --dry-run   Print payloads without sending requests
    --limit N   Process only the first N files (default: all)
"""

import sys
import json
import time
import argparse
import requests
from pathlib import Path

STAGING_DIR = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "staging"
WEBHOOK_URL = "http://localhost:8000/email"

# ── Auto-Read routing patterns (mirrors daemon logic) ─────────────────────────

def is_auto_read(subject: str) -> bool:
    """Return True if the subject matches any auto-read pattern."""
    s = subject.lower()
    return (
        "recycling collection" in s
        or "security alert" in s
        or "login from a new device" in s
        or ("new" in s and "login" in s)
        or ("verify" in s and "login" in s)
        or ("delivered" in s and "items" in s)
    )


# ── Frontmatter parser ────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Parse YAML-style frontmatter delimited by `---`.
    Returns (metadata_dict, body_text).
    Falls back gracefully if no frontmatter is found.
    """
    meta = {}
    body = text

    if not text.startswith("---"):
        return meta, body

    try:
        end = text.index("---", 3)
        fm_block = text[3:end].strip()
        body = text[end + 3:].strip()

        for line in fm_block.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
    except (ValueError, IndexError):
        pass

    return meta, body


# ── Main re-push logic ────────────────────────────────────────────────────────

def repush(dry_run: bool = False, limit: int = None):
    md_files = sorted(STAGING_DIR.glob("*.md"))

    if not md_files:
        print(f"❌ No .md files found in {STAGING_DIR}")
        sys.exit(1)

    if limit:
        md_files = md_files[:limit]

    print(f"📂 Staging dir : {STAGING_DIR}")
    print(f"🔗 Webhook URL : {WEBHOOK_URL}")
    print(f"📋 Files found : {len(md_files)}")
    print(f"🧪 Dry run     : {dry_run}")
    print("─" * 60)

    success = skipped = failed = 0

    for filepath in md_files:
        text = filepath.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(text)

        subject   = meta.get("subject", filepath.stem)
        sender    = meta.get("sender", "unknown")
        recipient = meta.get("recipient", "")
        date_str  = meta.get("date", "")

        status = "Read" if is_auto_read(subject) else "New"
        old_status = meta.get("status", "—")

        payload = {
            "type": "email",
            "subject": subject,
            "from": sender,
            "recipient": recipient,
            "received_at": date_str,
            "body": body,
            "local_file": filepath.name,
            "status": status
        }

        label = "Read (auto-routed)" if status == "Read" else "New"
        changed = " [STATUS CHANGED]" if old_status != status else ""
        print(f"  {'[DRY]' if dry_run else '     '} {filepath.name[:55]:<55} → {label}{changed}")

        if dry_run:
            skipped += 1
            continue

        try:
            resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            if resp.status_code == 200:
                success += 1
            else:
                print(f"    ⚠️  HTTP {resp.status_code}: {resp.text[:120]}")
                failed += 1
        except requests.ConnectionError:
            print(f"    ❌ Connection refused — is copaw-webhook-receiver running on port 8000?")
            failed += 1
        except Exception as e:
            print(f"    ❌ {e}")
            failed += 1

        # Polite pacing — avoid hammering the local server
        time.sleep(0.15)

    print("─" * 60)
    if dry_run:
        print(f"✅ Dry run complete. {len(md_files)} files would be processed.")
    else:
        print(f"✅ Done — Success: {success}  Failed: {failed}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-push staging emails to Notion via webhook")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without sending")
    parser.add_argument("--limit", type=int, default=None, help="Process only N files")
    args = parser.parse_args()

    repush(dry_run=args.dry_run, limit=args.limit)
