import requests
import json
import os
import sys

# Configuration
NOTION_TOKEN = ""
DATABASE_ID = "3284d2d9fc7c811188deeeaba9c5f845"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def claim_task():
    """Poll for tasks tagged for Antigravity and claim the first one."""
    query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    
    # Filter: Status == Ready for Dev AND Execution_Tier == Antigravity
    payload = {
        "filter": {
            "and": [
                {
                    "property": "Status",
                    "status": { "equals": "Ready for Dev" }
                },
                {
                    "property": "Execution_Tier",
                    "select": { "equals": "Antigravity" }
                }
            ]
        },
        "page_size": 1
    }
    
    try:
        resp = requests.post(query_url, headers=NOTION_HEADERS, json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        
        if not results:
            print("No new [Antigravity] tasks found.")
            return None
        
        task = results[0]
        task_id = task["id"]
        title = task["properties"]["Task Name"]["title"][0]["plain_text"]
        
        # Claim Task: Update Status to In Progress
        patch_url = f"https://api.notion.com/v1/pages/{task_id}"
        patch_payload = {
            "properties": {
                "Status": { "status": { "name": "In Progress" } },
                "State": { "select": { "name": "In Progress (Antigravity)" } }
            }
        }
        requests.patch(patch_url, headers=NOTION_HEADERS, json=patch_payload).raise_for_status()
        
        return {
            "id": task_id,
            "title": title,
            "url": task["url"]
        }
        
    except Exception as e:
        print(f"Error claiming task: {e}")
        return None

if __name__ == "__main__":
    mission = claim_task()
    if mission:
        print("\n" + "="*60)
        print("🚩 NEW MISSION ACQUIRED: " + mission["title"])
        print("ID: " + mission["id"])
        print("URL: " + mission["url"])
        print("="*60 + "\n")
        print("Antigravity, please proceed with the execution of this task brief.")
