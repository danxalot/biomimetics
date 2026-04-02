# MCP Integration QuickStart Guide

**Date**: 2026-03-19  
**Status**: Configuration Complete - GitHub MCP Redeployment Required  
**Projects**: Biomimetics + BiOS

---

## Quick Status

| Component | Status | Action Required |
|-----------|--------|-----------------|
| **Zed Editor** | ✅ Configured | Restart Zed |
| **Antigravity** | ✅ Configured | Restart Antigravity |
| **Notion MCP** | ✅ Ready | None |
| **GitHub MCP** | ⚠️ Was Deployed | **Redeploy required** |
| **GCP Gateway** | ✅ Active | None |
| **BiOS Databases** | ⚠️ Need Verification | Check existing DBs |

---

## Immediate Actions (Required)

### 1. Redeploy GitHub MCP Server (10 minutes)

**Previous Deployment Info**:
- The GitHub MCP server **was previously deployed** to Azure East US
- Container name: `github-mcp-server`
- Resource group: `arca-consolidated`
- Previous endpoint: `http://github-mcp-server.eastus.azurecontainer.io:8080/mcp`
- **Current Status**: Container is stopped/deleted, but Azure resources still exist

**Azure Resources Still Available**:
- ✓ Container Registry: `arcamcpconsolidated` (eastus)
- ✓ Key Vault: `arca-mcp-kv-dae` (67 secrets including `github-token`)
- ✓ Key Vault: `arca-mcp-kv-dae2` (backup)
- ✗ Container Instance: `github-mcp-server` (not found - needs redeployment)

```bash
# Navigate to Azure scripts
cd ~/biomimetics/azure

# Deploy GitHub MCP with Key Vault integration
./deploy_github_mcp_with_keyvault.sh
```

**What this does**:
- Retrieves GitHub token from Azure Key Vault (`arca-mcp-kv-dae`)
- Deploys GitHub MCP container in East US
- Provides SSE endpoint URL
- Updates CoPaw configuration automatically

**Expected Output**:
```
✅ GitHub token retrieved successfully
✅ Container deployed: github-mcp-server
📡 Endpoint: http://<ip>.eastus.azurecontainer.io:8080/mcp
```

**Update configs with new endpoint**:
After deployment, update the GitHub MCP URL in:
- `~/.zed/settings.json`
- `~/.antigravity/settings.json`
- `~/.copaw/config.json`

---

### 2. Create BiOS Notion Databases (10 minutes)

Create the following databases in Notion for BiOS project tracking:

#### BiOS Projects Database

1. Open Notion → Create new database
2. Add properties:
   - `Name` (Title)
   - `Status` (Status: Not Started, In Progress, On Hold, Complete)
   - `Priority` (Select: Critical, High, Medium, Low)
   - `Description` (Text)
   - `Github Link` (URL)
   - `Team` (Multi-select)
   - `Start Date` (Date)
   - `Due Date` (Date)
3. Copy database ID from URL

#### BiOS Tasks Database

1. Create new database
2. Add properties:
   - `Name` (Title)
   - `Status` (Status: Not Started, In Progress, Review, Done)
   - `Project` (Relation → BiOS Projects)
   - `Assignee` (People)
   - `Priority` (Select: Critical, High, Medium, Low)
   - `Description` (Text)
   - `Github Issue` (URL)
   - `Due Date` (Date)

#### Share with Integration

1. Open each database
2. Click `...` → `Connect to`
3. Select your Notion integration
4. Copy database IDs

---

### 3. Update Configuration with BiOS Database IDs (5 minutes)

Update `cloudflare/wrangler.toml`:

```toml
[vars]
# BiOS Project vars (replace with your IDs)
BiOS_PROJECTS_DB_ID = "your-arca-projects-db-id"
BiOS_TASKS_DB_ID = "your-arca-tasks-db-id"
BiOS_MEMORY_DB_ID = "your-arca-memory-db-id"
```

Update `~/.zed/settings.json`:

```json
{
  "agent_servers": {
    "BiOS_PM": {
      "type": "custom",
      "command": "python3",
      "args": ["~/.copaw/arca_orchestrator.py"],
      "env": {
        "NOTION_DB_ID": "your-arca-projects-db-id",
        "GCP_GATEWAY": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
      }
    }
  }
}
```

---

### 4. Test Integration (5 minutes)

```bash
# Run integration test suite
cd ~/biomimetics
./scripts/test_mcp_integration.sh
```

**Expected Output**:
```
✓ GitHub MCP SSE endpoint reachable (HTTP 200)
✓ GCP Gateway reachable (HTTP 200)
✓ npx available
✓ Notion MCP server executable
✓ Zed config exists
✓ GitHub MCP configured in Zed
✓ Notion MCP configured in Zed
✓ GCP Gateway configured in Zed
✓ Antigravity config exists
✓ All tests passed!
```

---

## Testing Each Component

### Test Notion MCP

```bash
# Test Notion connection
npx -y @notionhq/notion-mcp-server

# In Zed or Antigravity, try:
"Search my Notion for projects"
"Query the Biomimetic OS database"
```

### Test GitHub MCP (after deployment)

```bash
# Test SSE endpoint
curl -v http://<your-azure-ip>:8080/sse

# In Zed or Antigravity:
"List my GitHub repositories"
"Search GitHub issues for bug"
```

### Test GCP Gateway

```bash
# Test memory orchestrator
curl -X POST https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator \
  -H "Content-Type: application/json" \
  -d '{"action": "ping"}'
```

### Test Cloudflare Worker

```bash
# Test GitHub webhook endpoint
curl -X POST https://arca-github-notion-sync.dan-exall.workers.dev \
  -H "X-Arca-Source: GitHub" \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

---

## Troubleshooting

### GitHub MCP Deployment Fails

**Issue**: Azure Key Vault access denied

**Solution**:
```bash
# Grant Key Vault access
az login
az role assignment create \
  --assignee $(az ad signed-in-user show --query id -o tsv) \
  --role "Key Vault Administrator" \
  --scope /subscriptions/<your-sub-id>/resourceGroups/arca-rg/providers/Microsoft.KeyVault/vaults/arca-mcp-kv-dae
```

**Issue**: Container deployment fails

**Solution**:
```bash
# Check resource group exists
az group show -n arca-consolidated

# Create if needed
az group create -n arca-consolidated -l eastus
```

---

### Notion MCP Not Working

**Issue**: Database not found

**Solution**:
1. Open database in Notion
2. Click `...` → `Connect to`
3. Select your integration
4. Verify database ID in config

**Issue**: Token expired

**Solution**:
```bash
# Refresh secrets from Azure Key Vault
cd ~/biomimetics
python3 azure/azure_secrets_init.py --refresh

# Re-run MCP setup
./scripts/setup_notion_mcp.sh
```

---

### GCP Gateway Errors

**Issue**: Function not found

**Solution**:
1. Check GCP project: `arca-471022`
2. Verify Cloud Function deployed: `memory-orchestrator`
3. Check function logs in GCP Console

**Issue**: Authentication failed

**Solution**:
```bash
# Refresh GCP credentials
gcloud auth application-default login

# Verify service account
cat ~/.gcp/google_drive_credentials.json | jq .
```

---

## Configuration Files Reference

### Zed Editor
**Location**: `~/.zed/settings.json`

**Contents**:
- Notion MCP configuration
- GitHub MCP configuration (after deployment)
- BiOS_PM agent server
- GCP Gateway settings

### Antigravity
**Location**: `~/biomimetics/.antigravity/settings.json`

**Contents**:
- Notion MCP configuration
- GitHub MCP configuration (after deployment)
- GCP Gateway settings
- Project namespaces

### Cloudflare Worker
**Location**: `~/biomimetics/cloudflare/wrangler.toml`

**Contents**:
- Database IDs (Biomimetics + BiOS)
- GCP Gateway URL
- GitHub token (for worker)
- Other environment variables

---

## Next Steps

### After Deployment

1. ✅ GitHub MCP deployed and tested
2. ✅ BiOS Notion databases created
3. ✅ All configs updated with correct IDs
4. ✅ Integration tests passing

### Optional Enhancements

1. **Add SSL to GitHub MCP** (recommended for production)
   - Deploy custom domain
   - Add Let's Encrypt certificate
   - Update configs to use HTTPS

2. **Create BiOS-specific agent**
   - Copy `bios_orchestrator.py`
   - Customize for BiOS workflows
   - Configure in Zed/Antigravity

3. **Setup cross-project sync**
   - Configure Cloudflare Worker routing
   - Setup shared memory namespace
   - Test bi-directional sync

---

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/MCP_INTEGRATION_STATUS.md` | Detailed status report |
| `docs/BiOS_MCP_INTEGRATION.md` | BiOS project integration guide |
| `docs/MCP_INTEGRATION.md` | General MCP setup guide |
| `azure/GITHUB_MCP_KEYVAULT_INTEGRATION.md` | GitHub MCP deployment |
| `docs/GITHUB_MCP_SSE_DEPLOYMENT.md` | SSE deployment reference |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/setup_mcp_integration.sh` | Configure Zed + Antigravity |
| `scripts/test_mcp_integration.sh` | Test all integrations |
| `scripts/setup_notion_mcp.sh` | Setup Notion MCP only |
| `azure/deploy_github_mcp_with_keyvault.sh` | Deploy GitHub MCP |

---

## Contact & Support

- **Project**: Biomimetics / BiOS
- **Repository**: https://github.com/danxalot/biomimetics
- **Documentation**: `docs/`
- **Identity**: Claws <claws@arca-vsa.tech>

---

**Last Updated**: 2026-03-19  
**Status**: Configuration Complete - Awaiting GitHub MCP Deployment
