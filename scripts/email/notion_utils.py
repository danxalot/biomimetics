#!/usr/bin/env python3
"""
BiOS Notion Utility Module
Contains shared functions for Notion operations.
"""

import httpx
import logging
from pathlib import Path

logger = logging.getLogger("NotionUtils")

NOTION_TRIAGE_DB_ID = "3284d2d9-fc7c-81bd-9a91-e865511e642f"

def trash_notion_record(notion_token, page_id, dry_run=False):
    """Move a Notion page to trash"""
    if dry_run:
        logger.info(f"[DRY RUN] Would trash Notion page: {page_id}")
        return True
        
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    try:
        # Standard Notion API method for trashing is 'archived': True
        response = httpx.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json={"archived": True},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Successfully trashed Notion page: {page_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to trash Notion page {page_id}: {e}")
        return False

def clear_handling_and_trash(notion_token, page_id, dry_run=False):
    """
    Implements the BiOS Handshake: 
    1. Clear the 'Email Handling' property (Set to null/None)
    2. Move to Trash (archived: True)
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would clear 'Email Handling' and trash Notion page: {page_id}")
        return True

    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    try:
        # Step 1: Clear Email Handling
        clear_payload = {
            "properties": {
                "Email Handling": None
            }
        }
        resp = httpx.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json=clear_payload,
            timeout=10
        )
        resp.raise_for_status()
        logger.info(f"Cleared 'Email Handling' for page: {page_id}")

        # Step 2: Trash
        return trash_notion_record(notion_token, page_id, dry_run=False)

    except Exception as e:
        logger.error(f"Handshake failed for page {page_id}: {e}")
        return False
