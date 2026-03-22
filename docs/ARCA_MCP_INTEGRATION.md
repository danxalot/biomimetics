# ARCA Project MCP Integration Guide

**Date**: 2026-03-19  
**Status**: Ready for Implementation  
**Projects**: Biomimetics + ARCA

---

## Overview

This guide covers the integration of the **ARCA project** with the existing MCP infrastructure established in Biomimetics, including:

- **GitHub MCP Server** (Azure SSE)
- **Notion MCP Server** (GCP)
- **GCP Memory Gateway** (Cloud Functions)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARCA PROJECT ECOSYSTEM                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │  Zed Editor │     │Antigravity  │     │   CoPaw     │       │
│  │             │     │             │     │             │       │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘       │
│         │                   │                   │               │
│         └───────────────────┼───────────────────┘               │
│                             │                                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              MCP Integration Layer                       │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │  GitHub MCP  │  │  Notion MCP  │  │  GCP Gateway │  │   │
│  │  │  (Azure SSE) │  │  (GCP)       │  │  (Memory)    │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                             │                                   │
│         ┌───────────────────┼───────────────────┐              │
│         │                   │                   │              │
│         ▼                   ▼                   ▼              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │  GitHub     │    │   Notion    │    │  GCP Cloud  │        │
│  │  API        │    │   Databases │    │  Functions  │        │
│  └─────────────┘    └─────────────┘    └─────────────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### 1. Azure Resources

- **GitHub MCP Container**: Running on Azure ACI
- **Endpoint**: `http://github-mcp-sse.westus2.azurecontainer.io:8080/sse`
- **Resource Group**: `arca-mcp-services`

**Verify**:
```bash
az container show -g arca-mcp-services -n github-mcp-sse
```

### 2. GCP Resources

- **Memory Orchestrator**: Cloud Function deployed
- **Endpoint**: `https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator`
- **Project**: `arca-471022`

**Verify**:
```bash
gcloud functions describe memory-orchestrator --region us-central1
```

### 3. Notion Resources

- **Notion Integration Token**: Available in Azure Key Vault
- **Databases**: Create ARCA-specific databases (see below)

**Verify**:
```bash
az keyvault secret show --vault-name arca-mcp-kv-dae --name notion-api-key
```

---

## Step 1: Create ARCA Notion Databases

### Database Schema

Create the following databases in Notion:

#### 1. ARCA Projects Database

**Properties**:
- `Name` (Title)
- `Status` (Status: Not Started, In Progress, On Hold, Complete)
- `Priority` (Select: Critical, High, Medium, Low)
- `Description` (Text)
- `Github Link` (URL)
- `Team` (Multi-select)
- `Start Date` (Date)
- `Due Date` (Date)

#### 2. ARCA Tasks Database

**Properties**:
- `Name` (Title)
- `Status` (Status: Not Started, In Progress, Review, Done)
- `Project` (Relation → ARCA Projects)
- `Assignee` (People)
- `Priority` (Select: Critical, High, Medium, Low)
- `Description` (Text)
- `Github Issue` (URL)
- `Due Date` (Date)

#### 3. ARCA Memory Logs Database

**Properties**:
- `Name` (Title)
- `Timestamp` (Date)
- `Type` (Select: Query, Update, Insight, Event)
- `Source` (Select: ARCA, Biomimetics, GitHub, Serena)
- `Content` (Text)
- `Memory UUID` (Text)

### Share Databases with Integration

1. Open each database in Notion
2. Click `...` → `Connect to`
3. Select your Notion integration
4. Copy database IDs for configuration

---

## Step 2: Update Cloudflare Worker

Add ARCA project routing to `cloudflare/index.js`:

```javascript
// Add to X-Arca-Source routing switch
case 'ARCA':
  return await routeArcaRequest(request, env);
```

### Implementation

```javascript
/**
 * Route ARCA project requests
 */
async function routeArcaRequest(request, env) {
  const method = request.method;
  const url = new URL(request.url);
  
  // Get ARCA-specific database IDs from environment
  const arcaProjectsDbId = env.ARCA_PROJECTS_DB_ID;
  const arcaTasksDbId = env.ARCA_TASKS_DB_ID;
  const arcaMemoryDbId = env.ARCA_MEMORY_DB_ID;
  const notionToken = env.NOTION_TOKEN || env.NOTION_API_KEY;
  
  if (!arcaProjectsDbId || !notionToken) {
    return new Response("Missing ARCA database configuration", { status: 500 });
  }
  
  // Handle GET requests (queries)
  if (method === "GET") {
    const database = url.searchParams.get("database") || "projects";
    const filter = url.searchParams.get("filter");
    
    let databaseId = arcaProjectsDbId;
    if (database === "tasks") {
      databaseId = arcaTasksDbId;
    } else if (database === "memory") {
      databaseId = arcaMemoryDbId;
    }
    
    const queryData = {
      database_id: databaseId,
      filter: filter ? JSON.parse(filter) : {},
      page_size: 10
    };
    
    try {
      const response = await fetch("https://api.notion.com/v1/databases/query", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${notionToken}`,
          "Content-Type": "application/json",
          "Notion-Version": "2022-06-28"
        },
        body: JSON.stringify(queryData)
      });
      
      const result = await response.json();
      
      return new Response(JSON.stringify({
        success: true,
        database: database,
        results: result.results.length,
        data: result.results
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
      
    } catch (error) {
      return new Response(`Query Error: ${error.message}`, { status: 500 });
    }
  }
  
  // Handle POST requests (create/update)
  if (method === "POST") {
    let payload;
    try {
      payload = await request.json();
    } catch (e) {
      return new Response("Invalid JSON payload", { status: 400 });
    }
    
    const action = payload.action || "CREATE";
    
    if (action === "CREATE") {
      return await createArcaEntry(payload, env, arcaProjectsDbId, notionToken);
    } else if (action === "UPDATE") {
      return await updateArcaEntry(payload, env, notionToken);
    } else if (action === "LOG_MEMORY") {
      return await logArcaMemory(payload, env, arcaMemoryDbId, notionToken);
    }
    
    return new Response(`Unknown action: ${action}`, { status: 400 });
  }
  
  return new Response("Method not allowed", { status: 405 });
}

/**
 * Create ARCA database entry
 */
async function createArcaEntry(payload, env, databaseId, notionToken) {
  const { name, properties = {} } = payload;
  
  const notionData = {
    parent: { database_id: databaseId },
    properties: {
      "Name": {
        title: [{ text: { content: name || "Untitled Entry" } }]
      },
      ...properties
    }
  };
  
  try {
    const response = await fetch("https://api.notion.com/v1/pages", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${notionToken}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(notionData)
    });
    
    const result = await response.json();
    
    // Forward to GCP memory
    await forwardToGcpMemory({
      type: "arca-entry-created",
      entry: { name, properties },
      notionPageId: result.id
    }, env);
    
    return new Response(JSON.stringify({
      success: true,
      notion_page_id: result.id,
      action: "CREATE"
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
    
  } catch (error) {
    return new Response(`Create Error: ${error.message}`, { status: 500 });
  }
}

/**
 * Update ARCA database entry
 */
async function updateArcaEntry(payload, env, notionToken) {
  const { page_id, properties } = payload;
  
  if (!page_id) {
    return new Response("Missing page_id", { status: 400 });
  }
  
  const notionData = { properties };
  
  try {
    const response = await fetch(`https://api.notion.com/v1/pages/${page_id}`, {
      method: "PATCH",
      headers: {
        "Authorization": `Bearer ${notionToken}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(notionData)
    });
    
    const result = await response.json();
    
    return new Response(JSON.stringify({
      success: true,
      notion_page_id: result.id,
      action: "UPDATE"
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
    
  } catch (error) {
    return new Response(`Update Error: ${error.message}`, { status: 500 });
  }
}

/**
 * Log ARCA memory event
 */
async function logArcaMemory(payload, env, databaseId, notionToken) {
  const { event_type, content, memory_uuid } = payload;
  
  const notionData = {
    parent: { database_id: databaseId },
    properties: {
      "Name": {
        title: [{ text: { content: `ARCA: ${event_type}` } }]
      },
      "Timestamp": {
        date: { start: new Date().toISOString() }
      },
      "Type": {
        select: { name: "Event" }
      },
      "Source": {
        select: { name: "ARCA" }
      },
      "Content": {
        rich_text: [{ text: { content: content } }]
      },
      "Memory UUID": {
        rich_text: [{ text: { content: memory_uuid || generateUUID() } }]
      }
    }
  };
  
  try {
    const response = await fetch("https://api.notion.com/v1/pages", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${notionToken}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(notionData)
    });
    
    const result = await response.json();
    
    return new Response(JSON.stringify({
      success: true,
      notion_page_id: result.id,
      action: "LOG_MEMORY"
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
    
  } catch (error) {
    return new Response(`Log Error: ${error.message}`, { status: 500 });
  }
}
```

---

## Step 3: Update Wrangler Configuration

Add ARCA database IDs to `cloudflare/wrangler.toml`:

```toml
[vars]
# Existing vars
NOTION_DB_ID = "3224d2d9fc7c80deb18dd94e22e5bb21"
BIOMIMETIC_DB_ID = "3224d2d9fc7c80deb18dd94e22e5bb21"
LIFE_OS_TRIAGE_DB_ID = "3254d2d9fc7c81228daefc564e912546"
TOOL_GUARD_DB_ID = "3254d2d9fc7c81228daefc564e912546"
GCP_GATEWAY = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"

# ARCA Project vars
ARCA_PROJECTS_DB_ID = "your-arca-projects-db-id"
ARCA_TASKS_DB_ID = "your-arca-tasks-db-id"
ARCA_MEMORY_DB_ID = "your-arca-memory-db-id"
```

---

## Step 4: Configure Zed for ARCA

Update `~/.zed/settings.json`:

```json
{
  "mcp_servers": {
    "notion": { ... },
    "github": { ... }
  },
  "agent_servers": {
    "BiOS_PM": { ... },
    "ARCA_PM": {
      "type": "custom",
      "command": "python3",
      "args": ["~/.copaw/arca_orchestrator.py"],
      "env": {
        "NOTION_DB_ID": "your-arca-projects-db-id",
        "GCP_GATEWAY": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
        "ARCA_PROJECTS_DB_ID": "your-arca-projects-db-id",
        "ARCA_TASKS_DB_ID": "your-arca-tasks-db-id"
      }
    }
  },
  "gcp_gateway": {
    "url": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
    "enabled": true,
    "projects": ["biomimetics", "arca"]
  }
}
```

---

## Step 5: Configure Antigravity for ARCA

Update `~/.antigravity/settings.json`:

```json
{
  "mcp_servers": {
    "notion": { ... },
    "github": { ... }
  },
  "gcp_gateway": {
    "url": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
    "enabled": true,
    "projects": ["biomimetics", "arca"],
    "arca_namespaces": {
      "projects": "your-arca-projects-db-id",
      "tasks": "your-arca-tasks-db-id",
      "memory": "your-arca-memory-db-id"
    }
  }
}
```

---

## Step 6: Test Integration

### Test GitHub MCP

```bash
# In Zed or Antigravity, use GitHub MCP tools
github.list_pull_requests
github.search_issues
```

### Test Notion MCP (ARCA Databases)

```bash
# Query ARCA Projects database
curl -X POST https://api.notion.com/v1/databases/query \
  -H "Authorization: Bearer $NOTION_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Notion-Version: 2022-06-28" \
  -d '{"database_id": "your-arca-projects-db-id"}'
```

### Test GCP Gateway

```bash
# Send memory event
curl -X POST https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator \
  -H "Content-Type: application/json" \
  -d '{
    "action": "store",
    "project": "arca",
    "data": {"test": "ARCA integration"}
  }'
```

### Test Cloudflare Worker

```bash
# Query ARCA databases via worker
curl -X GET "https://arca-github-notion-sync.dan-exall.workers.dev?database=projects" \
  -H "X-Arca-Source: ARCA"
```

---

## Cross-Project Integration

### Biomimetics ↔ ARCA Data Flow

```
┌─────────────────┐         ┌─────────────────┐
│  Biomimetics    │         │  ARCA Project   │
│  Databases      │         │  Databases      │
│                 │         │                 │
│ ┌─────────────┐ │         │ ┌─────────────┐ │
│ │ Projects    │ │         │ │ Projects    │ │
│ │ Tasks       │ │         │ │ Tasks       │ │
│ │ Memory      │ │         │ │ Memory      │ │
│ └─────────────┘ │         │ └─────────────┘ │
└────────┬────────┘         └────────┬────────┘
         │                           │
         │         ┌─────────────────┘
         │         │
         ▼         ▼
    ┌─────────────────────────┐
    │   GCP Memory Gateway    │
    │   (Unified Context)     │
    └─────────────────────────┘
```

### Shared Memory Namespace

Both projects share the GCP Memory Gateway with project-specific namespaces:

- `biomimetics:*` - Biomimetics project data
- `arca:*` - ARCA project data
- `shared:*` - Cross-project context

---

## Troubleshooting

### ARCA Databases Not Accessible

1. Check database sharing in Notion
2. Verify database IDs in config
3. Test Notion token permissions

### GCP Gateway Returns Errors

1. Check Cloud Function logs
2. Verify service account permissions
3. Test endpoint directly with curl

### GitHub MCP Connection Fails

1. Check Azure container status
2. Verify SSE endpoint URL
3. Check network/firewall rules

---

## Next Steps

1. ✅ Create ARCA Notion databases
2. ✅ Update Cloudflare Worker code
3. ✅ Update wrangler.toml configuration
4. ✅ Configure Zed Editor
5. ✅ Configure Antigravity
6. ✅ Test all integrations
7. ✅ Document cross-project workflows

---

**Contact**: Claws <claws@arca-vsa.tech>  
**Documentation**: `docs/MCP_INTEGRATION_STATUS.md`  
**Repository**: https://github.com/danxalot/biomimetics
