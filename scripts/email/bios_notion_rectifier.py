#!/usr/bin/env python3
"""
BiOS Notion Data Rectifier (v1.0.0)
Reconstructs legacy email files from Notion payloads and reconciles the ledger.
"""

import httpx
import json
import os
import re
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Setup logging
LOG_DIR = Path.home() / "biomimetics" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "bios_notion_rectifier.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NotionRectifier")

# Configuration
CREDENTIALS_SERVER_URL = "http://localhost:8089"
CREDENTIALS_API_KEY_FILE = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
NOTION_TRIAGE_DB_ID = "3284d2d9-fc7c-81bd-9a91-e865511e642f"
VAULT_DIR = Path.home() / "biomimetics" / "docs" / "personal" / "emails" / "vault"

TARGET_SUBJECTS = [
    "FW: Citizens Advice",
    "Fwd: Secure File Transfer from Wakefield Council",
    "RE: [External] REVISED: STAGE 2 COMPLAINT",
    "RE: Citizens Advice",
    "Receipt of Email",
    "Citizens Advice"
]

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

def query_notion_for_rectification(notion_token):
    """Query Notion for records matching target subjects"""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.post(
            f"https://api.notion.com/v1/databases/{NOTION_TRIAGE_DB_ID}/query",
            headers=headers,
            json={},
            timeout=30
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        
        matches = []
        for page in results:
            props = page.get("properties", {})
            
            # Check subject
            name_list = props.get("Name", {}).get("title", [])
            subject = name_list[0].get("plain_text", "") if name_list else ""
            
            # Check Email Handling
            handling = props.get("Email Handling", {}).get("select") or {}
            handling_name = handling.get("name", "")
            
            # Check Auth Trigger
            auth_trigger = props.get("Auth Trigger", {}).get("checkbox", False)
            
            if any(target in subject for target in TARGET_SUBJECTS):
                if handling_name == "To Memory" and auth_trigger:
                    matches.append(page)
                
        return matches
    except Exception as e:
        logger.error(f"Failed to query Notion: {e}")
        return []

def sanitize_filename(name):
    """Sanitize string for filename"""
    # Remove common email prefixes
    name = re.sub(r'^(RE:|FW:|Fwd:|REVISED:)\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[^\w\s-]', '', name).strip()
    name = re.sub(r'[-\s]+', '_', name)
    return name[:50] # Truncate for safety

def extract_date_from_payload(payload):
    """Extract YYYY-MM-DD from payload or return default"""
    match = re.search(r'(\d{4}-\d{2}-\d{2})', payload)
    if match:
        return match.group(1)
    return "2026-01-10"

def update_notion_ledger(notion_token, page_id, filename, dry_run=False):
    """Perform the standard reset on the Notion record"""
    if dry_run:
        logger.info(f"[DRY RUN] Would update Notion page {page_id} with Local File: {filename}")
        return True
        
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    update_payload = {
        "properties": {
            "Auth Trigger": { "checkbox": False },
            "Email Handling": { "select": None },
            "Local File": { "rich_text": [{"text": {"content": filename}}] },
            "Status": { "select": { "name": "Archived" } }
        }
    }
    
    try:
        response = httpx.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json=update_payload,
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Successfully reconciled Notion page: {page_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to update Notion page {page_id}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="BiOS Notion Data Rectifier")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing")
    args = parser.parse_args()

    logger.info("="*60)
    logger.info(f"🛠️  BiOS Notion Data Rectifier (v1.0.0) - {datetime.now().isoformat()}")
    if args.dry_run:
        logger.info("⚠️  DRY RUN MODE ENABLED")
    logger.info("="*60)
    
    notion_token = fetch_notion_api_key()
    if not notion_token:
        logger.error("Could not fetch Notion API key. Aborting.")
        return

    items = query_notion_for_rectification(notion_token)
    logger.info(f"Found {len(items)} matching legacy records.")
    
    rectified_count = 0
    
    for page in items:
        props = page.get("properties", {})
        page_id = page.get("id")
        
        # Subject
        name_list = props.get("Name", {}).get("title", [])
        subject = name_list[0].get("plain_text", "Unknown") if name_list else "Unknown"
        
        # Payload
        payload_list = props.get("Payload", {}).get("rich_text", [])
        payload = "".join([t.get("plain_text", "") for t in payload_list])
        
        if not payload:
            logger.warning(f"No payload found for '{subject}'. Skipping reconstruction.")
            continue
            
        # Filename construction
        date_str = extract_date_from_payload(payload)
        sanitized_subject = sanitize_filename(subject)
        filename = f"{date_str}_{sanitized_subject}.md"
        
        file_path = VAULT_DIR / filename
        
        logger.info(f"Rectifying: {subject}")
        logger.info(f"-> Generated Filename: {filename}")
        
        if args.dry_run:
            logger.info(f"[DRY RUN] Would write file to: {file_path}")
            update_notion_ledger(notion_token, page_id, filename, dry_run=True)
            rectified_count += 1
        else:
            try:
                VAULT_DIR.mkdir(parents=True, exist_ok=True)
                file_path.write_text(payload)
                logger.info(f"✅ Created file: {filename}")
                
                if file_path.exists():
                    update_notion_ledger(notion_token, page_id, filename)
                    rectified_count += 1
                else:
                    logger.error(f"❌ Verification failed: {filename} not found on disk after write.")
            except Exception as e:
                logger.error(f"❌ Error rectifying {subject}: {e}")

    logger.info("-" * 60)
    logger.info(f"📊 Rectification Results: {rectified_count} records processed.")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
