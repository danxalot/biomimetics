# Notion Webhook Configuration Guide

## ✅ Your Notion Event Router is Ready!

**Webhook URL**: `https://hooks.arca-vsa.tech`  
**Signing Secret**: ``

---

## Step 1: Configure Notion Webhook

### Option A: Using Notion Native Webhooks (Recommended)

1. **Open your Notion Database**
   - Go to the database where you create tasks

2. **Add Webhook Integration**
   - Click `...` (three dots) in top right
   - Click **Connections** → **Add connection**
   - Search for "Webhooks" or use a webhook service

3. **Configure Webhook**
   - **URL**: `https://hooks.arca-vsa.tech`
   - **Signing Secret**: ``
   - **Triggers**: 
     - ✅ Pages added to database
     - ✅ Page content changed
     - ✅ Page properties changed

4. **Test Webhook**
   - Create a new task in your database
   - Add tag: `ARCA`
   - Check GitHub for new issue

---

### Option B: Using Hookdeck (Free Webhook Relay)

If Notion doesn't support direct webhooks in your plan:

1. **Create Hookdeck Account**
   - Go to https://hookdeck.com
   - Sign up (free tier available)

2. **Create Connection**
   - Source: Notion
   - Destination: `https://hooks.arca-vsa.tech`

3. **Configure Notion**
   - Use Hookdeck's webhook URL in Notion
   - Hookdeck forwards to your Worker

---

### Option C: Using Make.com / Zapier

1. **Create New Scenario/Zap**
   - Trigger: Notion → New Database Item
   - Action: Webhook → POST to `https://hooks.arca-vsa.tech`

2. **Configure Webhook**
   - URL: `https://hooks.arca-vsa.tech`
   - Method: POST
   - Headers:
     ```
     Content-Type: application/json
     X-Notion-Signature: sha256=<generated>
     ```
   - Body: Map Notion fields to Worker payload format

---

## Step 2: Database Setup

### Required Database Properties

Your Notion database should have these properties:

| Property Name | Type | Purpose |
|---------------|------|---------|
| **Name** (or Title) | Title | Task title |
| **Tags** | Multi-select | Categorization (use `ARCA` for dev tasks) |
| **Description** | Rich text | Task details |
| **Status** | Select | Optional: To-do, In Progress, Done |
| **Priority** | Select | Optional: Low, Medium, High |

### Recommended Tags

Create these tags in your Multi-select property:

- `ARCA` - Triggers GitHub issue creation
- `DEV` - Development task (also triggers GitHub)
- `CODE` - Code review/task (also triggers GitHub)
- `PM` - Project management
- `URGENT` - High priority
- `BACKLOG` - Future consideration

---

## Step 3: Test End-to-End

### 1. Create Test Task in Notion

**Title**: `Test ARCA Task`  
**Tags**: `ARCA`, `urgent`  
**Description**: `Testing Phase 1 deployment - this should create a GitHub issue`

### 2. Verify GitHub Issue

Visit: https://github.com/danxalot/ARCA/issues

Expected:
- ✅ New issue created
- ✅ Title matches Notion task
- ✅ Description includes Notion metadata
- ✅ Tags applied as labels

### 3. Verify Pub/Sub Message

```bash
# Create subscription if needed
gcloud pubsub subscriptions create os-events-sub --topic=os-events

# Pull messages
gcloud pubsub subscriptions pull os-events-sub --auto-ack --limit=5
```

Expected:
- ✅ Message published
- ✅ Payload contains task data
- ✅ Attributes include event type and tags

---

## Webhook Payload Format

Your Worker expects this payload structure:

```json
{
  "event": {
    "id": "notion-page-id",
    "created_time": "2024-01-01T00:00:00.000Z",
    "last_edited_time": "2024-01-01T00:00:00.000Z",
    "properties": {
      "title": [
        {
          "plain_text": "Task Title"
        }
      ],
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

## Troubleshooting

### Webhook Not Triggering

**Check**:
1. Webhook URL is correct: `https://hooks.arca-vsa.tech`
2. Database has correct permissions
3. Webhook triggers are enabled

**Test**:
```bash
curl -X POST https://hooks.arca-vsa.tech \
  -H "Content-Type: application/json" \
  -d '{"event":{"id":"test","properties":{"title":[{"plain_text":"Test"}]}}}'
```

Expected: `{"success":true,"message":"Event received and processing"}`

---

### GitHub Issue Not Created

**Check**:
1. Task has `ARCA`, `DEV`, or `CODE` tag
2. GitHub PAT is valid (check Cloudflare Secrets)
3. GitHub repo exists and is accessible

**View Logs**:
```bash
cd services/notion-event-router
wrangler tail --env production
```

---

### Signature Validation Failed

**Check**:
1. Signing secret matches exactly
2. Notion is sending `X-Notion-Signature` header
3. Secret in Cloudflare matches: ``

**Update Secret**:
```bash
wrangler secret put NOTION_WEBHOOK_SECRET --env production
```

---

## Monitoring

### Cloudflare Worker Logs
```bash
wrangler tail --env production
```

### Cloudflare Dashboard
1. https://dash.cloudflare.com
2. Workers & Pages → notion-event-router-production
3. Analytics tab

### GitHub Issues
https://github.com/danxalot/ARCA/issues

### GCP Pub/Sub
```bash
gcloud pubsub subscriptions pull os-events-sub --auto-ack
```

---

## Your Configuration

| Setting | Value |
|---------|-------|
| **Webhook URL** | `https://hooks.arca-vsa.tech` |
| **Signing Secret** | `` |
| **GitHub Repo** | `danxalot/ARCA` |
| **Pub/Sub Topic** | `os-events` |
| **Trigger Tags** | `ARCA`, `DEV`, `CODE` |

---

## Next Steps

After Notion webhook is configured:

1. ✅ Create test task with `ARCA` tag
2. ✅ Verify GitHub issue created
3. ✅ Verify Pub/Sub message published
4. ✅ **Phase 1 Complete!** 🎉
5. → Proceed to **Phase 2: The Cognitive Core** (Local MCPs)

---

## Security Notes

- ✅ Webhook uses HMAC SHA256 signature verification
- ✅ Secrets stored in Cloudflare Secrets (encrypted)
- ✅ HTTPS enforced (Cloudflare SSL)
- ✅ GitHub PAT has minimal required scopes
- ✅ GCP Service Account has Publisher role only

**Never share your signing secret publicly!**
