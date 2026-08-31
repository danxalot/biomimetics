# Custom Domain Setup Guide

## Domain: `arca-vsa.tech`

Your Worker will be available at: **`https://notion.arca-vsa.tech`**

---

## Prerequisites

1. **Cloudflare Account**: Your domain `arca-vsa.tech` must be managed by Cloudflare
2. **DNS Configured**: Domain nameservers should point to Cloudflare

---

## Deployment Steps

### 1. Install Dependencies
```bash
cd /Users/danexall/Documents/VS Code Projects/ARCA/services/notion-event-router
npm install
```

### 2. Set Cloudflare Secrets
```bash
./scripts/set-cloudflare-secrets.sh
```

This will set:
- `CLOUDFLARE_API_TOKEN` (from .secrets/cloudflare)
- `GITHUB_PAT` (from .secrets/github_token)
- `GCP_SERVICE_ACCOUNT_JSON` (from .secrets/gcp_credentials.json)
- `NOTION_WEBHOOK_SECRET` (auto-generated)

### 3. Deploy to Production
```bash
npm run deploy:prod
```

### 4. Configure Custom Domain in Cloudflare Dashboard

After deployment:

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Navigate to **Workers & Pages** → **notion-event-router**
3. Click **Custom Domains** tab
4. Click **Add Custom Domain**
5. Enter: `notion.arca-vsa.tech`
6. Click **Add Domain**

Cloudflare will automatically:
- Create the DNS record
- Provision SSL certificate
- Route traffic to your Worker

### 5. Verify DNS (if needed)

If the domain doesn't resolve immediately, add a CNAME record:

```
Type: CNAME
Name: notion
Target: notion-event-router.<your-subdomain>.workers.dev
Proxy: Enabled (orange cloud)
```

---

## Test Your Endpoint

```bash
curl -X POST https://notion.arca-vsa.tech \
  -H "Content-Type: application/json" \
  -H "X-Notion-Signature: sha256=test" \
  -d '{
    "event": {
      "id": "test-123",
      "created_time": "2024-01-01T00:00:00.000Z",
      "properties": {
        "title": [{"plain_text": "Test ARCA Task"}],
        "Tags": {"multi_select": [{"name": "ARCA"}]},
        "Description": {"rich_text": [{"plain_text": "Testing with custom domain"}]}
      }
    }
  }'
```

Expected response:
```json
{
  "success": true,
  "message": "Event received and processing",
  "notion_id": "test-123"
}
```

---

## Configure Notion Webhook

1. In Notion, go to your database
2. Click **...** → **Connections** → **Add connection**
3. Search for your webhook service (or use direct URL if supported)
4. Set webhook URL to: `https://notion.arca-vsa.tech`
5. Set signing secret to the value shown after running `set-cloudflare-secrets.sh`

**Note**: Notion may require a webhook relay service. Options:
- **Hookdeck**: Free tier available
- **Smee.io**: Free webhook relay
- **Direct**: If Notion supports direct webhooks

---

## SSL/TLS

Cloudflare automatically provisions SSL for custom domains. Your endpoint will have:
- ✅ HTTPS enabled
- ✅ Automatic certificate renewal
- ✅ TLS 1.3 support

---

## Monitoring

### View Logs
```bash
wrangler tail --env production
```

### Cloudflare Analytics
1. Go to Workers & Pages → notion-event-router
2. Click **Analytics** tab
3. View requests, errors, and performance

---

## Troubleshooting

### Domain not resolving
```bash
# Check DNS propagation
dig notion.arca-vsa.tech

# Should show Cloudflare nameservers
```

### SSL certificate pending
- Wait up to 24 hours for certificate provisioning
- Ensure domain is properly added to Cloudflare

### 401 Unauthorized
- Verify `X-Notion-Signature` header matches secret
- Check NOTION_WEBHOOK_SECRET in Cloudflare Secrets

---

## Your Custom Domain Details

| Setting | Value |
|---------|-------|
| **Domain** | `notion.arca-vsa.tech` |
| **Worker Name** | `notion-event-router` |
| **Environment** | `production` |
| **SSL** | Automatic (Cloudflare) |
| **DNS** | Managed by Cloudflare |

---

## Next Steps

After custom domain is working:
1. ✅ Test with curl
2. ✅ Configure Notion webhook
3. ✅ Create test task with ARCA tag
4. ✅ Verify GitHub issue created
5. ✅ Verify Pub/Sub message published

**Phase 1 Complete** when end-to-end flow works!
