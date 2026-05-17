#!/usr/bin/env python3
"""
BiOS Recovery Specialist (v1.0.0)
Advanced metadata extraction and 'True Recovery' logic for legacy records.
"""

import httpx
import json
import os
import re
import logging
import argparse
from pathlib import Path
from datetime import datetime
from notion_utils import trash_notion_record

# Setup logging
LOG_DIR = Path.home() / "biomimetics" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "bios_recovery_specialist.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("RecoverySpecialist")

# Configuration
CREDENTIALS_SERVER_URL = "http://localhost:8089"
CREDENTIALS_API_KEY_FILE = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
NOTION_TRIAGE_DB_ID = "3284d2d9-fc7c-81bd-9a91-e865511e642f"
VAULT_DIR = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "vault"

def fetch_notion_api_key():
    if CREDENTIALS_API_KEY_FILE.exists():
        api_key = CREDENTIALS_API_KEY_FILE.read_text().strip()
    else:
        api_key = os.environ.get("CREDENTIALS_API_KEY", "")
        
    try:
        response = httpx.get(
            f"{CREDENTIALS_SERVER_URL}/secrets/notion-api-key",
            headers={"X-API-Key": api_key},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("value", "")
    except Exception as e:
        logger.error(f"Error fetching Notion key: {e}")
    return ""

def query_notion_for_recovery(notion_token):
    """Query Notion for records that need recovery (Auth Trigger == True)"""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    query = {
        "filter": {
            "property": "Auth Trigger",
            "checkbox": { "equals": True }
        }
    }
    
    try:
        response = httpx.post(
            f"https://api.notion.com/v1/databases/{NOTION_TRIAGE_DB_ID}/query",
            headers=headers,
            json=query,
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        logger.error(f"Failed to query Notion: {e}")
        return []

def parse_payload(payload_str):
    """Parse JSON payload and extract metadata"""
    try:
        data = json.loads(payload_str)
        metadata = {
            "from": data.get("from", "Unknown"),
            "to": data.get("recipient", "Unknown"),
            "subject": data.get("subject", "No Subject"),
            "date": data.get("received_at", ""),
            "body": data.get("body", "")
        }
        return metadata
    except Exception as e:
        logger.warning(f"Failed to parse payload as JSON: {e}")
        return None

def sanitize_filename(name):
    name = re.sub(r'^(RE:|FW:|Fwd:|REVISED:)\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[^\w\s-]', '', name).strip()
    name = re.sub(r'[-\s]+', '_', name)
    return name[:50]

def main():
    parser = argparse.ArgumentParser(description="BiOS Recovery Specialist")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing")
    args = parser.parse_args()

    logger.info("="*60)
    logger.info(f"🛠️  BiOS Recovery Specialist (v1.0.0) - {datetime.now().isoformat()}")
    if args.dry_run:
        logger.info("⚠️  DRY RUN MODE ENABLED")
    logger.info("="*60)
    
    notion_token = fetch_notion_api_key()
    if not notion_token:
        logger.error("Could not fetch Notion API key. Aborting.")
        return

    items = query_notion_for_recovery(notion_token)
    logger.info(f"Found {len(items)} records pending recovery.")
    
    recovered_count = 0
    trashed_count = 0
    
    for page in items:
        # Enforce 15 RPM limit (4s heartbeat)
        import time
        time.sleep(4)
        
        page_id = page.get("id")
        props = page.get("properties", {})
        
        # Payload extraction
        payload_list = props.get("Payload", {}).get("rich_text", [])
        payload_str = "".join([t.get("plain_text", "") for t in payload_list])
        
        if not payload_str:
            logger.warning(f"Empty payload for page {page_id}. Trashing.")
            from notion_utils import clear_handling_and_trash
            clear_handling_and_trash(notion_token, page_id, dry_run=args.dry_run)
            trashed_count += 1
            continue
            
        metadata = parse_payload(payload_str)
        if not metadata:
            logger.warning(f"Unparseable payload for page {page_id}. Skipping.")
            continue
            
        # Validation: Substantial body check
        body = metadata["body"]
        if not body or len(body.strip()) < 50:
            logger.info(f"[DISPOSED - NO BODY] Subject: {metadata['subject']}")
            from notion_utils import clear_handling_and_trash
            clear_handling_and_trash(notion_token, page_id, dry_run=args.dry_run)
            trashed_count += 1
            continue
            
        # Filename construction
        date_raw = metadata["date"]
        # Simple date extraction YYYY-MM-DD
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_raw)
        date_str = date_match.group(1) if date_match else "2026-01-10"
        
        # Daily Briefing Override
        if "daily briefing" in metadata["subject"].lower():
            target_dir = Path.home() / "biomimetics" / "docs" / "personal" / "daily_briefings"
            logger.info(f"✨ Daily Briefing Override triggered for: {metadata['subject']}")
        else:
            target_dir = VAULT_DIR
        
        filename = f"{date_str}_{sanitize_filename(metadata['subject'])}.md"
        file_path = target_dir / filename
        
        content = f"""---
from: {metadata['from']}
to: {metadata['to']}
subject: {metadata['subject']}
date: {metadata['date']}
---

{body}
"""
        
        if args.dry_run:
            logger.info(f"[DRY RUN] Would recover: {filename} to {target_dir}")
            recovered_count += 1
        else:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
                logger.info(f"✅ Recovered: {filename}")
                
                # Handshake Protocol: Verify -> Clear -> Trash
                if file_path.exists():
                    from notion_utils import clear_handling_and_trash
                    if clear_handling_and_trash(notion_token, page_id):
                        recovered_count += 1
                else:
                    logger.error(f"❌ Verification failed for {filename}. Not trashing Notion record.")
            except Exception as e:
                logger.error(f"❌ Error recovering {filename}: {e}")

    logger.info("-" * 60)
    logger.info(f"📊 Results: {recovered_count} recovered, {trashed_count} trashed.")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
