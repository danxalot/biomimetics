#!/usr/bin/env python3
"""
Notion Duplicate Database Cleanup Script

This script:
1. Lists all databases in the Notion workspace
2. Identifies duplicates of "Life OS Triage" and "Tool Guard"
3. Archives duplicates that are NOT in db_state.json

Usage:
    python3 scripts/maintenance/cleanup_notion_duplicates.py

Dry-run mode (default): Shows what would be deleted without actually deleting
    python3 scripts/maintenance/cleanup_notion_duplicates.py --execute
"""

import os
import sys
import json
import argparse
import time
from pathlib import Path
from typing import List, Dict, Optional

# Configuration
NOTION_TOKEN = "[NOTION_TOKEN_REDACTED]"
DB_STATE_FILE = Path.home() / ".arca" / "omni_sync" / "db_state.json"
NOTION_API_URL = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Target database names to deduplicate
TARGET_DB_NAMES = ["Life OS Triage", "Tool Guard"]


def load_db_state() -> Dict[str, str]:
    """Load existing database IDs from state file."""
    if not DB_STATE_FILE.exists():
        return {}
    try:
        with open(DB_STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def search_databases() -> List[Dict]:
    """Search for all databases in the workspace."""
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed. Run: pip3 install requests")
        sys.exit(1)

    url = f"{NOTION_API_URL}/search"
    payload = {
        "query": "",
        "filter": {"property": "object", "value": "database"},
        "page_size": 100
    }

    try:
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result.get('results', [])
    except requests.RequestException as e:
        print(f"ERROR: Failed to search databases: {e}")
        return []


def find_duplicates(databases: List[Dict], protected_ids: Dict[str, str]) -> List[Dict]:
    """Find duplicate databases that should be archived."""
    duplicates = []

    for db in databases:
        db_name = db.get('title', [{}])[0].get('plain_text', '')
        db_id = db.get('id', '')

        # Skip if this is a protected database
        if db_id in protected_ids.values():
            continue

        # Check if this is a target database name
        if db_name in TARGET_DB_NAMES:
            duplicates.append({
                'id': db_id,
                'name': db_name,
                'url': db.get('url', ''),
                'created_time': db.get('created_time', '')
            })

    return duplicates


def archive_database(db_id: str, dry_run: bool = True) -> bool:
    """Archive (delete) a Notion database."""
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed")
        return False

    url = f"{NOTION_API_URL}/blocks/{db_id}"
    payload = {"archived": True}

    if dry_run:
        print(f"  [DRY RUN] Would archive: {db_id}")
        return True

    try:
        response = requests.patch(url, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        print(f"  ✓ Archived: {db_id}")
        return True
    except requests.RequestException as e:
        print(f"  ✗ Failed to archive {db_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Clean up duplicate Notion databases')
    parser.add_argument('--execute', action='store_true', 
                        help='Actually archive duplicates (default: dry-run)')
    args = parser.parse_args()

    print("=" * 60)
    print("Notion Duplicate Database Cleanup")
    print("=" * 60)
    print()

    # Load protected database IDs
    protected = load_db_state()
    print(f"Protected databases (from db_state.json):")
    if protected:
        for name, db_id in protected.items():
            print(f"  • {name}: {db_id}")
    else:
        print("  (none - db_state.json not found or empty)")
    print()

    # Search for all databases
    print("Searching for databases in workspace...")
    databases = search_databases()
    print(f"Found {len(databases)} databases")
    print()

    # Find duplicates
    duplicates = find_duplicates(databases, protected)
    print(f"Found {len(duplicates)} duplicate(s) to archive:")
    for dup in duplicates:
        print(f"  • {dup['name']} ({dup['id']})")
        print(f"    URL: {dup['url']}")
        print(f"    Created: {dup['created_time']}")
    print()

    if not duplicates:
        print("✓ No duplicates found. Workspace is clean!")
        return 0

    # Archive duplicates
    if args.execute:
        print("Archiving duplicates...")
        archived_count = 0
        failed_count = 0
        for i, dup in enumerate(duplicates):
            if archive_database(dup['id'], dry_run=False):
                archived_count += 1
            else:
                failed_count += 1
            # Rate limiting: Notion allows ~3-5 requests/sec
            # Wait 400ms between requests to stay under limit
            if i < len(duplicates) - 1:
                time.sleep(0.4)
                # Print progress every 10 items
                if (i + 1) % 10 == 0:
                    print(f"  Progress: {i + 1}/{len(duplicates)}...")
        print()
        print(f"Archived {archived_count}/{len(duplicates)} databases")
        if failed_count > 0:
            print(f"Failed: {failed_count}")
    else:
        print("DRY RUN MODE - No changes made")
        print()
        print("To actually archive these databases, run:")
        print("  python3 scripts/maintenance/cleanup_notion_duplicates.py --execute")

    return 0


if __name__ == '__main__':
    sys.exit(main())
