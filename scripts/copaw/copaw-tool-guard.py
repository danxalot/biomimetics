#!/usr/bin/env python3
"""
Copaw Tool Guard - Approval Workflow Handler
Intercepts high-risk tool executions and routes for approval via Notion/Telegram
"""

import os
import json
import re
import httpx
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# Configuration
GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
)
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_APPROVAL_DB_ID = os.environ.get("NOTION_APPROVAL_DB_ID", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# High-risk patterns that require approval
HIGH_RISK_PATTERNS = [
    r"git\s+push",
    r"git\s+commit",
    r"rm\s+-rf",
    r"sudo",
    r"chmod\s+777",
    r"curl.*\|\s*(ba)?sh",
    r"wget.*\|\s*(ba)?sh",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM",
    r"TRUNCATE",
    r"serena\.execute_shell_command",
    r"serena\.git_push",
    r"serena\.git_commit",
]

# Auto-approve patterns (safe operations)
AUTO_APPROVE_PATTERNS = [
    r"git\s+status",
    r"git\s+log",
    r"git\s+diff",
    r"ls\s+-la",
    r"cat\s+",
    r"head\s+",
    r"tail\s+",
    r"grep\s+",
    r"serena\.search_symbols",
    r"serena\.get_symbol_implementation",
    r"serena\.get_file_content",
]


class ToolGuard:
    """Intercept and approve/deny tool executions"""
    
    def __init__(self):
        self.high_risk_patterns = [re.compile(p, re.IGNORECASE) for p in HIGH_RISK_PATTERNS]
        self.auto_approve_patterns = [re.compile(p, re.IGNORECASE) for p in AUTO_APPROVE_PATTERNS]
        self.pending_approvals: Dict[str, dict] = {}
    
    def check_risk_level(self, tool_name: str, arguments: dict) -> str:
        """Determine risk level of tool execution"""
        # Combine tool name and arguments for pattern matching
        check_text = f"{tool_name} {json.dumps(arguments)}"
        
        # Check auto-approve first
        for pattern in self.auto_approve_patterns:
            if pattern.search(check_text):
                return "safe"
        
        # Check high-risk patterns
        for pattern in self.high_risk_patterns:
            if pattern.search(check_text):
                return "high_risk"
        
        return "medium"
    
    async def request_approval(
        self,
        tool_name: str,
        arguments: dict,
        context: str = ""
    ) -> str:
        """Request approval for high-risk operation
        
        Returns: 'approved', 'denied', or 'pending'
        """
        approval_id = f"{tool_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        approval_request = {
            "approval_id": approval_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "context": context,
            "requested_at": datetime.now().isoformat(),
            "status": "pending"
        }
        
        self.pending_approvals[approval_id] = approval_request
        
        # Send to Notion
        if NOTION_API_KEY and NOTION_APPROVAL_DB_ID:
            await self.send_to_notion(approval_request)
        
        # Send to Telegram
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            await self.send_to_telegram(approval_request)
        
        # Also store in memory
        await self.store_in_memory(approval_request)
        
        return "pending"
    
    async def send_to_notion(self, approval_request: dict):
        """Create Notion page for approval"""
        try:
            response = httpx.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {NOTION_API_KEY}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28"
                },
                json={
                    "parent": {"database_id": NOTION_APPROVAL_DB_ID},
                    "properties": {
                        "Name": {"title": [{"text": {"content": f"Approval: {approval_request['tool_name']}"}}]},
                        "Status": {"select": {"name": "Pending"}},
                        "Tool": {"rich_text": [{"text": {"content": approval_request['tool_name']}}]},
                        "Requested": {"date": {"start": approval_request['requested_at']}},
                        "Approval ID": {"rich_text": [{"text": {"content": approval_request['approval_id']}}]}
                    }
                },
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    async def send_to_telegram(self, approval_request: dict):
        """Send approval request to Telegram"""
        try:
            message = (
                f"🔒 *Tool Approval Required*\n\n"
                f"*Tool:* `{approval_request['tool_name']}`\n"
                f"*Arguments:* `{json.dumps(approval_request['arguments'])}`\n"
                f"*Context:* {approval_request['context']}\n\n"
                f"*Approval ID:* `{approval_request['approval_id']}`\n\n"
                f"Reply with /approve {approval_request['approval_id']} or /deny {approval_request['approval_id']}"
            )
            
            response = httpx.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown"
                },
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    async def store_in_memory(self, approval_request: dict):
        """Store approval request in MemU for context"""
        try:
            content = (
                f"Tool Approval Request\n"
                f"ID: {approval_request['approval_id']}\n"
                f"Tool: {approval_request['tool_name']}\n"
                f"Arguments: {json.dumps(approval_request['arguments'])}\n"
                f"Context: {approval_request['context']}\n"
                f"Status: pending"
            )
            
            response = httpx.post(
                GCP_GATEWAY_URL,
                json={
                    "operation": "memorize",
                    "content": content,
                    "metadata": {
                        "source": "tool_guard",
                        "type": "approval_request",
                        "approval_id": approval_request['approval_id']
                    }
                },
                timeout=30.0
            )
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def check_approval_status(self, approval_id: str) -> str:
        """Check if approval has been granted"""
        if approval_id not in self.pending_approvals:
            return "unknown"
        
        return self.pending_approvals[approval_id].get("status", "pending")
    
    def grant_approval(self, approval_id: str) -> bool:
        """Grant approval for pending request"""
        if approval_id not in self.pending_approvals:
            return False
        
        self.pending_approvals[approval_id]["status"] = "approved"
        self.pending_approvals[approval_id]["approved_at"] = datetime.now().isoformat()
        return True
    
    def deny_approval(self, approval_id: str) -> bool:
        """Deny approval for pending request"""
        if approval_id not in self.pending_approvals:
            return False
        
        self.pending_approvals[approval_id]["status"] = "denied"
        self.pending_approvals[approval_id]["denied_at"] = datetime.now().isoformat()
        return True


# Global tool guard instance
tool_guard = ToolGuard()


async def intercept_tool_call(
    tool_name: str,
    arguments: dict,
    context: str = ""
) -> dict:
    """
    Intercept tool call and check if approval is needed.
    
    Returns:
        {"status": "approved"} - Tool can execute
        {"status": "denied"} - Tool execution blocked
        {"status": "pending", "approval_id": "..."} - Waiting for approval
    """
    risk_level = tool_guard.check_risk_level(tool_name, arguments)
    
    if risk_level == "safe":
        return {"status": "approved", "risk_level": "safe"}
    
    if risk_level == "high_risk":
        approval_status = await tool_guard.request_approval(
            tool_name=tool_name,
            arguments=arguments,
            context=context
        )
        
        if approval_status == "pending":
            return {
                "status": "pending",
                "risk_level": "high_risk",
                "message": f"Tool '{tool_name}' requires approval. Check Notion or Telegram."
            }
    
    return {"status": "approved", "risk_level": risk_level}


if __name__ == "__main__":
    import asyncio
    
    # Test the tool guard
    async def test():
        print("Testing Tool Guard...")
        
        # Test safe operation
        result = await intercept_tool_call("git_status", {})
        print(f"git_status: {result}")
        
        # Test high-risk operation
        result = await intercept_tool_call(
            "serena.execute_shell_command",
            {"command": "git push origin main"},
            context="Pushing feature branch"
        )
        print(f"git push: {result}")
    
    asyncio.run(test())
