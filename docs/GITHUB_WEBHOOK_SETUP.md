---
tags: ["#bios/architecture", "#bios/swarm", "#bios/infrastructure"]
status: active
---

# GitHub Webhook Setup Guide

## Worker Deployed ✓

**Worker URL**: `https://arca-github-notion-sync.dan-exall.workers.dev`

---

## What the Worker Does

When GitHub events occur, the Worker:

1. **Issues**: Creates Notion entries in Biomimetic OS database
    - Automatically tags issues labeled "Serena" or "AI-Agent"
    - Syncs issue state (open/closed) to Notion status
    - Includes labels, description, and GitHub link
    - Forwards event data to GCP memory system for contextual AI enrichment    #bios/notion #bios/notion/sync #bios/notion/schema #bios/personal_assistant #bios/personal_assistant/memory #bios/notion #bios/notion/sync #bios/notion/schema #bios/personal_assistant #bios/personal_assistant/memory

2. **Pull Requests**: Tracks PR lifecycle
    - Opened → "In Progress"
    - Closed/Merged → "Done"
    - Forwards event data to GCP memory system for contextual AI enrichment    #bios/notion #bios/notion/sync #bios/personal_assistant #bios/personal_assistant/memory #bios/notion #bios/notion/sync #bios/personal_assistant #bios/personal_assistant/memory

3. **Push Events**: Logs commits to main/master branches
    - Summarizes commit messages
    - Tracks pusher information
    - Forwards event data to GCP memory system for contextual AI enrichment    #bios/notion #bios/notion/sync #bios/personal_assistant #bios/personal_assistant/memory #bios/notion #bios/notion/sync #bios/personal_assistant #bios/personal_assistant/memory

Additionally, the Worker handles:
- **Serena Agent Requests**: Processing SYNC_TASK, UPDATE_STATUS, CREATE_ENTRY, QUERY actions
- **GCP Memory Insights**: Processing task suggestions and context updates from the memory system
- **CoPaw Requests**: Handling tool approval requests, skill execution queues, and approval responses    #bios/notion #bios/notion/query #bios/personal_assistant #bios/personal_assistant/task #bios/copaw #bios/copaw/workflow #bios/copaw/action #bios/notion #bios/notion/query #bios/personal_assistant #bios/personal_assistant/task #bios/copaw #bios/copaw/workflow #bios/copaw/action

---

## Setup Instructions

### Step 1: Navigate to Repository Settings

1. Go to: **https://github.com/danxalot/biomimetics**
2. Click **Settings** tab
3. Click **Webhooks** in the left sidebar
4. Click **Add webhook** button #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational

### Step 2: Configure Webhook

Fill in the following:

| Field | Value |
|-------|-------|
| **Payload URL** | `https://arca-github-notion-sync.dan-exall.workers.dev` |
| **Content type** | `application/json` |
| **Secret** | *(See below)* | #bios/architecture #bios/architecture/config #bios/notion #bios/notion/sync #bios/architecture #bios/architecture/config #bios/notion #bios/notion/sync

### Step 3: Get Webhook Secret

The webhook secret was generated and stored in two places:

**Option A: From local file**
```bash
cat ~/biomimetics/secrets/github_webhook_secret.txt
```

**Option B: From Azure Key Vault**
```bash
az keyvault secret show --vault-name arca-mcp-kv-dae --name github-webhook-secret --query value -o tsv
```

Copy the secret and paste it into the **Secret** field in GitHub.

### Step 4: Select Events

Choose **which events to trigger**:

- ☑️ **Issues** - For issue creation, labeling, closing
- ☑️ **Pull requests** - For PR tracking
- ☑️ **Pushes** - For commit logging #bios/copaw #bios/copaw/trigger #bios/notion #bios/notion/sync #bios/copaw #bios/copaw/trigger #bios/notion #bios/notion/sync

Or select **Let me select individual events** and check:
- [x] Issues
- [x] Pull requests
- [x] Pushes

### Step 5: Save

Click **Add webhook** at the bottom.

---

## Verification

### Test the Webhook

1. After adding, GitHub will show a **Recent Deliveries** section
2. You should see a ping event with ✓ response
3. Create a test issue in the repository
4. Check the delivery shows 200 OK    #bios/meta #bios/meta/operational #bios/notion #bios/notion/sync #bios/meta #bios/meta/operational #bios/notion #bios/notion/sync

### Verify Notion Sync

1. Create a new issue in the biomimetics repository
2. Add the "Serena" label to it
3. Check your Notion Biomimetic OS database
4. A new entry should appear with:
   - Title: `[SERENA] Your Issue Title`
   - Status: Not Started / In Progress
   - Source: GitHub: danxalot/biomimetics
   - Github Link: URL to the issue    #bios/notion #bios/notion/sync #bios/copaw #bios/copaw/action #bios/notion #bios/notion/sync #bios/copaw #bios/copaw/action

---

## Troubleshooting

### Webhook Delivery Failed

**Check the response code:**
- `401` - Secret mismatch. Verify the secret matches.
- `400` - Invalid payload. Check content type is `application/json`.
- `500` - Worker error. Check Cloudflare Worker logs.    #bios/mcp_server #bios/mcp_server/auth #bios/meta #bios/meta/operational #bios/mcp_server #bios/mcp_server/auth #bios/meta #bios/meta/operational

### Notion Entry Not Created

**Check:**
1. Worker logs in Cloudflare Dashboard
2. Notion integration has access to the database
3. Database ID is correct in wrangler.toml #bios/architecture #bios/architecture/config #bios/notion #bios/notion/sync #bios/meta #bios/meta/operational #bios/architecture #bios/architecture/config #bios/notion #bios/notion/sync #bios/meta #bios/meta/operational

**To re-share database with integration:**
1. Open Notion database
2. Click `...` → `Connect to`
3. Select your integration

### Secret Rotation

If you need to rotate the webhook secret:

```bash
# Generate new secret
openssl rand -hex 32

# Update Azure Key Vault
az keyvault secret set --vault-name arca-mcp-kv-dae --name github-webhook-secret --value "NEW_SECRET"

# Update Cloudflare
cd ~/biomimetics/cloudflare
echo "NEW_SECRET" | npx wrangler secret put GITHUB_WEBHOOK_SECRET

# Update GitHub webhook settings with new secret
```

---

## Environment Variables

| Variable | Type | Description |
|----------|------|-------------|
| `NOTION_API_KEY` | Secret | Notion integration token |
| `NOTION_DB_ID` | Variable | Biomimetic OS database ID |
| `LIFE_OS_TRIAGE_DB_ID` | Variable | Life OS Triage database ID |
| `TOOL_GUARD_DB_ID` | Variable | Tool Guard database ID |
| `GCP_GATEWAY` | Variable | GCP Memory System endpoint URL |
| `COPAW_APPROVAL_DB_ID` | Variable | CoPaw Approvals database ID |
| `GITHUB_WEBHOOK_SECRET` | Secret | Webhook signature validation | #bios/architecture #bios/architecture/config #bios/notion #bios/notion/schema #bios/copaw #bios/copaw/workflow #bios/architecture #bios/architecture/config #bios/notion #bios/notion/schema #bios/copaw #bios/copaw/workflow

---

## Worker Capabilities

| Event Type | Actions Handled | Notion Fields Populated | Additional Integrations |
|------------|-----------------|------------------------|-------------------------|
| **Issues** | opened, labeled, closed | Name, Status, Source, Github Link, Description, Memory_UUID, Timestamp, Labels | Forwards to GCP memory system |
| **Pull Requests** | opened, closed, reopened | Name, Status, Source, Github Link, Description, Memory_UUID, Timestamp | Forwards to GCP memory system |
| **Push** | refs/heads/main, master, develop | Name, Status, Source, Github Link, Description (commit summary), Memory_UUID, Timestamp | Forwards to GCP memory system | #bios/notion #bios/notion/sync #bios/copaw #bios/copaw/trigger #bios/copaw/action #bios/notion #bios/notion/sync #bios/copaw #bios/copaw/trigger #bios/copaw/action

---

## Special Labels

The worker recognizes these labels for special handling:

| Label | Effect |
|-------|--------|
| `Serena` | Prefixes title with `[SERENA]` in Notion |
| `AI-Agent` | Same as Serena - marks as AI agent task | #bios/notion #bios/notion/schema #bios/personal_assistant #bios/personal_assistant/task #bios/notion #bios/notion/schema #bios/personal_assistant #bios/personal_assistant/task

---

## Support

- **Worker Logs**: Cloudflare Dashboard → Workers → arca-github-notion-sync → Logs
- **GitHub Deliveries**: Repository Settings → Webhooks → Recent Deliveries
- **Notion Database**: Check "Biomimetic OS" database for new entries #bios/meta #bios/meta/operational #bios/notion #bios/notion/sync #bios/meta #bios/meta/operational #bios/notion #bios/notion/sync

<!-- LLM_TAGGED -->