# Notion Event Router - Phase 1 Setup Guide

## Overview

This Cloudflare Worker receives Notion webhooks and:
1. Creates GitHub Issues for ARCA-tagged tasks
2. Publishes events to GCP Pub/Sub for system-wide processing

## Prerequisites

- [x] Cloudflare account (free tier OK)
- [x] GCP project with Pub/Sub API enabled
- [x] GitHub repository for issue tracking
- [x] Notion workspace with webhook capability
- [x] Node.js 18+ and npm installed

## Installation

### 1. Install Dependencies

```bash
cd services/notion-event-router
npm install
```

### 2. Create GCP Service Account

```bash
# In GCP Console or via gcloud:
gcloud iam service-accounts create notion-event-router \
  --display-name="Notion Event Router" \
  --project=YOUR_GCP_PROJECT_ID

# Grant Pub/Sub Publisher role
gcloud projects add-iam-policy-binding YOUR_GCP_PROJECT_ID \
  --member="serviceAccount:notion-event-router@YOUR_GCP_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

# Generate JSON key
gcloud iam service-accounts keys create service-account.json \
  --iam-account=notion-event-router@YOUR_GCP_PROJECT_ID.iam.gserviceaccount.com
```

### 3. Create GCP Pub/Sub Topic

```bash
gcloud pubsub topics create os-events --project=YOUR_GCP_PROJECT_ID
```

### 4. Create GitHub Personal Access Token

1. Go to: https://github.com/settings/tokens
2. Generate new token (classic)
3. Scopes: `repo` (full control of private repositories)
4. Copy the token (starts with `ghp_`)

### 5. Configure Notion Webhook

1. In Notion, go to your database
2. Click "..." → "Connections" → "Add connection"
3. Search for your webhook endpoint (you'll get this after deployment)
4. Or use a tool like [Hookdeck](https://hookdeck.com/) for local testing

### 6. Set Up Local Development

```bash
# Copy example env file
cp .env.example .dev.vars

# Edit .dev.vars with your values:
# - GCP_PROJECT_ID
# - GITHUB_OWNER
# - GITHUB_REPO
# - NOTION_WEBHOOK_SECRET (generate a random string)
```

### 7. Set Secrets (Production)

```bash
# GitHub PAT
wrangler secret put GITHUB_PAT
# Paste your ghp_... token when prompted

# GCP Service Account JSON
wrangler secret put GCP_SERVICE_ACCOUNT_JSON
# Paste the entire service-account.json content when prompted

# Notion Webhook Secret
wrangler secret put NOTION_WEBHOOK_SECRET
# Paste your random secret string
```

### 8. Update wrangler.toml

Edit `wrangler.toml` and replace:
```toml
GCP_PROJECT_ID = "your-actual-project-id"
GITHUB_OWNER = "your-github-username"
GITHUB_REPO = "your-target-repo"
NOTION_WEBHOOK_SECRET = "your-secret"
```

### 9. Test Locally

```bash
npm run dev
```

Worker will be available at: http://localhost:8787

Test with curl:
```bash
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -H "X-Notion-Signature: sha256=test" \
  -d '{
    "event": {
      "id": "test-123",
      "created_time": "2024-01-01T00:00:00.000Z",
      "properties": {
        "title": [{"plain_text": "Test Task"}],
        "Tags": {"multi_select": [{"name": "ARCA"}]},
        "Description": {"rich_text": [{"plain_text": "Test description"}]}
      }
    }
  }'
```

### 10. Deploy to Cloudflare

```bash
npm run deploy
```

Your worker will be deployed to:
```
https://notion-event-router.<your-subdomain>.workers.dev
```

### 11. Configure Notion Webhook

Use a webhook service to forward Notion events to your Worker:

**Option A: Hookdeck (Recommended for testing)**
1. Create account at https://hookdeck.com
2. Create connection: Notion → Your Worker URL
3. Configure Notion to send webhooks to Hookdeck

**Option B: Direct Webhook (Production)**
1. Deploy Worker with custom domain
2. Configure Notion integration
3. Set webhook URL to your Worker endpoint

## Testing End-to-End

1. Create a task in Notion with tag `ARCA`
2. Check GitHub repo for new issue
3. Check GCP Pub/Sub for message:
   ```bash
   gcloud pubsub subscriptions pull os-events-sub --auto-ack
   ```

## Troubleshooting

### Worker returns 401
- Check NOTION_WEBHOOK_SECRET matches
- Verify signature in Notion webhook settings

### GitHub issue not created
- Check GITHUB_PAT is valid and has `repo` scope
- Verify GITHUB_OWNER and GITHUB_REPO are correct
- Check Worker logs in Cloudflare Dashboard

### Pub/Sub message not published
- Verify GCP_SERVICE_ACCOUNT_JSON is valid
- Check service account has `roles/pubsub.publisher`
- Verify GCP_PROJECT_ID and PUBSUB_TOPIC_ID

## Next Steps

After Phase 1 is working:
- Set up monitoring (Cloudflare Logs + GCP Cloud Monitoring)
- Add retry logic for failed requests
- Create dead letter queue for Pub/Sub failures
- Proceed to Phase 2: Local MCPs
