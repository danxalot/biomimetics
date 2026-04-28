#!/usr/bin/env python3
"""
GitHub Project Sync Handler
===========================

Syncs tasks from the Notion Swarm Ledger to GitHub Issues.
Usage: python github_sync.py --task_id SWARM-1
"""

import sys
import os
import argparse
import json
import logging
from typing import Optional, Dict

import httpx

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("github_sync")

# Configuration placeholders
TARGET_REPO = os.getenv("GITHUB_SYNC_REPO", "danxalot/biomimetics")  # Default to user repository
CREDENTIALS_SERVER_URL = "http://localhost:8089"
SWARM_LEDGER_DB_ID = "33c4d2d9-fc7c-81d9-bbce-e8871dc740c0"

# Read the master key from the local vault
CREDENTIALS_PATH = "/Users/danexall/biomimetics/secrets/credentials_api_key"
try:
    with open(CREDENTIALS_PATH, "r") as f:
        CREDENTIALS_API_KEY = f.read().strip()
except FileNotFoundError:
    logger.error(f"Master credentials file not found at {CREDENTIALS_PATH}")
    sys.exit(1)

def fetch_secret(secret_name: str) -> Optional[str]:
    """Fetch a secret from the local Credentials Server."""
    try:
        response = httpx.get(
            f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}",
            headers={"X-API-Key": CREDENTIALS_API_KEY},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("value")
        return None
    except Exception as e:
        logger.error(f"Error fetching secret {secret_name}: {e}")
        return None

def get_notion_task(notion_token: str, task_id: str) -> Optional[Dict]:
    """Query Notion Swarm Ledger for a specific task ID."""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # Extract the integer for the unique_id filter
    try:
        task_number = int(task_id.split("-")[-1])
    except ValueError:
        logger.error(f"Invalid Task ID format: {task_id}. Expected format: SWARM-X")
        return None

    payload = {
        "filter": {
            "property": "Task ID",
            "unique_id": {
                "equals": task_number
            }
        }
    }
    
    try:
        response = httpx.post(
            f"https://api.notion.com/v1/databases/{SWARM_LEDGER_DB_ID}/query",
            headers=headers,
            json=payload,
            timeout=30
        )
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                return results[0]
            logger.warning(f"No task found with ID: {task_id}")
            return None
        logger.error(f"Notion API error: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        logger.error(f"Error querying Notion: {e}")
        return None

def create_github_issue(github_token: str, title: str, notion_url: str) -> Optional[str]:
    """Create a new issue in the target repository."""
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    body = f"Synced from Notion Swarm Ledger.\n\n[View in Notion]({notion_url})"
    
    payload = {
        "title": title,
        "body": body
    }
    
    try:
        response = httpx.post(
            f"https://api.github.com/repos/{TARGET_REPO}/issues",
            headers=headers,
            json=payload,
            timeout=30
        )
        if response.status_code == 201:
            return response.json().get("html_url")
        logger.error(f"GitHub API error: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        logger.error(f"Error creating GitHub issue: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Sync Notion task to GitHub Issue")
    parser.add_argument("--task_id", required=True, help="Notion Task ID (e.g., SWARM-1)")
    args = parser.parse_args()
    
    logger.info(f"Starting sync for task: {args.task_id}")
    
    # 1. Fetch credentials
    notion_token = fetch_secret("notion-api-key")
    github_token_raw = fetch_secret("github-token")
    
    if not notion_token or not github_token_raw:
        logger.error("Failed to fetch necessary tokens from Credentials Server.")
        sys.exit(1)

    # Parse token if stored in KEY=VALUE format
    github_token = github_token_raw.partition("=")[-1].strip() if "=" in github_token_raw else github_token_raw
        
    # 2. Query Notion for task details
    task_page = get_notion_task(notion_token, args.task_id)
    if not task_page:
        logger.error(f"Task {args.task_id} not found in Notion Swarm Ledger.")
        sys.exit(1)
        
    properties = task_page.get("properties", {})
    # Extract the actual task name from the Name property, not the ID
    title_list = properties.get("Name", {}).get("title", [])
    task_title = title_list[0].get("text", {}).get("content", "Untitled Task") if title_list else "Untitled Task"
    notion_url = task_page.get("url", "")
    
    # 3. Create GitHub Issue
    issue_url = create_github_issue(github_token, task_title, notion_url)
    
    if issue_url:
        print(issue_url)
        logger.info(f"Successfully synced to: {issue_url}")
    else:
        logger.error("Failed to create GitHub issue.")
        sys.exit(1)

if __name__ == "__main__":
    main()
