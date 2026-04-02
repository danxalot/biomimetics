# CoPaw WhatsApp Integration - Deployment Guide

## Quick Start

This guide walks you through deploying the WhatsApp integration for CoPaw tool approvals.

---

## Prerequisites

1. **Meta Developer Account**: https://developers.facebook.com/
2. **Cloudflare Account** (free tier is sufficient): https://dash.cloudflare.com/
3. **Phone number** for WhatsApp Business API (can be your mobile)

---

## Step 1: Set Up WhatsApp Business API

### 1.1 Create Meta Developer Account

1. Go to https://developers.facebook.com/
2. Click "Get Started" and sign in with Facebook
3. Accept the terms

### 1.2 Create WhatsApp Business App

1. Go to https://developers.facebook.com/apps/
2. Click "Create App"
3. Select **"Other"** → **"Business"** → Click "Next"
4. Fill in app details:
   - **App Name**: `CoPaw WhatsApp Notifications`
   - **App Contact Email**: your email
5. Click "Create App"

### 1.3 Add WhatsApp Product

1. In your app dashboard, find "WhatsApp" and click "Set up"
2. Follow the setup wizard

### 1.4 Get API Credentials

1. Go to **WhatsApp → API Setup**
2. Copy these values:
   - **Phone Number ID**: `123456789012345` (example)
   - **Temporary Access Token**: `EAAB...` (click "Copy")

> ⚠️ **Important**: The temporary token expires in 24 hours. For production, generate a long-lived token:
> 1. Go to **Business Settings → Users → System Users**
> 2. Create a system user with "WhatsApp Business Cloud" permissions
> 3. Generate a long-lived token (valid 60 days)

### 1.5 Add Recipient Phone Number

1. Go to **WhatsApp → Configuration**
2. Under "Message Templates", add your phone number as a test recipient
3. You'll receive a confirmation code via WhatsApp

---

## Step 2: Deploy Cloudflare Worker

### 2.1 Install Wrangler CLI

```bash
npm install -g wrangler
```

### 2.2 Login to Cloudflare

```bash
wrangler login
```

### 2.3 Deploy the Worker

```bash
cd /Users/danexall/biomimetics/cloudflare/whatsapp-notifier

# Deploy with environment variables
wrangler deploy \
  --var WHATSAPP_PHONE_ID:"YOUR_PHONE_ID" \
  --var WHATSAPP_ACCESS_TOKEN:"YOUR_ACCESS_TOKEN" \
  --var USER_WHATSAPP_NUMBER:"+YOUR_NUMBER" \
  --var COPAW_WEBHOOK_URL:"https://your-copaw-instance.com/webhook"
```

### 2.4 Set Secrets (More Secure)

```bash
# Store secrets securely in Cloudflare
wrangler secret put WHATSAPP_PHONE_ID
wrangler secret put WHATSAPP_ACCESS_TOKEN
wrangler secret put USER_WHATSAPP_NUMBER
wrangler secret put COPAW_WEBHOOK_URL

# Deploy
wrangler deploy
```

### 2.5 Get Worker URL

After deployment, note the worker URL:
```
https://whatsapp-notifier.<your-subdomain>.workers.dev
```

---

## Step 3: Configure Local Environment

### 3.1 Set Environment Variables

Add to your `~/.zshrc` or `~/.bashrc`:

```bash
# WhatsApp Cloud API
export WHATSAPP_PHONE_ID="your_phone_id"
export WHATSAPP_ACCESS_TOKEN="your_access_token"
export USER_WHATSAPP_NUMBER="+1234567890"

# Cloudflare Worker (optional - for proxy)
export CLOUDFLARE_WORKER_URL="https://whatsapp-notifier.your-subdomain.workers.dev"
```

Reload shell:
```bash
source ~/.zshrc
```

### 3.2 Test Configuration

```bash
cd /Users/danexall/biomimetics/scripts/whatsapp
python3 whatsapp_notifier.py config
```

Expected output:
```
=== WhatsApp Notifier Configuration ===

WHATSAPP_PHONE_ID: ✓ Set
WHATSAPP_ACCESS_TOKEN: ✓ Set
USER_WHATSAPP_NUMBER: ✓ Set
CLOUDFLARE_WORKER_URL: ✓ Set
```

---

## Step 4: Send Test Message ("Hello World")

### Option A: Direct API

```bash
python3 whatsapp_notifier.py test "+1234567890"
```

### Option B: Via Cloudflare Worker

```bash
curl -X POST "https://whatsapp-notifier.your-subdomain.workers.dev/test" \
  -H "Content-Type: application/json" \
  -d '{"message": "🔔 CoPaw Test - Hello World!"}'
```

### Expected Result

You should receive a WhatsApp message:
```
🔔 CoPaw WhatsApp Integration Test

Hello World! This is a test message from the CoPaw notification system.

If you received this, the integration is working correctly! ✅
```

---

## Step 5: Test Approval Workflow

### 5.1 Send Test Approval Notification

```bash
python3 whatsapp_notifier.py notify \
  --approval-id "test123" \
  --tool "execute_shell_command" \
  --context "Testing approval workflow" \
  --risk "high" \
  --args '{"command": "echo hello"}'
```

### 5.2 Test Command Parser

```bash
python3 whatsapp_notifier.py parse "APPROVE test123"
```

Expected output:
```json
{
  "success": true,
  "action": "approve",
  "approval_id": "test123",
  "confidence": 0.95,
  "response_message": "✅ *Approval APPROVED*\n\nID: `test123`\nTool execution will proceed."
}
```

---

## Step 6: Integrate with CoPaw Tool Guard

### 6.1 Update `copaw-tool-guard.py`

Add WhatsApp notification when requesting approval:

```python
from whatsapp_notifier import send_approval_notification

# In request_approval method:
async def request_approval(self, tool_name: str, arguments: dict, context: str) -> str:
    approval_id = generate_approval_id()
    
    # ... existing Notion creation code ...
    
    # Send WhatsApp notification
    whatsapp_result = send_approval_notification(
        approval_id=approval_id,
        tool_name=tool_name,
        arguments=arguments,
        context=context,
        risk_level="high"
    )
    
    if not whatsapp_result.get("success"):
        logger.warning(f"WhatsApp notification failed: {whatsapp_result.get('error')}")
    
    return approval_id
```

### 6.2 Update `whatsapp_bridge.py`

Add command parser integration:

```python
from whatsapp_command_parser import parse_approval_command

@app.post("/whatsapp-webhook")
async def handle_whatsapp_webhook(request: Request):
    # ... existing code ...
    
    # Parse approval commands
    command = parse_approval_command(body)
    if command:
        # Update Notion approval status
        await update_notion_approval(command.approval_id, command.action.value)
        
        # Send confirmation
        await send_whatsapp_message(
            to=from_id,
            message=format_response_message(command, True)
        )
```

---

## Troubleshooting

### Error: "Invalid access token"

- Token may have expired. Generate a new long-lived token.
- Check token has `whatsapp_business_messaging` permission.

### Error: "Phone number not verified"

- The recipient number must be added as a test recipient in Meta Developer Console.
- For production, submit your phone number for verification.

### Error: "Worker not found"

- Check worker was deployed: `wrangler deploy`
- Verify URL format: `https://whatsapp-notifier.<subdomain>.workers.dev`

### Messages not being received

- Check WhatsApp Business API quota (1,000 free conversations/month)
- Verify phone number format: `+1234567890` (with country code)

---

## Cost Estimate

| Component | Free Tier | Your Usage |
|-----------|-----------|------------|
| WhatsApp Cloud API | 1,000 conversations/month | ~50-100/month (approvals) |
| Cloudflare Worker | 100,000 requests/day | ~100-500/day |
| **Monthly Cost** | **$0** | **$0** |

---

## Next Steps

1. ✅ Send "Hello World" test message
2. ✅ Test approval notification format
3. ✅ Test command parser with various inputs
4. ⏳ Integrate with CoPaw Tool Guard
5. ⏳ Set up Meta webhook for inbound responses
6. ⏳ Test end-to-end approval workflow

---

## Support

- **Meta Developer Docs**: https://developers.facebook.com/docs/whatsapp/cloud-api
- **Cloudflare Workers Docs**: https://developers.cloudflare.com/workers/
- **Design Document**: See `WHATSAPP_INTEGRATION_DESIGN.md`
