# MCP Integration Status Report

**Date**: 2026-03-19  
**Project**: Biomimetics (ARCA Ecosystem)  
**Scope**: Zed & Antigravity integration with GitHub MCP (Azure) and Notion MCP (GCP)

---

## Executive Summary

### Current Status (As of 2026-03-19)

| Integration | Biomimetics | ARCA Project | Status |
|-------------|-------------|--------------|--------|
| **Zed Editor** | ✅ Configured | ⚠️ Needs ARCA DBs | **Ready** |
| **Antigravity** | ✅ Configured | ⚠️ Needs ARCA DBs | **Ready** |
| **GitHub MCP (Azure)** | ⚠️ Previously Deployed | ⚠️ Previously Deployed | **Needs Redeployment** |
| **Notion MCP (GCP)** | ✅ Configured | ⚠️ Needs ARCA DBs | **Ready** |
| **GCP Server** | ✅ Active (Memory Gateway) | ⚠️ Shared Access | **Ready** |

### Key Findings

**✅ What's Working**:
- Zed Editor configuration updated with GitHub MCP + Notion MCP + GCP Gateway
- Antigravity configuration created with full MCP integration
- Notion MCP server configured and operational (token: `ntn_2071...`)
- GCP Memory Gateway active and routing
- Cloudflare Worker multi-system integration hub deployed
- Notion databases exist: `3224d2d9fc7c80deb18dd94e22e5bb21` (Biomimetic OS)

**⚠️ What Needs Attention**:
- **GitHub MCP container not running** - Previously deployed to `arca-consolidated` RG, but container was deleted/stopped
- **Azure resources still exist**: Container Registry (`arcamcpconsolidated`), Key Vault (`arca-mcp-kv-dae`)
- **ARCA project Notion databases** - Need to be created or identified
- **Configuration needs endpoint update** - Once GitHub MCP is redeployed

**📋 Azure Resource Status**:
```
Resource Group: arca-consolidated (eastus)
  ✓ Container Registry: arcamcpconsolidated
  ✗ Container Instances: None found (github-mcp-server was deleted)

Resource Group: arca-rg (eastus)
  ✓ Key Vault: arca-mcp-kv-dae (67 secrets including github-token)
  ✓ Key Vault: arca-mcp-kv-dae2 (backup)
```

**🔧 Previous Deployment Info** (from docs):
- **Old SSE Endpoint**: `http://github-mcp-sse.westus2.azurecontainer.io:8080/sse` (not found)
- **Old MCP Endpoint**: `http://github-mcp-server.eastus.azurecontainer.io:8080/mcp` (not found)
- **Deployment Script**: `azure/deploy_github_mcp_eastus.sh` or `azure/deploy_github_mcp_with_keyvault.sh`

---

## Detailed Integration Status

### 1. Zed Editor Integration

#### Current Configuration (`~/.zed/settings.json`)

```json
{
  "agent_servers": {
    "BiOS_PM": {
      "type": "custom",
      "command": "python3",
      "args": ["~/.copaw/bios_orchestrator.py"],
      "env": {
        "NOTION_DB_ID": "3224d2d9fc7c80deb18dd94e22e5bb21",
        "GCP_GATEWAY": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
      }
    }
  },
  "mcp_servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "[NOTION_TOKEN_REDACTED]"
      }
    }
  }
}
```

#### Status: ⚠️ Partial

**✅ Working**:
- Notion MCP server configured
- BiOS_PM agent server configured with GCP Gateway
- Direct Notion access enabled

**❌ Missing**:
- GitHub MCP server not configured in Zed
- No ARCA project-specific configuration
- No GCP server integration for ARCA project

#### Required Actions

1. **Add GitHub MCP (Azure SSE) to Zed**:
```json
{
  "mcp_servers": {
    "notion": { ... },
    "github": {
      "url": "http://github-mcp-sse.westus2.azurecontainer.io:8080/sse",
      "transport": "sse",
      "description": "GitHub MCP via Azure ACI (24/7 remote access)"
    }
  }
}
```

2. **Create ARCA project-specific Zed config**:
   - Link to ARCA project databases
   - Configure ARCA-specific GCP memory access

---

### 2. Antigravity Integration

#### Current Status: ❌ Not Configured

**Directory**: `~/biomimetics/.antigravity/` (empty, 1 git-ignored file)

**Required Configuration** (`~/.antigravity/settings.json`):

```json
{
  "mcp_servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "[NOTION_TOKEN_REDACTED]"
      },
      "tools": [
        "search_notion", "get_page", "create_page",
        "update_page", "query_database"
      ]
    },
    "github": {
      "url": "http://github-mcp-sse.westus2.azurecontainer.io:8080/sse",
      "transport": "sse",
      "tools": [
        "github.create_issue",
        "github.update_issue",
        "github.search_issues",
        "github.get_issue",
        "github.create_pull_request",
        "github.list_pull_requests",
        "github.get_pull_request",
        "github.get_repository"
      ]
    }
  },
  "gcp_gateway": {
    "url": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
    "enabled": true,
    "projects": ["biomimetics", "arca"]
  }
}
```

#### Required Actions

1. Create `~/.antigravity/settings.json` with above configuration
2. Ensure Antigravity has access to both Notion databases
3. Configure GCP Gateway access for both projects

---

### 3. GitHub MCP Server (Azure)

#### Deployment Status: ✅ Deployed (SSE)

**Endpoint**: `http://github-mcp-sse.westus2.azurecontainer.io:8080/sse`

**Configuration** (from `docs/GITHUB_MCP_SSE_DEPLOYMENT.md`):

```json
{
  "mcp_servers": {
    "github-remote": {
      "url": "http://github-mcp-sse.westus2.azurecontainer.io:8080/sse",
      "transport": "sse",
      "description": "GitHub MCP via Azure ACI (24/7 remote access)",
      "restricted_tools": [
        "github.create_issue",
        "github.update_issue",
        "github.search_issues",
        "github.get_issue",
        "github.create_pull_request",
        "github.list_pull_requests",
        "github.get_pull_request",
        "github.get_repository"
      ],
      "require_approval_for": [
        "github.create_issue",
        "github.update_issue",
        "github.create_pull_request"
      ]
    }
  }
}
```

**Azure Resource**:
- **Container**: `github-mcp-sse`
- **Resource Group**: `arca-mcp-services`
- **Location**: westus2
- **CPU**: 2 cores, **Memory**: 2 GB
- **Cost**: ~$35/month

#### Integration Status

| Client | Status | Configured |
|--------|--------|------------|
| **CoPaw** | ✅ Configured | `~/.copaw/config.json` |
| **Zed** | ❌ Not Configured | - |
| **Antigravity** | ❌ Not Configured | - |
| **Biomimetics** | ⚠️ Via Cloudflare Worker | `cloudflare/index.js` |
| **ARCA Project** | ❌ Not Connected | - |

#### Required Actions

1. Add GitHub MCP to Zed config (see section 1)
2. Add GitHub MCP to Antigravity config (see section 2)
3. Configure ARCA project to use same GitHub MCP endpoint
4. Update CoPaw config if endpoint changed

---

### 4. Notion MCP Server (GCP)

#### Status: ✅ Configured for Biomimetics

**Configuration** (from `scripts/setup_notion_mcp.sh`):

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "[NOTION_TOKEN_REDACTED]"
      }
    }
  }
}
```

**Databases Connected**:

| Database | ID | Purpose |
|----------|-----|---------|
| **Biomimetic OS** | `3224d2d9fc7c80deb18dd94e22e5bb21` | Project tracking |
| **Life OS Triage** | `3254d2d9fc7c81228daefc564e912546` | Email/webhook triage |
| **Tool Guard** | `3254d2d9fc7c81228daefc564e912546` | Security & approvals |
| **CoPaw Approval** | `3274d2d9fc7c8161a00cd9995cff5520` | Tool approvals |

#### Integration Status

| Client | Status | Configured |
|--------|--------|------------|
| **Claude Desktop** | ✅ Configured | `~/Library/Application Support/Claude/...` |
| **Qwen Code** | ✅ Configured | `~/.qwen/settings.json` |
| **Zed** | ✅ Configured | `~/.zed/settings.json` |
| **Antigravity** | ❌ Not Configured | - |
| **ARCA Project** | ❌ Not Configured | - |

#### Required Actions

1. Add Notion MCP to Antigravity config
2. Create ARCA project Notion databases (if not existing)
3. Configure ARCA project to use Notion MCP
4. Share databases with Notion integration

---

### 5. GCP Server Integration

#### GCP Memory Gateway

**Endpoint**: `https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator`

**Purpose**: Unified memory system (MuninnDB + MemU) for contextual AI

**Projects Using**:
- ✅ **Biomimetics**: Full integration via Cloudflare Worker
- ⚠️ **ARCA Project**: Shared access, needs dedicated config

#### Architecture

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Zed Editor     │     │                     │     │  GCP Memory      │
│  Antigravity    │────▶│  Cloudflare Worker  │────▶│  Gateway         │
│  CoPaw          │     │  (Routing Layer)    │     │  (Cloud Func)    │
└─────────────────┘     └─────────────────────┘     └──────────────────┘
                                                        │
                                                        ▼
                                               ┌──────────────────┐
                                               │  MuninnDB +      │
                                               │  MemU Storage    │
                                               └──────────────────┘
```

#### Current Integration Points

**Biomimetics** (`cloudflare/wrangler.toml`):
```toml
GCP_GATEWAY = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
```

**Zed** (`~/.zed/settings.json`):
```json
{
  "agent_servers": {
    "BiOS_PM": {
      "env": {
        "GCP_GATEWAY": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
      }
    }
  }
}
```

**Cloudflare Worker** (`cloudflare/index.js`):
- Routes requests via `X-Arca-Source` header
- Supports: GitHub, Serena, GCP-Memory, CoPaw, PM-Agent
- Forwards to GCP Gateway for memory operations

#### Required Actions for ARCA Project

1. **Create ARCA-specific GCP Gateway config**:
```json
{
  "gcp_gateway": {
    "url": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
    "project_id": "arca",
    "memory_namespace": "arca-project",
    "enabled": true
  }
}
```

2. **Update Cloudflare Worker** to support ARCA project routing:
```javascript
case 'ARCA':
  return await routeArcaRequest(request, env);
```

3. **Configure ARCA project databases** in Notion
4. **Test GCP memory access** from ARCA project

---

## Integration Roadmap

### Phase 1: Complete Zed Integration (Priority: High)

**Tasks**:
1. Update `~/.zed/settings.json` with GitHub MCP
2. Test GitHub MCP connection from Zed
3. Test Notion MCP from Zed
4. Verify GCP Gateway access

**Estimated Time**: 30 minutes

**Configuration File**: `~/.zed/settings.json`

---

### Phase 2: Setup Antigravity Integration (Priority: High)

**Tasks**:
1. Create `~/.antigravity/settings.json`
2. Configure Notion MCP server
3. Configure GitHub MCP server (Azure SSE)
4. Configure GCP Gateway access
5. Test all integrations

**Estimated Time**: 45 minutes

**Configuration File**: `~/.antigravity/settings.json`

---

### Phase 3: ARCA Project Integration (Priority: Medium)

**Tasks**:
1. Identify/create ARCA project Notion databases
2. Configure ARCA-specific GCP memory namespace
3. Update Cloudflare Worker for ARCA routing
4. Create ARCA project Zed config
5. Create ARCA project Antigravity config
6. Test end-to-end integration

**Estimated Time**: 2-3 hours

**Configuration Files**:
- `cloudflare/index.js` (update routing)
- `~/.zed/settings.json` (ARCA project section)
- `~/.antigravity/settings.json` (ARCA project section)

---

### Phase 4: Documentation & Testing (Priority: Medium)

**Tasks**:
1. Update `MCP_INTEGRATION.md` with complete configs
2. Create integration test script
3. Document troubleshooting steps
4. Create architecture diagram

**Estimated Time**: 1-2 hours

**Documentation Files**:
- `docs/MCP_INTEGRATION.md` (update)
- `docs/MCP_INTEGRATION_STATUS.md` (this file)
- `scripts/test_mcp_integration.sh` (new)

---

## Testing Checklist

### Zed Editor

- [ ] Notion MCP: Search pages
- [ ] Notion MCP: Query database
- [ ] Notion MCP: Create page
- [ ] GitHub MCP: List issues
- [ ] GitHub MCP: Create issue
- [ ] GCP Gateway: Query memory
- [ ] BiOS_PM Agent: Execute task

---

### Antigravity

- [ ] Notion MCP: Search pages
- [ ] Notion MCP: Query database
- [ ] Notion MCP: Create page
- [ ] GitHub MCP: List repositories
- [ ] GitHub MCP: Create issue
- [ ] GCP Gateway: Query memory
- [ ] Cross-project sync: Biomimetics ↔ ARCA

---

### ARCA Project

- [ ] Notion databases accessible
- [ ] GCP memory namespace working
- [ ] Cloudflare Worker routing correct
- [ ] GitHub MCP access working
- [ ] Cross-project memory sharing

---

## Troubleshooting

### GitHub MCP Connection Fails

```bash
# Test SSE endpoint
curl -v http://github-mcp-sse.westus2.azurecontainer.io:8080/sse

# Check Azure container status
az container show -g arca-mcp-services -n github-mcp-sse

# View logs
az container logs -g arca-mcp-services -n github-mcp-sse
```

**Common Issues**:
- Container stopped: `az container restart -g arca-mcp-services -n github-mcp-sse`
- Wrong URL: Verify endpoint in config matches Azure deployment
- Network issues: Check Azure firewall rules

---

### Notion MCP Not Working

```bash
# Test Notion token
npx -y @notionhq/notion-mcp-server

# Check database access
# Open Notion → Database → ... → Connect to → Select integration

# Verify token in Azure secrets
az keyvault secret show --vault-name arca-mcp-kv-dae --name notion-api-key
```

**Common Issues**:
- Token expired: Run `python3 azure/azure_secrets_init.py --refresh`
- Database not shared: Share database with integration in Notion
- Wrong database ID: Verify IDs in config match Notion

---

### GCP Gateway Unreachable

```bash
# Test endpoint
curl -X POST https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator \
  -H "Content-Type: application/json" \
  -d '{"action": "ping"}'

# Check GCP credentials
cat ~/.gcp/google_drive_credentials.json | jq .

# Verify GCP Gateway URL in config
grep GCP_GATEWAY cloudflare/wrangler.toml
```

**Common Issues**:
- Wrong URL: Check `wrangler.toml` and update
- Auth failure: Refresh GCP service account credentials
- Function not deployed: Redeploy GCP Cloud Function

---

## Configuration Reference

### Complete Zed Configuration

```json
{
  "mcp_servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "[NOTION_TOKEN_REDACTED]"
      }
    },
    "github": {
      "url": "http://github-mcp-sse.westus2.azurecontainer.io:8080/sse",
      "transport": "sse",
      "description": "GitHub MCP via Azure ACI"
    }
  },
  "agent_servers": {
    "BiOS_PM": {
      "type": "custom",
      "command": "python3",
      "args": ["~/.copaw/bios_orchestrator.py"],
      "env": {
        "NOTION_DB_ID": "3224d2d9fc7c80deb18dd94e22e5bb21",
        "GCP_GATEWAY": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
      }
    }
  }
}
```

---

### Complete Antigravity Configuration

```json
{
  "mcp_servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "[NOTION_TOKEN_REDACTED]"
      },
      "tools": [
        "search_notion", "get_page", "create_page",
        "update_page", "query_database"
      ]
    },
    "github": {
      "url": "http://github-mcp-sse.westus2.azurecontainer.io:8080/sse",
      "transport": "sse",
      "tools": [
        "github.create_issue",
        "github.update_issue",
        "github.search_issues",
        "github.get_issue",
        "github.create_pull_request",
        "github.list_pull_requests",
        "github.get_pull_request",
        "github.get_repository"
      ]
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

## Summary

### What's Working ✅

- **Notion MCP**: Configured for Biomimetics (Claude, Qwen, Zed)
- **GitHub MCP**: Deployed on Azure ACI (SSE endpoint)
- **GCP Gateway**: Active and routing memory requests
- **Cloudflare Worker**: Multi-system integration hub
- **CoPaw**: Full integration with all MCP servers

### What Needs Work ⚠️

- **Zed Editor**: Missing GitHub MCP config
- **Antigravity**: No configuration exists
- **ARCA Project**: Not integrated with any MCP servers
- **Cross-project sync**: Not configured

### Next Steps 🎯

1. **Immediate** (30 min): Update Zed config with GitHub MCP
2. **Today** (45 min): Create Antigravity config
3. **This Week** (2-3 hrs): Integrate ARCA project
4. **Documentation** (1-2 hrs): Update all docs

---

**Contact**: Claws <claws@arca-vsa.tech>  
**Repository**: https://github.com/danxalot/biomimetics  
**Last Updated**: 2026-03-19
