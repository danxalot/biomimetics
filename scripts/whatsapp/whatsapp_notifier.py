#!/usr/bin/env python3
"""
WhatsApp Notifier Utility for CoPaw
Sends approval notifications via WhatsApp Cloud API or Cloudflare Worker

Usage:
    # Send test message
    python3 whatsapp_notifier.py test "+1234567890"
    
    # Send approval notification
    python3 whatsapp_notifier.py notify --approval-id abc123 --tool test_tool --context "Testing"
    
    # Parse command
    python3 whatsapp_notifier.py parse "APPROVE abc123"
"""

import os
import sys
import json
import httpx
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from whatsapp_command_parser import (
    parse_approval_command,
    format_response_message,
    format_approval_notification,
    ApprovalAction
)

# Configuration
WHATSAPP_API_URL = "https://graph.facebook.com/v17.0"
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
USER_WHATSAPP_NUMBER = os.getenv("USER_WHATSAPP_NUMBER", "")
CLOUDFLARE_WORKER_URL = os.getenv("CLOUDFLARE_WORKER_URL", "")


def send_test_message(to_number: str, custom_message: str = None) -> dict:
    """
    Send a test "Hello World" message via WhatsApp.
    
    Args:
        to_number: Recipient phone number (e.g., "+1234567890")
        custom_message: Optional custom message (default: Hello World test)
    
    Returns:
        dict with success status and message_id
    """
    message = custom_message or (
        "🔔 *CoPaw WhatsApp Integration Test*\n\n"
        "Hello World! This is a test message from the CoPaw notification system.\n\n"
        "If you received this, the integration is working correctly! ✅"
    )
    
    # Use Cloudflare Worker if configured
    if CLOUDFLARE_WORKER_URL:
        return send_via_cloudflare_worker("test", to_number, {"message": message})
    
    # Otherwise use direct WhatsApp API
    return send_via_whatsapp_api(to_number, message)


def send_approval_notification(
    approval_id: str,
    tool_name: str,
    arguments: dict,
    context: str = "",
    risk_level: str = "high",
    to_number: str = None
) -> dict:
    """
    Send an approval notification via WhatsApp.
    
    Args:
        approval_id: Unique approval request ID
        tool_name: Name of the tool being requested
        arguments: Tool arguments dict
        context: Additional context
        risk_level: Risk level (low, medium, high)
        to_number: Recipient number (default: USER_WHATSAPP_NUMBER)
    
    Returns:
        dict with success status and message_id
    """
    to_number = to_number or USER_WHATSAPP_NUMBER
    message = format_approval_notification(
        approval_id=approval_id,
        tool_name=tool_name,
        arguments=arguments,
        context=context,
        risk_level=risk_level
    )
    
    # Use Cloudflare Worker if configured
    if CLOUDFLARE_WORKER_URL:
        return send_via_cloudflare_worker("notify", to_number, {
            "approval_id": approval_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "context": context,
            "risk_level": risk_level
        })
    
    # Otherwise use direct WhatsApp API
    return send_via_whatsapp_api(to_number, message)


def send_via_whatsapp_api(to_number: str, message: str) -> dict:
    """Send message directly via WhatsApp Cloud API."""
    if not WHATSAPP_PHONE_ID or not WHATSAPP_ACCESS_TOKEN:
        return {
            "success": False,
            "error": "WhatsApp API credentials not configured. Set WHATSAPP_PHONE_ID and WHATSAPP_ACCESS_TOKEN."
        }
    
    try:
        response = httpx.post(
            f"{WHATSAPP_API_URL}/{WHATSAPP_PHONE_ID}/messages",
            headers={
                "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "text",
                "text": {"body": message}
            },
            timeout=30.0
        )
        response.raise_for_status()
        result = response.json()
        
        if "error" in result:
            return {"success": False, "error": result["error"].get("message", "Unknown error")}
        
        return {
            "success": True,
            "message_id": result.get("messages", [{}])[0].get("id"),
            "to": to_number
        }
        
    except httpx.HTTPError as e:
        return {"success": False, "error": f"HTTP error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Error: {str(e)}"}


def send_via_cloudflare_worker(endpoint: str, to_number: str, payload: dict) -> dict:
    """Send message via Cloudflare Worker."""
    try:
        url = f"{CLOUDFLARE_WORKER_URL}/{endpoint}"
        payload["to"] = to_number
        
        response = httpx.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        result = response.json()
        
        return {
            "success": result.get("success", False),
            "message_id": result.get("message_id"),
            "worker_response": result
        }
        
    except httpx.HTTPError as e:
        return {"success": False, "error": f"HTTP error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Error: {str(e)}"}


def parse_command(message: str) -> dict:
    """Parse a WhatsApp command message."""
    result = parse_approval_command(message)
    
    if result:
        return {
            "success": True,
            "action": result.action.value,
            "approval_id": result.approval_id,
            "confidence": result.confidence,
            "response_message": format_response_message(result, True)
        }
    else:
        return {
            "success": False,
            "error": "Could not parse command",
            "supported_formats": [
                "APPROVE <approval_id>",
                "DENY <approval_id>",
                "✅ APPROVE <approval_id>",
                "❌ DENY <approval_id>",
                "<approval_id> (implicit approve)"
            ]
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="WhatsApp Notifier for CoPaw")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Send test message")
    test_parser.add_argument("phone", help="Phone number (e.g., +1234567890)")
    test_parser.add_argument("--message", "-m", help="Custom test message")
    
    # Notify command
    notify_parser = subparsers.add_parser("notify", help="Send approval notification")
    notify_parser.add_argument("--approval-id", required=True, help="Approval ID")
    notify_parser.add_argument("--tool", required=True, help="Tool name")
    notify_parser.add_argument("--context", "-c", default="", help="Context")
    notify_parser.add_argument("--risk", "-r", default="high", choices=["low", "medium", "high"])
    notify_parser.add_argument("--phone", help="Phone number (default: env USER_WHATSAPP_NUMBER)")
    notify_parser.add_argument("--args", "-a", default="{}", help="Tool arguments as JSON")
    
    # Parse command
    parse_parser = subparsers.add_parser("parse", help="Parse command message")
    parse_parser.add_argument("message", help="Message to parse")
    
    # Config check
    subparsers.add_parser("config", help="Check configuration")
    
    args = parser.parse_args()
    
    if args.command == "test":
        print(f"📱 Sending test message to {args.phone}...")
        result = send_test_message(args.phone, args.message)
        print(json.dumps(result, indent=2))
        
    elif args.command == "notify":
        try:
            tool_args = json.loads(args.args)
        except json.JSONDecodeError:
            print("Error: Invalid JSON for --args")
            sys.exit(1)
            
        print(f"🔒 Sending approval notification for {args.tool}...")
        result = send_approval_notification(
            approval_id=args.approval_id,
            tool_name=args.tool,
            arguments=tool_args,
            context=args.context,
            risk_level=args.risk,
            to_number=args.phone
        )
        print(json.dumps(result, indent=2))
        
    elif args.command == "parse":
        print(f"📝 Parsing message: {args.message}")
        result = parse_command(args.message)
        print(json.dumps(result, indent=2))
        
    elif args.command == "config":
        print("=== WhatsApp Notifier Configuration ===\n")
        print(f"WHATSAPP_PHONE_ID: {'✓ Set' if WHATSAPP_PHONE_ID else '✗ Not set'}")
        print(f"WHATSAPP_ACCESS_TOKEN: {'✓ Set' if WHATSAPP_ACCESS_TOKEN else '✗ Not set'}")
        print(f"USER_WHATSAPP_NUMBER: {'✓ Set' if USER_WHATSAPP_NUMBER else '✗ Not set'}")
        print(f"CLOUDFLARE_WORKER_URL: {'✓ Set' if CLOUDFLARE_WORKER_URL else '✗ Not set'}")
        
        if not WHATSAPP_PHONE_ID and not CLOUDFLARE_WORKER_URL:
            print("\n⚠️  Warning: No messaging backend configured!")
            print("Set WHATSAPP_PHONE_ID + WHATSAPP_ACCESS_TOKEN for direct API,")
            print("or CLOUDFLARE_WORKER_URL for Cloudflare Worker proxy.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
