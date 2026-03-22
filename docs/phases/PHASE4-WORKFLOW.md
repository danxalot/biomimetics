# Phase 4: The Autonomous IDE - Workflow Documentation

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Notion         │────▶│  Cloudflare Worker  │────▶│  Copaw Agent     │
│  (Task Mgmt)    │     │  (Webhook Router)   │     │  (LLM + Memory)  │
└─────────────────┘     └─────────────────────┘     └────────┬─────────┘
                                                             │
                    ┌────────────────────────────────────────┤
                    │                                        │
                    ▼                                        ▼
          ┌─────────────────┐                    ┌──────────────────┐
          │  Azure ACI      │                    │  Serena MCP      │
          │  GitHub MCP     │                    │  (Code Intel)    │
          │  (Issues/PRs)   │                    │                  │
          └─────────────────┘                    └──────────────────┘
                    │                                        │
                    └────────────────┬───────────────────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │  Tool Guard         │
                          │  (Approval Router)  │
                          └──────────┬──────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
          ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
          │  Notion      │ │  Telegram    │ │  MemU        │
          │  (Approval)  │ │  (Approval)  │ │  (Context)   │
          └──────────────┘ └──────────────┘ └──────────────┘
```

---

## Workflow: Notion Task → GitHub Issue → Code Execution

### Step 1: User Creates Task in Notion
```
User Action:
- Opens Notion database
- Creates new page: "Implement feature X"
- Sets Action property to "plan_feature"
- Presses database button
```

### Step 2: Cloudflare Worker Routes to Copaw
```javascript
// Cloudflare Worker receives webhook
{
  "action": "plan_feature",
  "data": {
    "page_id": "abc123",
    "title": "Implement feature X",
    "description": "..."
  }
}

// Forwards to local Copaw API
POST http://localhost:8000/notion
```

### Step 3: Copaw Queries MemU for Context
```python
# Memory Interceptor Hook (pre_reply)
# Automatically queries GCP Gateway before LLM reasoning

gateway_response = await gateway.post({
  "query": "Implement feature X architecture context",
  "user_id": "copaw"
})

# Returns unified memory from:
# - MuninnDB (working memory)
# - MemU (archive memory with 1536-dim embeddings)

# Memory context silently injected into system prompt
```

### Step 4: GitHub MCP Creates Issue
```python
# Copaw uses Azure-hosted GitHub MCP
github_mcp.create_issue(
  repo="org/repo",
  title="Implement feature X",
  body="...",
  labels=["feature", "copaw-generated"]
)

# MCP request goes to Azure ACI:
# http://github-mcp-server-xxxx.westus2.azurecontainer.io:8080/mcp
```

### Step 5: Serena Provides Code Intelligence
```python
# Serena MCP (local stdio transport)
serena.search_symbols(query="feature X related code")
serena.get_symbol_implementation(symbol="ExistingFeature")
serena.get_call_hierarchy(symbol="mainFunction")

# Results stored in ~/.serena/memories/
# Auto-synced to MemU by serena-memory-sync.py
```

### Step 6: Tool Guard Intercepts High-Risk Actions
```python
# User approves plan, Copaw executes

# Safe operation - auto-approved
serena.get_file_content("src/main.py")  # ✅ Approved

# High-risk - requires approval
serena.execute_shell_command("git push origin main")
# → Tool Guard intercepts
# → Creates Notion approval page
# → Sends Telegram message
# → Waits for user approval
```

### Step 7: User Approves via Notion/Telegram
```
Notion Approval Page:
- Name: "Approval: serena.execute_shell_command"
- Status: Pending → Approved (user clicks button)
- Tool: serena.execute_shell_command
- Arguments: {"command": "git push origin main"}

Telegram:
🔒 Tool Approval Required
Tool: serena.execute_shell_command
Arguments: {"command": "git push origin main"}

Reply with /approve <approval_id>
```

### Step 8: Execution Continues
```python
# After approval
tool_guard.grant_approval(approval_id)

# Copaw continues execution
serena.execute_shell_command("git push origin main")  # ✅ Executed

# Result stored in memory
gateway.post({
  "operation": "memorize",
  "content": "Pushed feature X to main branch",
  "metadata": {"source": "copaw_execution"}
})
```

---

## Configuration Files

### Copaw Config (~/.copaw/config.json)
```json
{
  "mcp_servers": {
    "github": {
      "url": "http://github-mcp-server-xxxx.westus2.azurecontainer.io:8080/mcp",
      "transport": "http",
      "headers": {"X-MCP-Tools": "issues,pull_requests"},
      "restricted_tools": ["github.create_issue", "github.update_issue"],
      "require_approval_for": ["github.create_issue"]
    },
    "serena": {
      "command": "uvx",
      "args": ["mcp-server-serena"],
      "transport": "stdio",
      "restricted_tools": ["serena.search_symbols"],
      "require_approval_for": ["serena.execute_shell_command"]
    }
  },
  "tool_guard": {
    "enabled": true,
    "approval_channels": {
      "notion": {"enabled": true, "database_id": "..."},
      "telegram": {"enabled": false}
    }
  }
}
```

### Azure Deployment
```bash
# Resource Group
az group create --name arca-mcp-services --location westus2

# Container Registry
az acr create --name arcamcpregistry --resource-group arca-mcp-services

# Import GitHub MCP Server
az acr import --source ghcr.io/github/github-mcp-server:latest

# Deploy to ACI
az container create \
  --name github-mcp-server \
  --resource-group arca-mcp-services \
  --image arcamcpregistry.azurecr.io/github-mcp-server:latest \
  --environment-variables GITHUB_PAT=<from-keyvault>
```

### Serena Sync (launchd)
```xml
<!-- ~/Library/LaunchAgents/com.arca.serena-sync.plist -->
<dict>
  <key>Label</key>
  <string>com.arca.serena-sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/danexall/serena-memory-sync.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
```

---

## Environment Variables

```bash
# Azure
export AZURE_RESOURCE_GROUP=arca-mcp-services
export AZURE_LOCATION=westus2
export AZURE_KEY_VAULT_NAME=arca-vault

# GitHub
export GITHUB_PAT=ghp_xxx  # Stored in Key Vault

# Notion
export NOTION_API_KEY=secret_xxx
export NOTION_TASKS_DB_ID=xxx
export NOTION_APPROVAL_DB_ID=xxx
export NOTION_WEBHOOK_SECRET=xxx

# Telegram (optional)
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx

# GCP Memory Gateway
export GCP_GATEWAY_URL=https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator
```

---

## Files Created

| File | Purpose |
|------|---------|
| `phase4-azure-deploy.sh` | Azure ACI deployment script |
| `phase4-keyvault-setup.sh` | Key Vault + GitHub PAT setup |
| `phase4-setup.sh` | Complete Phase 4 setup |
| `serena-memory-sync.py` | Serena → MemU sync daemon |
| `copaw-tool-guard.py` | Approval workflow handler |
| `~/.copaw/config-phase4.json` | Copaw configuration |
| `notion-approval-db-template.json` | Notion database template |

---

## Testing the Workflow

```bash
# 1. Start Serena sync
launchctl load ~/Library/LaunchAgents/com.arca.serena-sync.plist

# 2. Start webhook receiver
launchctl load ~/Library/LaunchAgents/com.arca.copaw-webhook.plist

# 3. Create Notion task
# - Add page to tasks database
# - Set Action = "plan_feature"
# - Press button

# 4. Watch logs
tail -f ~/.arca/copaw-webhook.log
tail -f ~/.arca/serena-sync.log

# 5. Check MemU for synced context
curl -X POST https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator \
  -H "Content-Type: application/json" \
  -d '{"query": "serena code spec"}'
```
