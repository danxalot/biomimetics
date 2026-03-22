#!/usr/bin/env python3
"""
CoPaw Approval Poller

Polls the CoPaw Approval Database in Notion every 15 seconds.
When an entry is marked "Approved" (via phone/Notion/Gemini Live),
it signals the local MCP server to release the held task.

This bridges the gap between cloud-based approval and local execution.
"""

import os
import sys
import json
import time
import httpx
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# Configuration
NOTION_API_KEY = os.environ.get(
    "NOTION_API_KEY", 
    "[NOTION_TOKEN_REDACTED]"
)
NOTION_APPROVAL_DB_ID = os.environ.get(
    "NOTION_APPROVAL_DB_ID", 
    "3274d2d9fc7c8161a00cd9995cff5520"
)
GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
)
POLL_INTERVAL = int(os.environ.get("APPROVAL_POLL_INTERVAL", "15"))
STATE_FILE = Path.home() / ".arca" / "approval_poller_state.json"
SIGNAL_FILE = Path.home() / ".arca" / "approved_actions.json"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}


class ApprovalPoller:
    """Poll Notion for approved actions and signal local MCP"""
    
    def __init__(self):
        self.processed_approvals: set = set()
        self.load_state()
        
    def load_state(self):
        """Load processed approval IDs from state file"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.processed_approvals = set(data.get("processed", []))
            except:
                self.processed_approvals = set()
    
    def save_state(self):
        """Save processed approval IDs to state file"""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump({
                "processed": list(self.processed_approvals),
                "last_updated": datetime.now().isoformat()
            }, f, indent=2)
    
    def load_signal_file(self) -> Dict[str, Any]:
        """Load approved actions signal file"""
        if SIGNAL_FILE.exists():
            try:
                with open(SIGNAL_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {"approved_actions": []}
        return {"approved_actions": []}
    
    def save_signal_file(self, data: Dict[str, Any]):
        """Save approved actions signal file"""
        SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SIGNAL_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    async def query_approvals(self) -> List[Dict[str, Any]]:
        """Query Notion for approval entries"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.notion.com/v1/databases/query",
                    headers=NOTION_HEADERS,
                    json={
                        "database_id": NOTION_APPROVAL_DB_ID,
                        "filter": {
                            "property": "Status",
                            "select": {
                                "equals": "Approved"
                            }
                        },
                        "page_size": 100
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
        except Exception as e:
            print(f"❌ Error querying Notion: {e}", file=sys.stderr)
            return []
    
    def extract_approval_data(self, page: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract approval data from Notion page"""
        try:
            properties = page.get("properties", {})
            
            # Extract fields
            approval_id = self._get_rich_text(properties.get("Approval ID", {}))
            tool_name = self._get_rich_text(properties.get("Tool", {}))
            status = self._get_select(properties.get("Status", {}))
            response = self._get_select(properties.get("Response", {}))
            requested_at = self._get_date(properties.get("Requested", {}))
            responded_at = self._get_date(properties.get("Responded", {}))
            
            # Get additional properties from page content
            page_id = page.get("id", "")
            
            return {
                "page_id": page_id,
                "approval_id": approval_id,
                "tool_name": tool_name,
                "status": status,
                "response": response,
                "requested_at": requested_at,
                "responded_at": responded_at,
                "notion_url": f"https://www.notion.so/{page_id.replace('-', '')}"
            }
        except Exception as e:
            print(f"❌ Error extracting approval data: {e}", file=sys.stderr)
            return None
    
    def _get_rich_text(self, prop: Dict[str, Any]) -> str:
        """Extract text from rich_text property"""
        if not prop:
            return ""
        rich_text = prop.get("rich_text", [])
        if rich_text:
            return rich_text[0].get("plain_text", "")
        return ""
    
    def _get_select(self, prop: Dict[str, Any]) -> str:
        """Extract value from select property"""
        if not prop:
            return ""
        select = prop.get("select", {})
        if select:
            return select.get("name", "")
        return ""
    
    def _get_date(self, prop: Dict[str, Any]) -> str:
        """Extract date from date property"""
        if not prop:
            return ""
        date = prop.get("date", {})
        if date:
            return date.get("start", "")
        return ""
    
    async def update_notion_status(self, page_id: str, status: str):
        """Update Notion page status after processing"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=NOTION_HEADERS,
                    json={
                        "properties": {
                            "Status": {"select": {"name": status}},
                            "Processed": {"date": {"start": datetime.now().isoformat()}}
                        }
                    },
                    timeout=10.0
                )
                if response.status_code == 200:
                    print(f"✅ Updated Notion status to: {status}", file=sys.stderr)
                else:
                    print(f"⚠️  Failed to update Notion: {response.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"❌ Error updating Notion: {e}", file=sys.stderr)
    
    async def signal_approval(self, approval_data: Dict[str, Any]):
        """Signal the local MCP server to execute the approved action"""
        # Load existing signals
        signals = self.load_signal_file()
        
        # Add new approved action
        approved_action = {
            "approval_id": approval_data["approval_id"],
            "tool_name": approval_data["tool_name"],
            "status": "approved",
            "approved_at": datetime.now().isoformat(),
            "notion_url": approval_data["notion_url"]
        }
        
        signals["approved_actions"].append(approved_action)
        
        # Keep only last 50 actions
        signals["approved_actions"] = signals["approved_actions"][-50:]
        
        # Save signal file
        self.save_signal_file(signals)
        
        # Log to GCP Gateway
        await self.log_to_gateway(approved_action)
        
        print(f"🚀 SIGNAL SENT: Approval {approval_data['approval_id']} - Execute {approval_data['tool_name']}", file=sys.stderr)
    
    async def log_to_gateway(self, approval_data: Dict[str, Any]):
        """Log approval execution to GCP Gateway"""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    GCP_GATEWAY_URL,
                    json={
                        "operation": "memorize",
                        "content": json.dumps(approval_data),
                        "metadata": {
                            "source": "approval_poller",
                            "type": "approval_executed"
                        }
                    },
                    timeout=10.0
                )
        except Exception as e:
            print(f"⚠️  Gateway log error: {e}", file=sys.stderr)
    
    async def poll_once(self) -> int:
        """Single poll iteration"""
        print(f"\n📡 Polling Notion for approvals at {datetime.now().isoformat()}...", file=sys.stderr)
        
        # Query approvals
        pages = await self.query_approvals()
        print(f"   Found {len(pages)} approved entries", file=sys.stderr)
        
        new_approvals = 0
        for page in pages:
            approval_data = self.extract_approval_data(page)
            if not approval_data:
                continue
            
            approval_id = approval_data.get("approval_id", "")
            
            # Skip if already processed
            if approval_id in self.processed_approvals:
                continue
            
            # Mark as processed
            self.processed_approvals.add(approval_id)
            self.save_state()
            new_approvals += 1
            
            # Signal execution
            await self.signal_approval(approval_data)
            
            # Update Notion status
            page_id = approval_data.get("page_id", "")
            if page_id:
                await self.update_notion_status(page_id, "Processed")
        
        return new_approvals
    
    async def run(self):
        """Main polling loop"""
        print("=" * 60, file=sys.stderr)
        print("🔔 CoPaw Approval Poller", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"   Approval DB: {NOTION_APPROVAL_DB_ID}", file=sys.stderr)
        print(f"   Poll Interval: {POLL_INTERVAL}s", file=sys.stderr)
        print(f"   State File: {STATE_FILE}", file=sys.stderr)
        print(f"   Signal File: {SIGNAL_FILE}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        
        iteration = 0
        while True:
            iteration += 1
            new_approvals = await self.poll_once()
            
            if new_approvals > 0:
                print(f"   ✅ Processed {new_approvals} new approval(s)", file=sys.stderr)
            else:
                print(f"   No new approvals", file=sys.stderr)
            
            print(f"   Sleeping for {POLL_INTERVAL}s...", file=sys.stderr)
            await asyncio.sleep(POLL_INTERVAL)


async def main():
    """Run the approval poller"""
    poller = ApprovalPoller()
    await poller.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Approval Poller stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
