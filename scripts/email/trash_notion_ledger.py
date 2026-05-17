"""
BiOS Notion Trash Protocol (v1.1.0)
Explicit trashing of records where Auth Trigger is True and Email Handling is Empty.
This allows for manual disposal of records while preserving the 'Auth Trigger: False' ledger.
"""

import httpx
import os
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
        logging.FileHandler(LOG_DIR / "clear_processed_board.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TrashProtocol")

# Configuration
CREDENTIALS_SERVER_URL = "http://localhost:8089"
CREDENTIALS_API_KEY_FILE = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
NOTION_TRIAGE_DB_ID = "3284d2d9-fc7c-81bd-9a91-e865511e642f"

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

def query_records_for_trash(notion_token):
    """
    Query Notion for records specifically marked for destruction:
    - Auth Trigger == True
    - Email Handling == Empty
    """
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    query = {
        "filter": {
            "and": [
                {
                    "property": "Auth Trigger",
                    "checkbox": { "equals": True }
                },
                {
                    "property": "Email Handling",
                    "select": { "is_empty": True }
                }
            ]
        }
    }
    
    all_results = []
    has_more = True
    start_cursor = None
    
    try:
        while has_more:
            payload = query.copy()
            if start_cursor:
                payload["start_cursor"] = start_cursor
                
            response = httpx.post(
                f"https://api.notion.com/v1/databases/{NOTION_TRIAGE_DB_ID}/query",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            all_results.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")
            
        return all_results
    except Exception as e:
        logger.error(f"Failed to query Notion: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="BiOS Notion Trash Protocol")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing")
    args = parser.parse_args()

    logger.info("="*60)
    logger.info(f"🗑️  BiOS Trash Protocol (v1.1.0) - {datetime.now().isoformat()}")
    if args.dry_run:
        logger.info("⚠️  DRY RUN MODE ENABLED")
    logger.info("="*60)
    
    notion_token = fetch_notion_api_key()
    if not notion_token:
        logger.error("Could not fetch Notion API key. Aborting.")
        return

    items = query_records_for_trash(notion_token)
    logger.info(f"Found {len(items)} records specifically marked for destruction.")
    
    if len(items) == 0:
        logger.info("Nothing to trash. Triage board matches persistent ledger rules.")
        return

    trashed_count = 0
    for page in items:
        page_id = page.get("id")
        # Extract name for logging
        props = page.get("properties", {})
        name_list = props.get("Name", {}).get("title", [])
        subject = name_list[0].get("plain_text", "Unknown") if name_list else "Unknown"
        
        logger.info(f"Trashing: {subject}")
        if trash_notion_record(notion_token, page_id, dry_run=args.dry_run):
            trashed_count += 1

    logger.info("-" * 60)
    logger.info(f"📊 Results: {trashed_count} records trashed.")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
