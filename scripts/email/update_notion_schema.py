import httpx
import json
import os
from pathlib import Path

# Configuration
CREDENTIALS_SERVER_URL = "http://localhost:8089"
CREDENTIALS_API_KEY_FILE = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
NOTION_TRIAGE_DB_ID = "3284d2d9-fc7c-81bd-9a91-e865511e642f"

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
        print(f"Error fetching Notion key: {e}")
    return ""

def main():
    notion_token = fetch_notion_api_key()
    if not notion_token:
        print("❌ Could not fetch Notion API key.")
        return

    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    print(f"🛠️  Adding 'Local File' property to database: {NOTION_TRIAGE_DB_ID}...")
    payload = {
        "properties": {
            "Local File": {"rich_text": {}}
        }
    }
    
    try:
        response = httpx.patch(
            f"https://api.notion.com/v1/databases/{NOTION_TRIAGE_DB_ID}",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        print("✅ 'Local File' property added successfully.")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
