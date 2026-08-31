# Notion Developer Integration Setup Guide

**The 100% Free, Real-Time Webhook Solution**

---

## Overview

This guide walks you through setting up Notion's native Developer Integration with your Notion Event Router. This method:

- ✅ **100% Free** - No third-party services
- ✅ **Real-time** - Instant webhook delivery
- ✅ **Reliable** - Direct from Notion to Cloudflare
- ✅ **Secure** - HMAC signature verification

---

## Step 1: Verification Trap is Deployed ✅

Your Cloudflare Worker has been updated with the verification trap code.

**What it does**: When Notion sends the verification token, your Worker will:
1. Log it to the console
2. Return "OK" to complete verification
3. Continue normal operation for real webhooks

---

## Step 2: Create Notion Integration

### 1. Go to Notion Integrations

Open: **https://notion.so/my-integrations**

### 2. Create New Integration

Click **+ New integration**

Fill in the details:
- **Name**: `Biomimetic OS Router` (or your choice)
- **Logo**: (optional)
- **Associated workspace**: Select your workspace
- **Capabilities**: 
  - ✅ **Read content** (required)

Click **Submit**

### 3. Save Your Credentials

After creating, you'll see:
- **Internal Integration Token**: `secret_xxx...`
- **Client ID**: Not needed for internal integrations

**⚠️ Important**: Copy the Internal Integration Token - you may need it later!

---

## Step 3: Register the Webhook

### 1. Open Webhooks Tab

In your Integration dashboard, click **Webhooks** on the left sidebar.

### 2. Create Subscription

Click **+ Create a subscription**

### 3. Configure Webhook

**Webhook URL**: 
```
https://hooks.arca-vsa.tech
```

**Event triggers**:
- ✅ **Page created**
- ✅ **Page updated**

**Optional - Specific databases**:
- You can select specific databases to monitor
- Or leave empty to monitor all databases the integration has access to

Click **Create subscription**

---

## Step 4: Catch the Verification Token

### 1. Open Terminal for Live Logs

```bash
cd /Users/danexall/Documents/VS Code Projects/ARCA/services/notion-event-router
npx wrangler tail --env production
```

**Keep this terminal window open and visible!**

### 2. Watch for Verification Token

Within 5 seconds of creating the subscription, you'll see:

```
🔑 NOTION VERIFICATION TOKEN: secret_XXXXXXXXXXXXXXXXXXXXXXXX
Copy this token and paste it into Notion's verification field!
```

### 3. Verify in Notion

1. In the Notion Webhooks dashboard, click **Verify** next to your webhook
2. Paste the token from your terminal
3. Click **Confirm**

**Status should change to**: ✅ **Verified**

---

## Step 5: Grant Database Access

Your integration needs permission to read your database.

### 1. Open Your Notion Database

Navigate to the database where you create tasks.

### 2. Add Integration Connection

Click **`...`** (three dots) in top right → **Connections** → **Add connection**

Select your integration: **Biomimetic OS Router**

Click **Confirm**

---

## Step 6: Test End-to-End

### 1. Create Test Task

In your Notion database, create:

| Property | Value |
|----------|-------|
| **Name** | `Test ARCA Task - Phase 1` |
| **Tags** | `ARCA`, `urgent` |
| **Description** | `Testing Notion Developer Integration webhook` |

### 2. Verify GitHub Issue (within 5 seconds)

Visit: **https://github.com/danxalot/ARCA/issues**

Expected:
- ✅ New issue created
- ✅ Title matches Notion task
- ✅ Description includes Notion metadata

### 3. Check Worker Logs

Your terminal should show:

```
🔑 NOTION VERIFICATION TOKEN: secret_... (from earlier)
Received Notion task: {
  title: "Test ARCA Task - Phase 1",
  tags: ["ARCA", "urgent"],
  notionId: "xxx-xxx-xxx"
}
Creating GitHub issue for ARCA task...
GitHub issue created: https://github.com/danxalot/ARCA/issues/xxx
Publishing to GCP Pub/Sub...
Published to Pub/Sub: xxxxx
```

---

## Troubleshooting

### Verification Token Not Appearing

**Check**:
1. Terminal is running `wrangler tail`
2. Webhook URL is exactly: `https://hooks.arca-vsa.tech`
3. Worker was deployed successfully

**Retry**:
```bash
# Redeploy to ensure verification trap is active
cd services/notion-event-router
npm run deploy:prod

# Watch logs
npx wrangler tail --env production

# In Notion: Delete webhook and recreate
```

---

### Webhook Status Shows "Failed"

**Check**:
1. Verification was completed
2. Database has integration connection
3. Worker logs show requests

**Fix**:
```bash
# View recent logs
wrangler tail --env production

# Test manually
curl -X POST https://hooks.arca-vsa.tech \
  -H "Content-Type: application/json" \
  -d '{"event":{"id":"test","properties":{"title":[{"plain_text":"Test"}]}}}'
```

---

### GitHub Issue Not Created

**Check**:
1. Task has `ARCA` tag (case-insensitive)
2. GitHub PAT is valid in Cloudflare Secrets
3. Worker logs show "Creating GitHub issue"

**Debug**:
```bash
# Check Cloudflare Secrets
wrangler secret list --env production

# Should show:
# - GITHUB_PAT
# - GCP_SERVICE_ACCOUNT_JSON
# - NOTION_WEBHOOK_SECRET
```

---

## Webhook Payload Format

Notion sends this structure:

```json
{
  "verification_token": "secret_xxx",  // Only on first request
  "event": {
    "id": "page-id",
    "type": "page",
    "created_time": "2024-01-01T00:00:00.000Z",
    "last_edited_time": "2024-01-01T00:00:00.000Z",
    "properties": {
      "Name": {
        "title": [
          {
            "plain_text": "Task Title"
          }
        ]
      },
      "Tags": {
        "multi_select": [
          {
            "name": "ARCA"
          }
        ]
      },
      "Description": {
        "rich_text": [
          {
            "plain_text": "Task description..."
          }
        ]
      }
    },
    "parent": {
      "type": "database_id",
      "database_id": "database-id"
    }
  }
}
```

---

## Security Best Practices

### 1. Protect Your Integration Token

- ✅ Store in Cloudflare Secrets (already done)
- ❌ Never commit to git
- ❌ Never share publicly

### 2. Signature Verification

Your Worker validates HMAC SHA256 signatures automatically. The signing secret is:

```

```

### 3. Limit Database Access

Only grant integration access to specific databases that need webhook support.

---

## Monitoring

### Real-time Logs
```bash
npx wrangler tail --env production
```

### Cloudflare Dashboard
1. https://dash.cloudflare.com
2. Workers & Pages → notion-event-router-production
3. Analytics tab

### Notion Integration Dashboard
https://notion.so/my-integrations → Your Integration → Webhooks

---

## Your Configuration Summary

| Component | Value |
|-----------|-------|
| **Webhook URL** | `https://hooks.arca-vsa.tech` |
| **Integration Name** | Biomimetic OS Router |
| **Integration Token** | `secret_xxx...` (save this!) |
| **Signing Secret** | `` |
| **GitHub Repo** | `danxalot/ARCA` |
| **Pub/Sub Topic** | `os-events` |
| **Trigger Tags** | `ARCA`, `DEV`, `CODE` |

---

## Next Steps

After successful verification:

1. ✅ **Test with real task** - Create task with `ARCA` tag
2. ✅ **Verify GitHub issue** - Check danxalot/ARCA/issues
3. ✅ **Check Pub/Sub** - `gcloud pubsub subscriptions pull os-events-sub`
4. ✅ **Phase 1 Complete!** 🎉
5. → **Proceed to Phase 2** (Local MCPs)

---

## Quick Reference Commands

```bash
# View live logs
npx wrangler tail --env production

# Redeploy if needed
npm run deploy:prod

# Check GitHub issues
curl -H "Authorization: Bearer $(cat ~/.secrets/github_token)" \
  https://api.github.com/repos/danxalot/ARCA/issues?state=all&per_page=5

# Check Pub/Sub
gcloud pubsub subscriptions pull os-events-sub --auto-ack --limit=5
```

---

**Ready to set up? Follow Steps 2-6 above!** 🚀
