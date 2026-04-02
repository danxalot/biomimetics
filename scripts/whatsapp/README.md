# CoPaw WhatsApp Integration

Human-in-the-Loop (HITL) approval workflow via WhatsApp.

## Components

```
scripts/whatsapp/
├── whatsapp_notifier.py       # Main notifier utility
├── whatsapp_command_parser.py # Command parser for APPROVE/DENY
└── README.md                  # This file

cloudflare/whatsapp-notifier/
├── src/worker.js              # Cloudflare Worker script
└── wrangler.toml              # Worker configuration

docs/
├── WHATSAPP_INTEGRATION_DESIGN.md  # Technical design document
└── WHATSAPP_DEPLOYMENT.md          # Deployment guide
```

## Quick Start

### 1. Test Command Parser

```bash
cd scripts/whatsapp
python3 whatsapp_command_parser.py
```

### 2. Check Configuration

```bash
python3 whatsapp_notifier.py config
```

### 3. Set Environment Variables

```bash
export WHATSAPP_PHONE_ID="your_phone_id"
export WHATSAPP_ACCESS_TOKEN="your_token"
export USER_WHATSAPP_NUMBER="+1234567890"
```

### 4. Send Test Message

```bash
python3 whatsapp_notifier.py test "+1234567890"
```

### 5. Send Approval Notification

```bash
python3 whatsapp_notifier.py notify \
  --approval-id "abc123" \
  --tool "execute_shell_command" \
  --context "Deploying to production" \
  --risk "high" \
  --args '{"command": "git push"}'
```

### 6. Parse Commands

```bash
python3 whatsapp_notifier.py parse "APPROVE abc123"
python3 whatsapp_notifier.py parse "DENY xyz789"
python3 whatsapp_notifier.py parse "✅ APPROVE test123"
```

## Cloudflare Worker Deployment

See `docs/WHATSAPP_DEPLOYMENT.md` for full deployment instructions.

```bash
cd cloudflare/whatsapp-notifier
wrangler deploy
```

## API Reference

### whatsapp_notifier.py

```bash
# Send test message
python3 whatsapp_notifier.py test <phone_number> [--message "custom"]

# Send approval notification
python3 whatsapp_notifier.py notify \
  --approval-id <id> \
  --tool <tool_name> \
  --context <context> \
  --risk <low|medium|high> \
  [--args '{"key": "value"}'] \
  [--phone <number>]

# Parse command
python3 whatsapp_notifier.py parse "<message>"

# Check config
python3 whatsapp_notifier.py config
```

### whatsapp_command_parser.py

```python
from whatsapp_command_parser import (
    parse_approval_command,
    format_approval_notification,
    format_response_message,
    ApprovalAction
)

# Parse incoming message
command = parse_approval_command("APPROVE abc123")
print(command.action)  # ApprovalAction.APPROVE
print(command.approval_id)  # "abc123"

# Format notification
msg = format_approval_notification(
    approval_id="abc123",
    tool_name="execute_shell_command",
    arguments={"command": "ls -la"},
    context="Listing files",
    risk_level="medium"
)

# Format response
response = format_response_message(command, success=True)
```

## Supported Commands

| Format | Example | Confidence |
|--------|---------|------------|
| Direct approve | `APPROVE abc123` | 95% |
| Direct deny | `DENY xyz789` | 95% |
| Emoji approve | `✅ APPROVE abc123` | 95% |
| Emoji deny | `❌ DENY xyz789` | 95% |
| Implicit | `abc123` | 70% |

## Message Format

Approval notifications are formatted as:

```
🔒 *Tool Approval Required*

*Tool:* `execute_shell_command`
*Arguments:* `{"command": "git push"}`
*Context:* Deploying to production

🔴 *Risk Level:* high

*Approval ID:* `abc123`

*Reply with:*
✅ APPROVE abc123
❌ DENY abc123

⏱️  Timeout: 5 minutes
```

## Integration Points

### CoPaw Tool Guard

```python
# In copaw-tool-guard.py
from whatsapp_notifier import send_approval_notification

async def request_approval(self, tool_name, arguments, context):
    approval_id = generate_id()
    
    # Send WhatsApp notification
    result = send_approval_notification(
        approval_id=approval_id,
        tool_name=tool_name,
        arguments=arguments,
        context=context,
        risk_level="high"
    )
    
    return approval_id
```

### WhatsApp Bridge (Inbound)

```python
# In whatsapp_bridge.py
from whatsapp_command_parser import parse_approval_command

@app.post("/whatsapp-webhook")
async def handle_webhook(request):
    body = message.get("body", "")
    command = parse_approval_command(body)
    
    if command:
        await update_notion_approval(command.approval_id, command.action)
```

## Cost

- **WhatsApp Cloud API**: Free for first 1,000 conversations/month
- **Cloudflare Worker**: Free for 100,000 requests/day
- **Estimated monthly cost**: $0 (typical usage)

## Documentation

- **Design Document**: `docs/WHATSAPP_INTEGRATION_DESIGN.md`
- **Deployment Guide**: `docs/WHATSAPP_DEPLOYMENT.md`
