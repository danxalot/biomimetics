# X-Arca-Source Routing Implementation

## Deployment Complete ✓

**Worker URL**: `https://arca-github-notion-sync.dan-exall.workers.dev`

**Version ID**: `2e652434-9338-4da9-b384-48b37b3b73af`

**URL Status**: ✅ **UNCHANGED** - No need to update GitHub webhook settings!

---

## New Routing Logic

### Header-Based Routing (Priority)

```javascript
// Extract X-Arca-Source header
const arcaSource = request.headers.get("X-Arca-Source");

if (arcaSource) {
  switch (arcaSource) {
    case 'GitHub':
      return await routeGitHubRequest(request, env);
    case 'Serena':
      return await routeSerenaRequest(request, env);
    default:
      return new Response(`Unknown X-Arca-Source: ${arcaSource}`);
  }
}
```

### Routing Decision Tree

```
Request Received
      │
      ▼
┌─────────────────────┐
│ X-Arca-Source       │
│ header present?     │
└────┬────────────────┘
     │
  YES│────────────────┐
     │                │
     ▼                ▼
┌─────────┐    ┌──────────┐
│ GitHub  │    │ Serena   │
└────┬────┘    └────┬─────┘
     │              │
     ▼              ▼
┌─────────────┐ ┌──────────────┐
│ Biomimetic  │ │ GET/POST to  │
│ OS Database │ │ Life OS &    │
│ (Issues,    │ │ Biomimetic   │
│ PRs, Push)  │ │ databases    │
└─────────────┘ └──────────────┘
     │
  NO │ (fallback to legacy detection)
     ▼
┌─────────────────────┐
│ User-Agent contains │
│ "GitHub-Hookshot"?  │
└────┬────────────────┘
     │
  YES│
     ▼
┌─────────────┐
│ GitHub      │
│ Webhook     │
└─────────────┘
```

---

## Database Configuration

| Database | ID | Used By |
|----------|-----|---------|
| **Biomimetic OS** | `3244d2d9fc7c808b97c3ce78648d77a1` | GitHub webhooks, Serena default |
| **Life OS Triage** | (from env `LIFE_OS_TRIAGE_DB_ID`) | Serena when `database: "life-os"` |

---

## Usage Examples

### GitHub Webhook (Automatic)

GitHub sends requests automatically with:
- `User-Agent: GitHub-Hookshot/abc123`
- `X-GitHub-Event: issues`
- `X-Hub-Signature-256: sha256=...`

**No changes needed** - existing webhook continues to work!

### Serena Agent - POST to Biomimetic OS

```bash
curl -X POST https://arca-github-notion-sync.dan-exall.workers.dev \
  -H "Content-Type: application/json" \
  -H "X-Arca-Source: Serena" \
  -H "X-Serena-Action: SYNC_TASK" \
  -d '{
    "task_id": "task-001",
    "title": "My Task",
    "description": "Task description",
    "status": "In Progress",
    "database": "biomimetic"
  }'
```

### Serena Agent - POST to Life OS Triage

```bash
curl -X POST https://arca-github-notion-sync.dan-exall.workers.dev \
  -H "Content-Type: application/json" \
  -H "X-Arca-Source: Serena" \
  -H "X-Serena-Action: SYNC_TASK" \
  -d '{
    "task_id": "triage-001",
    "title": "Triage Entry",
    "description": "Needs review",
    "database": "life-os"
  }'
```

### Serena Agent - GET Query

```bash
# Query Biomimetic OS
curl -X GET "https://arca-github-notion-sync.dan-exall.workers.dev?database=biomimetic&filter={\"property\":\"Status\",\"status\":{\"equals\":\"In Progress\"}}" \
  -H "X-Arca-Source: Serena"

# Query Life OS Triage
curl -X GET "https://arca-github-notion-sync.dan-exall.workers.dev?database=life-os" \
  -H "X-Arca-Source: Serena"
```

---

## Environment Variables

| Variable | Type | Value |
|----------|------|-------|
| `NOTION_DB_ID` | Variable | `3244d2d9fc7c808b97c3ce78648d77a1` |
| `BIOMIMETIC_DB_ID` | Variable | `3244d2d9fc7c808b97c3ce78648d77a1` |
| `LIFE_OS_TRIAGE_DB_ID` | Variable | (set via `wrangler secret put`) |
| `NOTION_API_KEY` | Secret | Notion integration token |
| `NOTION_TOKEN` | Secret | Alias for NOTION_API_KEY |
| `GITHUB_WEBHOOK_SECRET` | Secret | Webhook validation |

---

## Routing Summary

| X-Arca-Source | Method | Action | Target Database |
|---------------|--------|--------|-----------------|
| `GitHub` | POST | Webhook (issues, PRs, push) | Biomimetic OS |
| `Serena` | POST | SYNC_TASK | Biomimetic OS (default) or Life OS |
| `Serena` | POST | UPDATE_STATUS | Biomimetic OS (default) or Life OS |
| `Serena` | POST | CREATE_ENTRY | Biomimetic OS (default) or Life OS |
| `Serena` | GET | QUERY | Biomimetic OS (default) or Life OS |
| *(none)* | POST | Legacy GitHub webhook | Biomimetic OS |
| *(none)* | POST | X-Serena-Action | Biomimetic OS (default) or Life OS |

---

## Security

- **403 Forbidden**: Requests without recognized headers
- **401 Unauthorized**: Invalid GitHub webhook signature
- **400 Bad Request**: Unknown X-Arca-Source value
- **405 Method Not Allowed**: Non-POST/GET requests

---

## Files Modified

| File | Changes |
|------|---------|
| `cloudflare/index.js` | Added X-Arca-Source routing, routeGitHubRequest(), routeSerenaRequest(), handleSerenaQuery() |
| `cloudflare/wrangler.toml` | Already configured with database IDs |

---

## Verification

The Worker URL remains:
```
https://arca-github-notion-sync.dan-exall.workers.dev
```

**GitHub webhook settings do NOT need to be updated!**
