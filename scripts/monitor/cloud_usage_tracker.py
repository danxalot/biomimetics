#!/usr/bin/env python3
"""
Cloud Usage Tracker - BiOS Service

Queries Cloudflare Billing API and Azure Consumption API.
Logs daily spend and token usage to the Tool Guard Notion DB.

This provides visibility into cloud costs and helps optimize spending.
"""

import os
import sys
import json
import time
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

# Configuration
CLOUDFLARE_API_KEY = os.environ.get("CLOUDFLARE_API_KEY", "")
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "aa0a386d0cbd07685723b242e9157e67")
AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
NOTION_API_KEY = os.environ.get(
    "NOTION_API_KEY", 
    "[NOTION_TOKEN_REDACTED]"
)
TOOL_GUARD_DB_ID = os.environ.get(
    "TOOL_GUARD_DB_ID", 
    "3284d2d9fc7c8113bfecca75f4235ece"
)
GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
)
TRACKING_INTERVAL = int(os.environ.get("USAGE_TRACKING_INTERVAL", "3600"))  # 1 hour default
STATE_FILE = Path.home() / ".arca" / "cloud_usage_state.json"
LOG_FILE = Path.home() / ".arca" / "cloud_usage.log"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}


class CloudUsageTracker:
    """Track cloud spending and token usage across providers"""
    
    def __init__(self):
        self.last_cloudflare_query: Optional[str] = None
        self.last_azure_query: Optional[str] = None
        self.load_state()
        
    def load_state(self):
        """Load last query timestamps from state file"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.last_cloudflare_query = data.get("last_cloudflare_query")
                    self.last_azure_query = data.get("last_azure_query")
            except:
                pass
    
    def save_state(self):
        """Save query timestamps to state file"""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump({
                "last_cloudflare_query": self.last_cloudflare_query,
                "last_azure_query": self.last_azure_query,
                "last_updated": datetime.now().isoformat()
            }, f, indent=2)
    
    def log(self, message: str):
        """Log message to file and stderr"""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {message}\n"
        
        # Write to log file
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(log_entry)
        
        # Also print to stderr
        print(log_entry.strip(), file=sys.stderr)
    
    async def query_cloudflare_billing(self) -> Optional[Dict[str, Any]]:
        """Query Cloudflare Billing API for current month usage"""
        if not CLOUDFLARE_API_KEY:
            self.log("⚠️  Cloudflare API key not configured")
            return None
        
        try:
            # Get current month start and end
            now = datetime.now()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = now
            
            async with httpx.AsyncClient() as client:
                # Query Workers usage
                response = await client.get(
                    f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/billing/reports",
                    headers={
                        "Authorization": f"Bearer {CLOUDFLARE_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    params={
                        "since": month_start.isoformat() + "Z",
                        "until": month_end.isoformat() + "Z"
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.log(f"✅ Cloudflare billing query successful")
                    self.last_cloudflare_query = datetime.now().isoformat()
                    return self._parse_cloudflare_response(data)
                else:
                    self.log(f"⚠️  Cloudflare API error: {response.status_code}")
                    return None
                    
        except Exception as e:
            self.log(f"❌ Cloudflare query error: {e}")
            return None
    
    def _parse_cloudflare_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Cloudflare billing response"""
        result = data.get("result", {})
        
        # Extract usage data
        total_spend = 0.0
        workers_requests = 0
        workers_duration = 0.0
        
        # Parse billing data (structure depends on API response)
        if isinstance(result, dict):
            total_spend = float(result.get("total", 0))
            
            # Workers specific metrics
            workers = result.get("workers", {})
            workers_requests = int(workers.get("requests", 0))
            workers_duration = float(workers.get("cpu_time", 0))
        
        return {
            "provider": "Cloudflare",
            "total_spend_usd": total_spend,
            "workers_requests": workers_requests,
            "workers_duration_ms": workers_duration,
            "query_time": datetime.now().isoformat(),
            "period": "current_month"
        }
    
    async def query_azure_consumption(self) -> Optional[Dict[str, Any]]:
        """Query Azure Consumption API for current month usage"""
        if not AZURE_SUBSCRIPTION_ID:
            self.log("⚠️  Azure Subscription ID not configured")
            return None
        
        try:
            # Get Azure token using CLI
            azure_token = self._get_azure_token()
            if not azure_token:
                self.log("❌ Failed to get Azure authentication token")
                return None
            
            # Get current month start and end
            now = datetime.now()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = now
            
            async with httpx.AsyncClient() as client:
                # Query Azure Cost Management API
                response = await client.post(
                    f"https://management.azure.com/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.CostManagement/query?api-version=2023-03-01",
                    headers={
                        "Authorization": f"Bearer {azure_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "type": "ActualCost",
                        "timeframe": "Custom",
                        "timePeriod": {
                            "from": month_start.isoformat() + "Z",
                            "to": month_end.isoformat() + "Z"
                        },
                        "dataset": {
                            "granularity": "Daily",
                            "aggregation": {
                                "totalCost": {
                                    "name": "Cost",
                                    "function": "Sum"
                                }
                            }
                        }
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.log(f"✅ Azure consumption query successful")
                    self.last_azure_query = datetime.now().isoformat()
                    return self._parse_azure_response(data)
                else:
                    self.log(f"⚠️  Azure API error: {response.status_code}")
                    return None
                    
        except Exception as e:
            self.log(f"❌ Azure query error: {e}")
            return None
    
    def _get_azure_token(self) -> Optional[str]:
        """Get Azure authentication token using az CLI"""
        try:
            import subprocess
            result = subprocess.run(
                ["az", "account", "get-access-token", "--resource", "https://management.azure.com/", "--query", "accessToken", "-o", "tsv"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except:
            return None
    
    def _parse_azure_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Azure consumption response"""
        rows = data.get("properties", {}).get("rows", [])
        
        total_spend = 0.0
        daily_costs = []
        
        for row in rows:
            # Row format: [Date, Cost, Currency, ...]
            if len(row) >= 2:
                date_str = row[0]
                cost = float(row[1]) if row[1] else 0.0
                total_spend += cost
                daily_costs.append({"date": date_str, "cost": cost})
        
        return {
            "provider": "Azure",
            "total_spend_usd": total_spend,
            "daily_costs": daily_costs,
            "query_time": datetime.now().isoformat(),
            "period": "current_month"
        }
    
    async def log_to_notion(self, usage_data: Dict[str, Any]):
        """Log usage data to Tool Guard Notion database"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=NOTION_HEADERS,
                    json={
                        "parent": {"database_id": TOOL_GUARD_DB_ID},
                        "properties": {
                            "Name": {
                                "title": [{
                                    "text": {
                                        "content": f"Cloud Usage: {usage_data['provider']} - {datetime.now().strftime('%Y-%m-%d')}"
                                    }
                                }]
                            },
                            "Status": {"select": {"name": "Logged"}},
                            "Tool": {
                                "rich_text": [{
                                    "text": {
                                        "content": f"{usage_data['provider']} - ${usage_data['total_spend_usd']:.2f}"
                                    }
                                }]
                            }
                        },
                        "children": [
                            {
                                "paragraph": {
                                    "rich_text": [{
                                        "text": {
                                            "content": json.dumps(usage_data, indent=2)
                                        }
                                    }]
                                },
                                "type": "paragraph"
                            }
                        ]
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    self.log(f"✅ Logged to Notion: {usage_data['provider']}")
                else:
                    self.log(f"⚠️  Notion error: {response.status_code}")
                    
        except Exception as e:
            self.log(f"❌ Notion log error: {e}")
    
    async def log_to_gateway(self, usage_data: Dict[str, Any]):
        """Log usage data to GCP Gateway"""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    GCP_GATEWAY_URL,
                    json={
                        "operation": "memorize",
                        "content": json.dumps(usage_data),
                        "metadata": {
                            "source": "cloud_usage_tracker",
                            "type": "usage_report",
                            "provider": usage_data["provider"]
                        }
                    },
                    timeout=10.0
                )
                self.log(f"✅ Logged to GCP Gateway: {usage_data['provider']}")
        except Exception as e:
            self.log(f"⚠️  Gateway log error: {e}")
    
    async def track_once(self) -> Dict[str, Any]:
        """Single tracking iteration"""
        self.log("\n📊 Running cloud usage tracking...")
        
        results = {
            "tracking_time": datetime.now().isoformat(),
            "providers": {}
        }
        
        # Query Cloudflare
        cloudflare_data = await self.query_cloudflare_billing()
        if cloudflare_data:
            results["providers"]["cloudflare"] = cloudflare_data
            await self.log_to_notion(cloudflare_data)
            await self.log_to_gateway(cloudflare_data)
        
        # Query Azure
        azure_data = await self.query_azure_consumption()
        if azure_data:
            results["providers"]["azure"] = azure_data
            await self.log_to_notion(azure_data)
            await self.log_to_gateway(azure_data)
        
        # Calculate totals
        total_spend = sum(
            p.get("total_spend_usd", 0) 
            for p in results["providers"].values()
        )
        results["total_spend_usd"] = total_spend
        
        self.log(f"💰 Total cloud spend: ${total_spend:.2f}")
        
        # Save state
        self.save_state()
        
        return results
    
    async def run(self):
        """Main tracking loop"""
        self.log("=" * 60)
        self.log("☁️  Cloud Usage Tracker")
        self.log("=" * 60)
        self.log(f"   Cloudflare Account: {CLOUDFLARE_ACCOUNT_ID[:8]}...")
        self.log(f"   Azure Subscription: {AZURE_SUBSCRIPTION_ID[:8] if AZURE_SUBSCRIPTION_ID else 'Not configured'}...")
        self.log(f"   Tracking Interval: {TRACKING_INTERVAL}s")
        self.log(f"   Tool Guard DB: {TOOL_GUARD_DB_ID}")
        self.log("=" * 60)
        
        iteration = 0
        while True:
            iteration += 1
            await self.track_once()
            
            self.log(f"   Next tracking run in {TRACKING_INTERVAL}s...")
            await asyncio.sleep(TRACKING_INTERVAL)


async def main():
    """Run the cloud usage tracker"""
    tracker = CloudUsageTracker()
    await tracker.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Cloud Usage Tracker stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
