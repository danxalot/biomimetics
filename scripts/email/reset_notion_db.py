#!/usr/bin/env python3
"""
Notion Triage Database Purge Script
Archives all pages in the BiOS Triage database.

Secure Auth: Fetches notion-api-key from Credentials Server at runtime.
"""

import httpx
import sys
import time
from pathlib import Path

# Configuration
CREDENTIALS_SERVER_URL = "http://localhost:8089"
CREDENTIALS_API_KEY_FILE = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
NOTION_TRIAGE_DB_ID = "3284d2d9-fc7c-81bd-9a91-e865511e642f"  # BiOS Triage


def get_credentials_api_key() -> str:
    """Load Credentials API key from secure file."""
    if CREDENTIALS_API_KEY_FILE.exists():
        return CREDENTIALS_API_KEY_FILE.read_text().strip()
    raise FileNotFoundError(f"Credentials API key not found at {CREDENTIALS_API_KEY_FILE}")


def fetch_notion_api_key() -> str:
    """Fetch Notion API key from Credentials Server."""
    api_key = get_credentials_api_key()
    
    response = httpx.get(
        f"{CREDENTIALS_SERVER_URL}/secrets/notion-api-key",
        headers={"X-API-Key": api_key},
        timeout=10
    )
    
    if response.status_code != 200:
        raise Exception(f"Failed to fetch Notion API key: {response.status_code} - {response.text}")
    
    data = response.json()
    return data.get("value", "")


def get_all_page_ids(notion_token: str) -> list:
    """Query all pages from the Triage database."""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    all_pages = []
    start_cursor = None
    
    while True:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        
        response = httpx.post(
            f"https://api.notion.com/v1/databases/{NOTION_TRIAGE_DB_ID}/query",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to query database: {response.status_code} - {response.text}")
        
        data = response.json()
        pages = data.get("results", [])
        all_pages.extend([page["id"] for page in pages])
        
        if not data.get("has_more", False):
            break
        
        start_cursor = data.get("next_cursor")
    
    return all_pages


def archive_page(notion_token: str, page_id: str) -> bool:
    """Archive a single Notion page."""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json={"archived": True},
            timeout=30
        )
        return response.status_code == 200
    except httpx.ReadTimeout:
        # Retry once on timeout
        try:
            response = httpx.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                json={"archived": True},
                timeout=60
            )
            return response.status_code == 200
        except:
            return False
    except:
        return False


def main():
    print("=" * 60)
    print("  BiOS Triage Database Purge")
    print("=" * 60)
    print()
    
    try:
        # Fetch Notion API key
        print("📋 Fetching Notion API key from Credentials Server...")
        notion_token = fetch_notion_api_key()
        print(f"✅ Notion API key loaded: {notion_token[:10]}...")
        print()
        
        # Get all page IDs
        print(f"📊 Querying BiOS Triage database ({NOTION_TRIAGE_DB_ID})...")
        page_ids = get_all_page_ids(notion_token)
        print(f"📄 Found {len(page_ids)} pages to archive")
        print()
        
        if not page_ids:
            print("✅ No pages to archive. Database is already clean.")
            return 0
        
        # Archive all pages
        print("🗑️  Archiving pages...")
        archived_count = 0
        failed_count = 0
        
        for i, page_id in enumerate(page_ids, 1):
            if archive_page(notion_token, page_id):
                archived_count += 1
                if i % 10 == 0:
                    print(f"   Progress: {i}/{len(page_ids)} pages archived...")
            else:
                failed_count += 1
                print(f"   ⚠️  Failed to archive page: {page_id}")
            
            # Small delay to avoid rate limiting
            if i % 5 == 0:
                time.sleep(0.5)
        
        print()
        print("=" * 60)
        print("  PURGE COMPLETE")
        print("=" * 60)
        print()
        print(f"📊 Summary:")
        print(f"   Total pages found: {len(page_ids)}")
        print(f"   ✅ Successfully archived: {archived_count}")
        print(f"   ❌ Failed: {failed_count}")
        print()
        
        return 0 if failed_count == 0 else 1
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
