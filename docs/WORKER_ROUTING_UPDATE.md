# Worker Routing Logic Update

## Deployment Complete ✓

**Worker URL**: `https://arca-github-notion-sync.dan-exall.workers.dev`

**Version ID**: `3e3ce929-f238-44db-8d5f-3effef2e7318` (Updated with GCP Memory & CoPaw Integration)

---

## New Routing Logic Code Block

```javascript
// =========================================================
// HEADER EXTRACTION
// =========================================================
const arcaSource = request.headers.get("X-Arca-Source");
const userAgent = request.headers.get("User-Agent");
const actionType = request.headers.get("X-Serena-Action");

// GitHub webhook headers
const githubEvent = request.headers.get("X-GitHub-Event");
const githubSignature = request.headers.get("X-Hub-Signature-256");
const githubDelivery = request.headers.get("X-GitHub-Delivery");

// Log request info
console.log(`Request received - X-Arca-Source: ${arcaSource}, User-Agent: ${userAgent}, X-Serena-Action: ${actionType}, GitHub-Event: ${githubEvent}`);

// =========================================================
// ROUTING LOGIC
// =========================================================

// Route 1: X-Arca-Source header takes priority
if (arcaSource) {
  console.log(`Routing via X-Arca-Source: ${arcaSource}`);

  switch (arcaSource) {
    case 'GitHub':
      return await routeGitHubRequest(request, env);
    case 'Serena':
      return await routeSerenaRequest(request, env);
    case 'GCP-Memory':
      return await routeGcpMemoryInsight(request, env);
    case 'CoPaw':
      return await routeCoPawRequest(request, env);
    default:
      return new Response(`Unknown X-Arca-Source: ${arcaSource}. Use 'GitHub', 'Serena', 'GCP-Memory', or 'CoPaw'.`, {
        status: 400,
        headers: { "Content-Type": "text/plain" }
      });
  }
}

// Route 2: GitHub Webhook (detected by User-Agent)
if (userAgent && userAgent.includes("GitHub-Hookshot")) {
  console.log("Routing: GitHub Webhook detected (User-Agent)");
  return await routeGitHubRequest(request, env);
}

// Route 3: Serena Agent Task (detected by X-Serena-Action header)
if (actionType) {
  console.log(`Routing: Serena Agent action - ${actionType}`);
  return await routeSerenaRequest(request, env);
}

// Route 4: Legacy GitHub event routing (fallback)
if (githubEvent) {
  console.log(`Routing: Legacy GitHub event - ${githubEvent}`);
  return await routeGitHubRequest(request, env);
}

// Default: No recognized headers - reject request
console.log("Request rejected: No recognized headers");
return new Response("Forbidden: No recognized request type. Use X-Arca-Source header (GitHub|Serena|GCP-Memory|CoPaw), GitHub webhook, or X-Serena-Action header.", {
  status: 403,
  headers: { "Content-Type": "text/plain" }
});
```

---

## Routing Decision Tree

```
POST Request Received
        │
        ▼
┌───────────────────────┐
│  Extract Headers:     │
│  - User-Agent         │
│  - X-Serena-Action    │
│  - X-GitHub-Event     │
└──────────┬────────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌─────────────────┐  ┌─────────────────┐
│ User-Agent      │  │ X-Serena-Action │
│ contains        │  │ present?        │
│ "GitHub-Hook"?  │  │                 │
└────┬────────────┘  └────┬────────────┘
     │                    │
  YES│                    │YES
     ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│ handleGitHub    │  │ handleSerena    │
│ Webhook()       │  │ Task()          │
│                 │  │                 │
│ - Verify sig    │  │ - SYNC_TASK     │
│ - Parse payload │  │ - UPDATE_STATUS │
│ - Route by type │  │ - CREATE_ENTRY  │
└─────────────────┘  │ - QUERY         │
                     └─────────────────┘
           │
           ▼
    ┌──────────────┐
    │ X-GitHub-    │
    │ Event        │
    │ present?     │
    └────┬─────────┘
         │
      YES│
         ▼
    ┌─────────────────┐
    │ handleGitHub    │
    │ Webhook()       │
    │ (legacy path)   │
    └─────────────────┘
         │
      NO │
         ▼
    ┌─────────────────┐
    │ RETURN 403      │
    │ Forbidden       │
    └─────────────────┘
```

---

## Serena Agent Action Types

| Action Type | Function | Description |
|-------------|----------|-------------|
| `SYNC_TASK` | `syncTask()` | Create/update task in Notion |
| `UPDATE_STATUS` | `updateTaskStatus()` | Update task status |
| `CREATE_ENTRY` | `createDatabaseEntry()` | Create generic entry |
| `QUERY` | `queryDatabase()` | Query Notion database |

---

## Environment Variables

| Variable | Type | Description |
|----------|------|-------------|
| `NOTION_API_KEY` | Secret | Notion integration token |
| `NOTION_TOKEN` | Secret | Alias for NOTION_API_KEY |
| `NOTION_DB_ID` | Variable | Biomimetic OS database ID |
| `BIOMIMETIC_DB_ID` | Variable | Alias for NOTION_DB_ID |
| `LIFE_OS_TRIAGE_DB_ID` | Variable | Life OS Triage database ID |
| `TOOL_GUARD_DB_ID` | Variable | Tool Guard database ID |
| `GCP_GATEWAY` | Variable | GCP Memory System endpoint URL |
| `COPAW_APPROVAL_DB_ID` | Variable | CoPaw Approvals database ID |
| `GITHUB_WEBHOOK_SECRET` | Secret | Webhook signature validation |

---

## Usage Examples

### GitHub Webhook (Automatic)

```bash
# GitHub sends automatically when webhook is configured
# User-Agent: GitHub-Hookshot/abc123
# X-GitHub-Event: issues
# X-Hub-Signature-256: sha256=...
```

### Serena Agent Task

```bash
curl -X POST https://arca-github-notion-sync.dan-exall.workers.dev \
  -H "Content-Type: application/json" \
  -H "X-Serena-Action: SYNC_TASK" \
  -d '{
    "task_id": "task-001",
    "title": "My Task",
    "description": "Task description",
    "status": "In Progress",
    "source": "Serena Agent",
    "metadata": {
      "labels": ["urgent", "ai-agent"],
      "priority": "high"
    }
  }'
```

### Query Database

```bash
curl -X POST https://arca-github-notion-sync.dan-exall.workers.dev \
  -H "Content-Type: application/json" \
  -H "X-Serena-Action: QUERY" \
  -d '{
    "filter": {
      "property": "Status",
      "status": { "equals": "In Progress" }
    },
    "page_size": 10
  }'
```

---

## Security

- **403 Forbidden**: Returned for requests without recognized headers
- **401 Unauthorized**: Returned for invalid webhook signatures
- **Signature Verification**: All GitHub webhooks are verified against `GITHUB_WEBHOOK_SECRET`

---

## Files Modified

| File | Changes |
|------|---------|
| `cloudflare/index.js` | Added X-Arca-Source routing, GCP memory integration, CoPaw tool approval workflow |
| `cloudflare/wrangler.toml` | Added LIFE_OS_TRIAGE_DB_ID, TOOL_GUARD_DB_ID, GCP_GATEWAY, COPAW_APPROVAL_DB_ID variables |
