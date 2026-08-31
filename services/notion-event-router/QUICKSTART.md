# Phase 1: Quick Start Guide

## 🚀 5-Minute Setup (If you have all credentials ready)

### 1. Install & Configure
```bash
cd services/notion-event-router
npm install
```

### 2. Setup GCP (Automated)
```bash
export GCP_PROJECT_ID=your-project-id
chmod +x scripts/setup-gcp.sh
./scripts/setup-gcp.sh
```

This creates:
- Service Account
- Pub/Sub Topic (`os-events`)
- Pub/Sub Subscription
- Service Account JSON key

### 3. Configure Worker
Edit `wrangler.toml`:
```toml
GCP_PROJECT_ID = "your-actual-project-id"
GITHUB_OWNER = "your-github-username"
GITHUB_REPO = "your-repo-name"
```

### 4. Set Secrets
```bash
# GitHub PAT (create at github.com/settings/tokens)
wrangler secret put GITHUB_PAT

# GCP Service Account (content from service-account.json)
wrangler secret put GCP_SERVICE_ACCOUNT_JSON

# Notion Secret (generate random string)
wrangler secret put NOTION_WEBHOOK_SECRET
```

### 5. Deploy
```bash
npm run deploy
```

### 6. Test
```bash
curl -X POST https://notion-event-router.<your-subdomain>.workers.dev \
  -H "Content-Type: application/json" \
  -H "X-Notion-Signature: sha256=test" \
  -d '{
    "event": {
      "id": "test-123",
      "created_time": "2024-01-01T00:00:00.000Z",
      "properties": {
        "title": [{"plain_text": "Test ARCA Task"}],
        "Tags": {"multi_select": [{"name": "ARCA"}]},
        "Description": {"rich_text": [{"plain_text": "Testing Phase 1"}]}
      }
    }
  }'
```

### 7. Verify
- **GitHub**: Check for new issue in your repo
- **GCP**: `gcloud pubsub subscriptions pull os-events-sub --auto-ack`

---

## 📋 Credentials Checklist

Before starting, gather:

| Credential | Where to Get | Format |
|------------|--------------|--------|
| `GCP_PROJECT_ID` | GCP Console | `my-project-123` |
| `GITHUB_PAT` | github.com/settings/tokens | `ghp_xxxxx` |
| `GITHUB_OWNER` | Your GitHub username | `username` |
| `GITHUB_REPO` | Target repo name | `repo-name` |
| `NOTION_WEBHOOK_SECRET` | Generate random string | `random-string` |

### Generate Notion Secret
```bash
# macOS/Linux
openssl rand -hex 32

# Or use Python
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 🔧 Local Development

```bash
# Start dev server
npm run dev

# In another terminal, test with curl
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -d '{"event": {"id": "test", "properties": {"title": [{"plain_text": "Test"}]}}}'
```

---

## ✅ Phase 1 Completion Checklist

- [ ] Worker deployed to Cloudflare
- [ ] GCP Service Account created
- [ ] Pub/Sub topic `os-events` exists
- [ ] GitHub PAT configured
- [ ] Test event creates GitHub issue
- [ ] Test event publishes to Pub/Sub
- [ ] Monitoring/logs visible in Cloudflare Dashboard

**Phase 1 Complete** when: Notion task → GitHub issue + Pub/Sub event

---

## 🆘 Troubleshooting

### 401 Unauthorized
```bash
# Check signature matches
wrangler secret put NOTION_WEBHOOK_SECRET
```

### GitHub issue not created
```bash
# Verify PAT has repo scope
# Check wrangler logs
wrangler tail
```

### Pub/Sub error
```bash
# Verify service account has publisher role
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --format="table(bindings.role)" \
  --filter="bindings.members:serviceAccount:SERVICE_ACCOUNT"
```

---

## 📞 Need Help?

1. Check Cloudflare Worker logs: https://dash.cloudflare.com
2. Check GCP Pub/Sub: https://console.cloud.google.com/cloudpubsub
3. Review error messages in Worker tail: `wrangler tail`
