#!/usr/bin/env python3
"""
BiOS Notion Vault Sweeper (v1.3.1)
Stabilizes the email triage and ingestion workflow by aligning with the "BiOS Authorisation" schema.

Logic:
1. Fetch all pages from "BiOS Authorisation" where "Auth Trigger" == True.
2. If "Email Handling" == "Read":
   - Delete file from staging/
   - TRASH Notion record (Move to Trash)
3. If "Email Handling" == "To Memory":
   - Move file from staging/ to vault/
   - VERIFY existence in vault/
   - TRASH Notion record (Move to Trash, only if move succeeds)
4. Persistent Ledger Safety: 
   - Records are only trashed if Auth Trigger == True.
   - Trashing uses Notion's 'archived: true' method.
"""

import httpx
import json
import os
import shutil
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
        logging.FileHandler(LOG_DIR / "notion_vault_sweeper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NotionVaultSweeper")

# Configuration
CREDENTIALS_SERVER_URL = "http://localhost:8089"
CREDENTIALS_API_KEY_FILE = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
NOTION_TRIAGE_DB_ID = "3284d2d9-fc7c-81bd-9a91-e865511e642f"

STAGING_DIR = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "staging"
VAULT_DIR = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "vault"

def get_credentials_api_key():
    if CREDENTIALS_API_KEY_FILE.exists():
        return CREDENTIALS_API_KEY_FILE.read_text().strip()
    return os.environ.get("CREDENTIALS_API_KEY", "")

def fetch_notion_api_key():
    api_key = get_credentials_api_key()
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

def query_authorized_items(notion_token):
    """Fetch items where 'Auth Trigger' is True"""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # Filter for Auth Trigger == True
    query_payload = {
        "filter": {
            "property": "Auth Trigger",
            "checkbox": {
                "equals": True
            }
        }
    }
    
    try:
        response = httpx.post(
            f"https://api.notion.com/v1/databases/{NOTION_TRIAGE_DB_ID}/query",
            headers=headers,
            json=query_payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        logger.error(f"Failed to query Notion: {e}")
        return []

def mark_notion_page_processed(notion_token, page_id, dry_run=False):
    """
    Finalize a record by moving it to the trash.
    The Trash Protocol is only triggered for successfully processed records.
    Uses the BiOS Handshake (Clear -> Trash).
    """
    from notion_utils import clear_handling_and_trash
    return clear_handling_and_trash(notion_token, page_id, dry_run=dry_run)

def main():
    parser = argparse.ArgumentParser(description="BiOS Notion Vault Sweeper")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without modifying filesystem or Notion")
    args = parser.parse_args()

    logger.info("="*60)
    logger.info(f"Sweep Active: BiOS Notion Vault Sweeper (v1.3.1) - {datetime.now().isoformat()}")
    if args.dry_run:
        logger.info("⚠️  DRY RUN MODE ENABLED")
    logger.info("="*60)
    
    notion_token = fetch_notion_api_key()
    if not notion_token:
        logger.error("Could not fetch Notion API key. Aborting.")
        return

    authorized_items = query_authorized_items(notion_token)
    logger.info(f"Found {len(authorized_items)} authorized items to process.")
    
    processed_count = 0
    error_count = 0
    
    for page in authorized_items:
        # Enforce 15 RPM limit (4s heartbeat)
        import time
        time.sleep(4)

        props = page.get("properties", {})
        page_id = page.get("id")
        
        # Metadata extraction
        name_list = props.get("Name", {}).get("title", [])
        subject = name_list[0].get("plain_text", "Unknown") if name_list else "Unknown"
        
        handling_select = props.get("Email Handling", {}).get("select")
        handling = handling_select.get("name") if handling_select else None
        
        file_list = props.get("Local File", {}).get("rich_text", [])
        filename = file_list[0].get("plain_text") if file_list else None
        
        if not filename:
            logger.warning(f"No 'Local File' specified for item: {subject}. Skipping.")
            continue
            
        # Daily Briefing Override
        if "daily briefing" in subject.lower():
            target_dir = Path.home() / "biomimetics" / "docs" / "personal" / "daily_briefings"
            logger.info(f"✨ Daily Briefing Override triggered for: {subject}")
        else:
            target_dir = VAULT_DIR

        staging_path = STAGING_DIR / filename
        vault_path = target_dir / filename
        
        # Logic Branch A: "Read" (Delete)
        if handling == "Read":
            logger.info(f"Route [READ]: Processing {filename}")
            if staging_path.exists():
                try:
                    if args.dry_run:
                        logger.info(f"[DRY RUN] Would delete staging file: {filename}")
                    else:
                        staging_path.unlink()
                        logger.info(f"✅ Deleted staging file: {filename}")
                    
                    mark_notion_page_processed(notion_token, page_id, dry_run=args.dry_run)
                    processed_count += 1
                except Exception as e:
                    logger.error(f"❌ Error processing {filename}: {e}")
                    error_count += 1
            else:
                logger.warning(f"⚠️  File not found in staging: {filename}. Marking Notion row as processed anyway.")
                mark_notion_page_processed(notion_token, page_id, dry_run=args.dry_run)
                processed_count += 1
                
        # Logic Branch B: "To Memory" (Move)
        elif handling == "To Memory":
            logger.info(f"Route [MEMORY]: Processing {filename}")
            if staging_path.exists():
                try:
                    if args.dry_run:
                        logger.info(f"[DRY RUN] Would move {filename} to vault")
                        mark_notion_page_processed(notion_token, page_id, dry_run=True)
                        processed_count += 1
                    else:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(staging_path), str(vault_path))
                        
                        # ATOMICITY REQUIREMENT: Verify existence in vault/
                        if vault_path.exists():
                            logger.info(f"✅ Verified {filename} in vault. Marking Notion row as processed.")
                            mark_notion_page_processed(notion_token, page_id)
                            processed_count += 1
                        else:
                            logger.error(f"❌ VERIFICATION FAILED: {filename} moved but not found in vault!")
                            error_count += 1
                except Exception as e:
                    logger.error(f"❌ Error moving {filename} to vault: {e}")
                    error_count += 1
            else:
                logger.error(f"❌ STAGING MISSING: {filename} not found in staging! Skipping Notion update.")
                error_count += 1
        
        else:
            logger.info(f"⏳ Route [PENDING]: Handling '{handling}' for '{subject}' - Awaiting user decision or Trash Protocol execution.")

    logger.info("-" * 60)
    logger.info(f"📊 Results: Processed {processed_count}, Errors {error_count}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
