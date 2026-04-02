# CoPaw ↔ WhatsApp Integration Design Document

## Executive Summary

This document outlines the technical design for integrating WhatsApp as the Human-in-the-Loop (HITL) interface for CoPaw tool approvals and status alerts.

---

## 1. API Selection Analysis

### Option Comparison

| Criteria | WhatsApp Business Cloud API | n8n Automation | Albato Bridge |
|----------|----------------------------|----------------|---------------|
| **Cost** | Free tier: 1,000 conversations/month | Self-hosted: Free | $9-29/month |
| **Setup Complexity** | Medium (Meta developer account) | Low (UI-based) | Lowest (no-code) |
| **Latency** | Direct API (~100-500ms) | Additional hop (~200-800ms) | Additional hop (~300-1000ms) |
| **Control** | Full API access | Limited by n8n nodes | Limited by Albato actions |
| **Cloudflare Compatibility** | ✅ Direct HTTP | ⚠️ Webhook only | ⚠️ Webhook only |
| **Recommended** | ✅ **YES** | ❌ No | ❌ No |

### Recommendation: **WhatsApp Business Cloud API (Direct)**

**Rationale:**
1. **Cost-effective**: Free tier covers 1,000 conversations/month (sufficient for approval workflow)
2. **Direct integration**: No middleman, lower latency
3. **Full control**: Access to all WhatsApp features (templates, interactive messages)
4. **Cloudflare-native**: Worker can directly proxy to Meta API

---

## 2. Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   CoPaw Tool    │────▶│  Cloudflare      │────▶│  WhatsApp       │
│   Guard         │     │  Worker          │     │  Cloud API      │
│   (Notion)      │     │  (Webhook)       │     │  (Meta)         │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │                        │
                               │                        │
                               ▼                        ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │  WhatsApp        │     │  User Mobile    │
                        │  Bridge (Local)  │     │  Device         │
                        │  Port 8001       │     │                 │
                        └──────────────────┘     └─────────────────┘
```

### Components

1. **CoPaw Tool Guard** (`copaw-tool-guard.py`)
   - Intercepts high-risk tool calls
   - Creates approval entry in Notion
   - Triggers WhatsApp notification via Cloudflare Worker

2. **Cloudflare Worker** (`whatsapp-notifier`)
   - Receives approval requests from CoPaw
   - Formats and sends WhatsApp messages via Meta API
   - Parses user responses (APPROVE/DENY)
   - Updates Notion approval status

3. **WhatsApp Bridge** (`whatsapp_bridge.py` - Local)
   - Receives inbound WhatsApp webhooks from Meta
   - Forwards messages to CoPaw webhook receiver
   - Handles command parsing for approval responses

---

## 3. Cloudflare Worker Implementation

### Worker Script: `whatsapp-notifier.js`

```javascript
// WhatsApp Notification Worker for CoPaw
// Routes approval requests to WhatsApp Cloud API

const WHATSAPP_API_URL = "https://graph.facebook.com/v17.0";
const WHATSAPP_PHONE_ID = WHATSAPP_PHONE_ID_ENV;
const WHATSAPP_ACCESS_TOKEN = WHATSAPP_ACCESS_TOKEN_ENV;
const USER_WHATSAPP_NUMBER = USER_WHATSAPP_NUMBER_ENV; // e.g., "+1234567890"

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // CORS preflight
    if (request.method === "OPTIONS") {
      return handleCORS();
    }
    
    // Route: /notify - Send approval notification
    if (url.pathname === "/notify" && request.method === "POST") {
      return await handleNotify(request, env);
    }
    
    // Route: /response - Handle WhatsApp user response
    if (url.pathname === "/response" && request.method === "POST") {
      return await handleResponse(request, env);
    }
    
    // Route: /health - Health check
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "healthy" }), {
        headers: { "Content-Type": "application/json" }
      });
    }
    
    return new Response("Not Found", { status: 404 });
  }
};

async function handleNotify(request, env) {
  try {
    const payload = await request.json();
    
    // Expected payload:
    // {
    //   "approval_id": "abc123",
    //   "tool_name": "execute_shell_command",
    //   "arguments": {"command": "git push"},
    //   "context": "Deploying to production",
    //   "risk_level": "high"
    // }
    
    const message = formatApprovalMessage(payload);
    
    const response = await fetch(
      `${WHATSAPP_API_URL}/${WHATSAPP_PHONE_ID}/messages`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${WHATSAPP_ACCESS_TOKEN}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          messaging_product: "whatsapp",
          to: USER_WHATSAPP_NUMBER,
          type: "text",
          text: { body: message }
        })
      }
    );
    
    const result = await response.json();
    
    return new Response(JSON.stringify({
      success: true,
      message_id: result.messages?.[0]?.id
    }), {
      headers: { "Content-Type": "application/json" }
    });
    
  } catch (error) {
    return new Response(JSON.stringify({
      success: false,
      error: error.message
    }), { status: 500 });
  }
}

function formatApprovalMessage(payload) {
  return `🔒 *Tool Approval Required*\n\n` +
    `*Tool:* \`${payload.tool_name}\`\n` +
    `*Arguments:* \`${JSON.stringify(payload.arguments)}\`\n` +
    `*Context:* ${payload.context}\n\n` +
    `*Approval ID:* \`${payload.approval_id}\`\n\n` +
    `*Reply with:*\n` +
    `✅ APPROVE ${payload.approval_id}\n` +
    `❌ DENY ${payload.approval_id}\n\n` +
    `⏱️  Timeout: 5 minutes`;
}

async function handleResponse(request, env) {
  // Handle inbound WhatsApp message responses
  // Parse APPROVE/DENY commands and update Notion
  const payload = await request.json();
  
  const { message, from } = payload;
  const command = parseCommand(message);
  
  if (command) {
    // Forward to CoPaw webhook receiver
    await fetch("https://your-copaw-instance.com/webhook", {
      method: "POST",
      body: JSON.stringify({
        type: "whatsapp_approval_response",
        from: from,
        approval_id: command.approval_id,
        action: command.action,
        timestamp: new Date().toISOString()
      })
    });
  }
  
  return new Response(JSON.stringify({ success: true }));
}

function parseCommand(message) {
  const match = message.match(/(APPROVE|DENY)\s+([a-zA-Z0-9_-]+)/i);
  if (match) {
    return {
      action: match[1].toLowerCase(),
      approval_id: match[2]
    };
  }
  return null;
}

function handleCORS() {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type"
    }
  });
}
```

---

## 4. Command Parser Implementation

### Parser: `whatsapp_command_parser.py`

```python
#!/usr/bin/env python3
"""
WhatsApp Command Parser for CoPaw Approvals
Parses APPROVE/DENY commands from WhatsApp messages
"""

import re
from typing import Optional, Dict, Any
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
    """
    message = message.strip()
    
    # Pattern 1: Direct command (APPROVE/DENY + ID)
    direct_pattern = r"(?:✅\s*)?(APPROVE|APPROVED|YES)\s+([a-zA-Z0-9_-]+)"
    match = re.search(direct_pattern, message, re.IGNORECASE)
    if match:
        action = ApprovalAction.APPROVE if match.group(1).upper() in ["APPROVE", "APPROVED", "YES"] else ApprovalAction.DENY
        return ParsedCommand(
            action=action,
            approval_id=match.group(2),
            raw_message=message,
            confidence=0.95
        )
    
    # Pattern 2: Deny command
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
    id_pattern = r"\b([a-zA-Z0-9_-]{6,})\b"
    match = re.search(id_pattern, message)
    if match and len(message.split()) == 1:
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
        return f"{action_emoji} *Approval {command.action.value.upper()}*\n\n" \
               f"ID: `{command.approval_id}`\n" \
               f"Tool execution will proceed." if command.action == ApprovalAction.APPROVE \
               else f"Tool execution blocked."
    else:
        return f"⚠️ *Could not process approval*\n\n" \
               f"ID: `{command.approval_id}`\n" \
               f"Please check the approval ID and try again."
```

---

## 5. Implementation Checklist

### Phase 1: Setup (Day 1)
- [ ] Create Meta Developer Account
- [ ] Create WhatsApp Business App
- [ ] Get Phone Number ID and Access Token
- [ ] Deploy Cloudflare Worker
- [ ] Configure environment variables

### Phase 2: Integration (Day 2)
- [ ] Update `copaw-tool-guard.py` to call Cloudflare Worker
- [ ] Update `whatsapp_bridge.py` with command parser
- [ ] Add Notion status update on WhatsApp response
- [ ] Test end-to-end flow

### Phase 3: Testing (Day 3)
- [ ] Send test "Hello World" message
- [ ] Test approval workflow with real tool call
- [ ] Test denial workflow
- [ ] Test timeout handling

---

## 6. Environment Variables

```bash
# WhatsApp Cloud API Configuration
WHATSAPP_PHONE_ID="123456789012345"  # From Meta Developer Dashboard
WHATSAPP_ACCESS_TOKEN="EAAB..."       # Long-lived access token
USER_WHATSAPP_NUMBER="+1234567890"    # Your mobile number (verified)

# Cloudflare Worker
WHATSAPP_NOTIFY_URL="https://whatsapp-notifier.<subdomain>.workers.dev/notify"

# Local WhatsApp Bridge
WHATSAPP_VERIFY_TOKEN="your_verify_token"
COPAW_WEBHOOK_URL="http://127.0.0.1:8000/webhook"
PORT=8001
```

---

## 7. Cost Estimate

| Component | Free Tier | Paid Tier |
|-----------|-----------|-----------|
| WhatsApp Cloud API | 1,000 conversations/month | $0.005-0.065 per conversation |
| Cloudflare Worker | 100,000 requests/day | $0.30 per million requests |
| **Estimated Monthly** | **$0** (for typical usage) | **$5-10** (high volume) |

---

## 8. Security Considerations

1. **Webhook Verification**: Always verify `x-hub-signature-256` header from Meta
2. **Access Token Storage**: Store in Cloudflare Secrets, not code
3. **Rate Limiting**: Implement rate limiting on Worker (100 req/min)
4. **Approval Timeout**: Auto-deny approvals after 5 minutes
5. **Audit Log**: Log all approval decisions to Notion with timestamps

---

## 9. Next Steps

1. Create Meta Developer Account and WhatsApp Business App
2. Deploy Cloudflare Worker with provided script
3. Test "Hello World" message to verified number
4. Integrate with CoPaw Tool Guard
5. Test end-to-end approval workflow
