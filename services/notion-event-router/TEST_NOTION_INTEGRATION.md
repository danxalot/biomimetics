# Notion Integration Test Guide

**Date**: 2026-03-13  
**Goal**: Verify end-to-end flow from Notion → GitHub + Pub/Sub

---

## Your Webhook Credentials

**URL**: `https://hooks.arca-vsa.tech`  
**Secret**: ``

---

## Step 1: Configure Notion Webhook

### In Your Notion Database:

1. **Open your task database** in Notion
2. Click **`...`** (three dots) in top right corner
3. Click **Connections** → **Add connection**
4. Search for **"Webhooks"** or your webhook service
5. Configure:
   - **Webhook URL**: `https://hooks.arca-vsa.tech`
   - **Signing Secret**: ``
   - **Triggers**:
     - ✅ Pages added to database
     - ✅ Page properties changed

### If Notion Doesn't Have Native Webhooks:

Use **Hookdeck** (free relay service):

1. Go to https://hookdeck.com
2. Sign up (free)
3. Create connection:
   - **Source**: Notion
   - **Destination**: `https://hooks.arca-vsa.tech`
4. Use Hookdeck's URL in Notion

---

## Step 2: Create Test Task

### In Your Notion Database:

**Create a new task with these exact values:**

| Property | Value |
|----------|-------|
| **Name/Title** | `Test ARCA Task - Phase 1` |
| **Tags** | `ARCA`, `urgent` |
| **Description** | `This is a test task to verify Phase 1 deployment. If you see this, the webhook is working!` |

---

## Step 3: Verify GitHub Issue

### Check Immediately (within 5 seconds):

**Visit**: https://github.com/danxalot/ARCA/issues

**Expected**:
- ✅ New issue created
- ✅ Title: `Test ARCA Task - Phase 1`
- ✅ Description includes:
  - Notion ID
  - Created timestamp
  - Tags listed
  - Link back to Notion setup guide

**Example Issue Content**:
```markdown
## 📋 Task from Notion

**Source**: Notion Database
**Notion ID**: `xxx-xxx-xxx`
**Created**: 2026-03-13T...

---

## Description

This is a test task to verify Phase 1 deployment...

---

## Tags

- `ARCA`
- `urgent`

*Automatically created by Notion Event Router*
```

---

## Step 4: Verify Pub/Sub Message

### Check GCP Pub/Sub:

```bash
# Create subscription (first time only)
gcloud pubsub subscriptions create os-events-sub --topic=os-events

# Pull messages
gcloud pubsub subscriptions pull os-events-sub --auto-ack --limit=5
```

**Expected Output**:
```
MESSAGE_ID: xxxxx
DATA: {"event_type":"notion.task.created","source":"notion",...}
ATTRIBUTES:
  event-type: notion.task.created
  source: notion
  notion-id: xxx-xxx-xxx
  tags: ARCA,urgent
```

---

## Step 5: View Worker Logs

### Real-time Logs:

```bash
cd /Users/danexall/Documents/VS Code Projects/ARCA/services/notion-event-router
wrangler tail --env production
```

**Expected Log Output**:
```
Received Notion task: {
  title: "Test ARCA Task - Phase 1",
  tags: ["ARCA", "urgent"],
  notionId: "xxx-xxx-xxx"
}
Creating GitHub issue for ARCA task...
GitHub issue created: https://github.com/danxalot/ARCA/issues/xxx
Publishing to GCP Pub/Sub...
Published to Pub/Sub: xxxxx
Event processing results: {...}
```

---

## Troubleshooting

### Issue Not Created in GitHub

**Check**:
1. Task has `ARCA` tag (case-insensitive)
2. GitHub PAT is valid
3. Worker logs show "Creating GitHub issue"

**Debug**:
```bash
# View logs
wrangler tail --env production

# Check GitHub API directly
curl -H "Authorization: Bearer $(cat /Users/danexall/Documents/VS\ Code\ Projects/ARCA/.secrets/github_token)" \
  https://api.github.com/repos/danxalot/ARCA/issues?state=all&per_page=3
```

---

### Pub/Sub Message Not Received

**Check**:
1. GCP Service Account has `roles/pubsub.publisher`
2. Topic `os-events` exists
3. Worker logs show "Publishing to GCP Pub/Sub"

**Debug**:
```bash
# Verify topic exists
gcloud pubsub topics list | grep os-events

# Check subscription
gcloud pubsub subscriptions describe os-events-sub

# Pull without auto-ack (to see if messages are there)
gcloud pubsub subscriptions pull os-events-sub
```

---

### Webhook Not Triggering

**Check**:
1. Webhook URL is exactly: `https://hooks.arca-vsa.tech`
2. Webhook triggers are enabled in Notion
3. Database has correct permissions

**Test Webhook Directly**:
```bash
curl -X POST https://hooks.arca-vsa.tech \
  -H "Content-Type: application/json" \
  -d '{"event":{"id":"direct-test","properties":{"title":[{"plain_text":"Direct Test"}],"Tags":{"multi_select":[{"name":"ARCA"}]}}}}'
```

Expected: `{"success":true,"message":"Event received and processing"}`

---

## Success Criteria

Phase 1 test passes when:

- [ ] ✅ Notion webhook configured
- [ ] ✅ Test task created with `ARCA` tag
- [ ] ✅ GitHub issue created (within 5 seconds)
- [ ] ✅ Pub/Sub message published
- [ ] ✅ Worker logs show successful processing

---

## Test Results Template

Copy and fill this out after testing:

```markdown
## Test Results

**Date**: 2026-03-13
**Tester**: [Your Name]

### Configuration
- [ ] Webhook URL entered: ___
- [ ] Signing secret saved: ___

### Test Task
- [ ] Title: ___
- [ ] Tags: ___
- [ ] Description: ___

### Verification
- [ ] GitHub issue created: YES/NO
  - Issue URL: ___
  - Time to create: ___ seconds
- [ ] Pub/Sub message published: YES/NO
  - Message ID: ___
- [ ] Worker logs viewed: YES/NO

### Issues Found
[List any issues]

### Overall Status
PASS / FAIL
```

---

## Next Steps After Successful Test

1. ✅ **Phase 1 Complete!** 🎉
2. Configure production Notion database
3. Set up monitoring alerts
4. → **Proceed to Phase 2** (Local MCPs)

---

## Support

### Quick Commands

```bash
# View live logs
wrangler tail --env production

# Check recent GitHub issues
curl -s https://github.com/danxalot/ARCA/issues

# Check Pub/Sub
gcloud pubsub subscriptions pull os-events-sub --auto-ack --limit=5

# Redeploy if needed
cd services/notion-event-router && npm run deploy:prod
```

### Contact
- Worker logs: Cloudflare Dashboard
- GitHub issues: https://github.com/danxalot/ARCA
- Pub/Sub: GCP Console
