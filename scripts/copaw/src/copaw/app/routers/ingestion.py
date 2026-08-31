# -*- coding: utf-8 -*-
"""Ingestion router for CoPaw.

Handles email metadata, Obsidian sync, and Notion webhooks.
Routes items to Notion for tracking and human-in-the-loop authorization.
"""
import logging
import json
import os
import httpx
from fastapi import APIRouter, Request, Response, HTTPException
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ingestion"])

# --- Notion Helpers ---
async def send_to_notion(payload: dict) -> dict:
    """Send tracking entry to Notion database."""
    try:
        notion_api_key = os.environ.get("NOTION_API_KEY")
        # Default to BiOS Authorisation DB ID
        notion_db_id = os.environ.get("NOTION_EMAIL_DB_ID", "3284d2d9fc7c81bd9a91e865511e642f")
        
        if not notion_api_key:
            return {"error": "NOTION_API_KEY not set"}
        
        notion_data = {
            "parent": {"database_id": notion_db_id},
            "properties": {
                "Name": {"title": [{"text": {"content": f"[{payload.get('type', 'email').upper()}] {payload.get('subject', 'No Subject')}"}}]},
                "Source": {"select": {"name": payload.get("type", "Email").capitalize()}},
                "Status": {"select": {"name": payload.get("status", "Triage")}},
                "Local File": {"rich_text": [{"text": {"content": payload.get("local_file", "")}}]},
                "Payload": {"rich_text": [{"text": {"content": json.dumps(payload, indent=2)[:2000]}}]}
            }
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {notion_api_key}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28"
                },
                json=notion_data,
                timeout=15.0
            )
            if resp.status_code != 200:
                logger.error(f"Notion API Error: {resp.status_code} {resp.text}")
                return {"error": resp.text}
            return resp.json()

    except Exception as e:
        logger.error(f"Failed to send to Notion: {e}")
        return {"error": str(e)}

@router.post("/email")
async def handle_email(request: Request):
    """Receive email metadata from email daemon and push to Notion."""
    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    logger.info(f"Ingesting email: {data.get('subject')}")
    
    notion_result = await send_to_notion(data)
    
    return {
        "status": "received",
        "notion_result": notion_result
    }

@router.post("/obsidian")
async def handle_obsidian(request: Request):
    """Handle Obsidian markdown sync notification."""
    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    logger.info(f"Ingesting Obsidian file: {data.get('filename')}")
    
    # Obsidian sync traditionally goes straight to memory 
    # but we can also track it in Notion if desired.
    # For now, we will follow the 'one memorization' rule 
    # and let the daily pipeline handle the actual sync.
    
    # If the user wants immediate memory sync for Obsidian, we could call memory router here.
    # But to prevent duplication, we'll just acknowledge or push to Notion.
    notion_result = await send_to_notion({
        "type": "obsidian",
        "subject": data.get("filename", "Untitled"),
        "status": "Synced",
        "local_file": data.get("path", ""),
        "body": data.get("content", "")[:1000]
    })
    
    return {"status": "received", "notion_result": notion_result}

@router.post("/webhook")
async def handle_webhook(request: Request):
    """Generic webhook endpoint (backward compatibility)."""
    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    source = data.get("source", "unknown")
    logger.info(f"Received generic webhook from {source}")
    
    # Forward everything to Notion by default for tracking
    notion_result = await send_to_notion(data)
    
    return {"status": "received", "notion_result": notion_result}

@router.post("/webhook/notion/sync")
async def trigger_notion_sync():
    """Trigger notion_vault_sweeper.py to instantly process checkboxed entries."""
    logger.info("Notion webhook trigger: Initiating Vault Sweep")
    import subprocess
    import sys
    import asyncio
    
    script_path = "/Users/danexall/biomimetics/scripts/email/notion_vault_sweeper.py"
    
    try:
        def run_sweeper():
            return subprocess.run([sys.executable, script_path], capture_output=True, text=True)
            
        result = await asyncio.to_thread(run_sweeper)
        logger.info(f"Vault sweeper stdout: {result.stdout}")
        if result.returncode == 0:
            return {"status": "success", "message": "Vault sweep completed successfully", "output": result.stdout}
        else:
            logger.error(f"Vault sweeper failed: {result.stderr}")
            return {"status": "error", "message": "Vault sweeper execution error", "error": result.stderr}
    except Exception as e:
        logger.error(f"Failed to run vault sweeper: {e}")
        raise HTTPException(status_code=500, detail=str(e))
