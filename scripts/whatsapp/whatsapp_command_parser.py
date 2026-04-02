#!/usr/bin/env python3
"""
WhatsApp Command Parser for CoPaw Approvals
Parses APPROVE/DENY commands from WhatsApp messages

Usage:
    from whatsapp_command_parser import parse_approval_command, format_response_message
    
    # Parse incoming message
    command = parse_approval_command("APPROVE abc123")
    if command:
        print(f"Action: {command.action}, ID: {command.approval_id}")
"""

import re
from typing import Optional
from dataclasses import dataclass
from enum import Enum


class ApprovalAction(Enum):
    APPROVE = "approve"
    DENY = "deny"
    UNKNOWN = "unknown"


@dataclass
class ParsedCommand:
    action: ApprovalAction
    approval_id: str
    raw_message: str
    confidence: float


def parse_approval_command(message: str) -> Optional[ParsedCommand]:
    """
    Parse WhatsApp message for approval commands.
    
    Supported formats:
    - "APPROVE abc123"
    - "approve abc123"
    - "✅ APPROVE abc123"
    - "DENY xyz789"
    - "deny xyz789"
    - "❌ DENY xyz789"
    - "Yes, approve abc123"
    - "No, deny xyz789"
    - Just the approval ID (implicit approve)
    """
    if not message:
        return None
    
    message = message.strip()
    
    # Pattern 1: Direct APPROVE command
    approve_pattern = r"(?:✅\s*)?(APPROVE|APPROVED|YES)\s+([a-zA-Z0-9_-]+)"
    match = re.search(approve_pattern, message, re.IGNORECASE)
    if match:
        return ParsedCommand(
            action=ApprovalAction.APPROVE,
            approval_id=match.group(2),
            raw_message=message,
            confidence=0.95
        )
    
    # Pattern 2: Direct DENY command
    deny_pattern = r"(?:❌\s*)?(DENY|DENIED|NO|REJECT)\s+([a-zA-Z0-9_-]+)"
    match = re.search(deny_pattern, message, re.IGNORECASE)
    if match:
        return ParsedCommand(
            action=ApprovalAction.DENY,
            approval_id=match.group(2),
            raw_message=message,
            confidence=0.95
        )
    
    # Pattern 3: Approval ID only (implicit approve)
    # Only if message is a single token that looks like an ID
    id_pattern = r"^([a-zA-Z0-9_-]{6,})$"
    match = re.search(id_pattern, message)
    if match:
        return ParsedCommand(
            action=ApprovalAction.APPROVE,
            approval_id=match.group(1),
            raw_message=message,
            confidence=0.7  # Lower confidence for implicit approval
        )
    
    return None


def format_response_message(command: ParsedCommand, success: bool) -> str:
    """Format confirmation message to send back via WhatsApp."""
    if success:
        action_emoji = "✅" if command.action == ApprovalAction.APPROVE else "❌"
        action_text = "approved" if command.action == ApprovalAction.APPROVE else "denied"
        
        if command.action == ApprovalAction.APPROVE:
            followup = "Tool execution will proceed."
        else:
            followup = "Tool execution blocked."
            
        return (
            f"{action_emoji} *Approval {action_text.upper()}*\n\n"
            f"ID: `{command.approval_id}`\n"
            f"{followup}"
        )
    else:
        return (
            f"⚠️ *Could not process approval*\n\n"
            f"ID: `{command.approval_id}`\n"
            f"Please check the approval ID and try again."
        )


def format_approval_notification(
    approval_id: str,
    tool_name: str,
    arguments: dict,
    context: str = "",
    risk_level: str = "unknown"
) -> str:
    """
    Format an approval notification message for WhatsApp.
    
    Args:
        approval_id: Unique approval request ID
        tool_name: Name of the tool being requested
        arguments: Tool arguments as dict
        context: Additional context for the request
        risk_level: Risk level (low, medium, high)
    
    Returns:
        Formatted WhatsApp message string
    """
    import json
    
    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk_level.lower(), "⚪")
    
    return (
        f"🔒 *Tool Approval Required*\n\n"
        f"*Tool:* `{tool_name}`\n"
        f"*Arguments:* `{json.dumps(arguments)}`\n"
        f"*Context:* {context or 'N/A'}\n\n"
        f"{risk_emoji} *Risk Level:* {risk_level}\n\n"
        f"*Approval ID:* `{approval_id}`\n\n"
        f"*Reply with:*\n"
        f"✅ APPROVE {approval_id}\n"
        f"❌ DENY {approval_id}\n\n"
        f"⏱️  Timeout: 5 minutes"
    )


if __name__ == "__main__":
    # Test the parser
    test_messages = [
        "APPROVE abc123",
        "approve abc123",
        "✅ APPROVE abc123",
        "DENY xyz789",
        "❌ DENY xyz789",
        "abc123",  # Implicit approve
        "Yes approve def456",
        "No deny ghi789",
        "Invalid message",
    ]
    
    print("=== WhatsApp Command Parser Test ===\n")
    
    for msg in test_messages:
        result = parse_approval_command(msg)
        if result:
            print(f"✓ '{msg}'")
            print(f"  → Action: {result.action.value}, ID: {result.approval_id}, Confidence: {result.confidence}\n")
        else:
            print(f"✗ '{msg}' → No command parsed\n")
    
    # Test notification formatting
    print("\n=== Sample Approval Notification ===\n")
    notification = format_approval_notification(
        approval_id="test123",
        tool_name="execute_shell_command",
        arguments={"command": "git push origin main"},
        context="Deploying to production",
        risk_level="high"
    )
    print(notification)
