# Azure Consolidation to EastUS - Deployment Guide

**Date**: 2026-03-19  
**Status**: Phase 2 Complete - Infrastructure Created  
**Next**: Manual deployment required for containers

---

## ✅ Completed Phases

### Phase 1: Backup ✅
- Backed up existing Key Vault secrets (67 secrets)
- Documented existing container configurations
- Identified 2 Docker images to migrate

### Phase 2: Infrastructure Creation ✅

| Resource | Name | Location | Status |
|----------|------|----------|--------|
| **Resource Group** | `arca-consolidated` | eastus | ✅ Created |
| **Container Registry** | `arcamcpconsolidated` | eastus | ✅ Created (Basic SKU) |
| **Key Vault** | `arca-consolidated-kv` | eastus | ✅ Created (Standard SKU) |

### Phase 3: Image Import ⏳

| Image | Status |
|-------|--------|
| `github-mcp-server:latest` | ✅ Imported |
| `github-mcp-sse:latest` | ⏳ Pending |

---

## 📋 Manual Deployment Steps

### Step 1: Complete Image Import

```bash
# Import remaining image
az acr import \
    -n arcamcpconsolidated \
    --source arcamcpregistry.azurecr.io/github-mcp-sse:latest
```

### Step 2: Deploy GitHub MCP Server

```bash
# Get credentials
GITHUB_TOKEN=$(az keyvault secret show \
    --vault-name arca-mcp-kv-dae \
    --name github-token \
    --query value -o tsv)

ACR_PASSWORD=$(az acr credential show \
    -n arcamcpconsolidated \
    -g arca-consolidated \
    --query passwords[0].value -o tsv)

# Deploy container
az container create \
    -g arca-consolidated \
    -n github-mcp-server \
    --image arcamcpconsolidated.azurecr.io/github-mcp-server:latest \
    --cpu 1 \
    --memory 1 \
    --ports 8080 \
    --ip-address Public \
    --registry-login-server arcamcpconsolidated.azurecr.io \
    --registry-username arcamcpconsolidated \
    --registry-password "$ACR_PASSWORD" \
    --environment-variables GITHUB_TOKEN="$GITHUB_TOKEN"
```

### Step 3: Deploy GitHub MCP SSE

```bash
az container create \
    -g arca-consolidated \
    -n github-mcp-sse \
    --image arcamcpconsolidated.azurecr.io/github-mcp-sse:latest \
    --cpu 1 \
    --memory 1 \
    --ports 8080 \
    --ip-address Public \
    --registry-login-server arcamcpconsolidated.azurecr.io \
    --registry-username arcamcpconsolidated \
    --registry-password "$ACR_PASSWORD"
```

### Step 4: Update CoPaw Configuration

Edit `~/.copaw/config.json`:

```json
{
  "mcp_servers": {
    "github": {
      "url": "http://github-mcp-server.eastus.azurecontainer.io:8080/mcp",
      "transport": "http",
      "headers": {
        "X-MCP-Tools": "issues,pull_requests"
      },
      "description": "GitHub Issues and PRs (Azure ACI - EastUS)"
    }
  }
}
```

### Step 5: Restart CoPaw

```bash
copaw daemon restart
```

### Step 6: Verify & Cleanup

```bash
# Test new endpoint
curl http://github-mcp-server.eastus.azurecontainer.io:8080/health

# Delete old westus2 resources
az container delete -n github-mcp-server -g arca-mcp-services
az container delete -n github-mcp-sse -g arca-mcp-services

# Optional: Delete old resource groups
az group delete -n arca-mcp-services
az group delete -n arca-rg
```

---

## 💰 Cost Analysis

### Before Consolidation

| Resource | Location | Monthly Cost |
|----------|----------|--------------|
| ACI (2 containers) | westus2 | ~$0 (within free tier) |
| ACR Basic | westus2 | ~$5.00 |
| Key Vault (2x) | eastus | ~$0 (within free tier) |
| Cross-region transfer | westus2↔eastus | ~$0.50 |
| **Total** | | **~$5.50/month** |

### After Consolidation

| Resource | Location | Monthly Cost |
|----------|----------|--------------|
| ACI (2 containers) | eastus | ~$0 (within free tier) |
| ACR Basic | eastus | ~$5.00 |
| Key Vault | eastus | ~$0 (within free tier) |
| Cross-region transfer | N/A | $0 |
| **Total** | | **~$5.00/month** |

**Savings**: ~$0.50/month + reduced latency

---

## 🎯 Free Tier Status

| Resource | Free Tier Allowance | Your Usage | Status |
|----------|--------------------|------------|--------|
| **ACI Compute** | 1 vCPU-month | ~0.5 vCPU-month | ✅ Within |
| **ACI Memory** | 4 GB-month | ~0.5 GB-month | ✅ Within |
| **Key Vault Ops** | 25K/month | ~5K/month | ✅ Within |
| **ACR Storage** | Not included | ~500MB | ⚠️ ~$5/month |

---

## 📊 Resource Comparison

### Old Setup (Multi-Region)

```
┌─────────────────────┐         ┌─────────────────────┐
│  GitHub MCP Server  │         │   Key Vault         │
│  westus2            │ ──────→ │   eastus            │
│  (ACI)              │  ~50ms  │   (2 vaults)        │
└─────────────────────┘         └─────────────────────┘
         ↓
┌─────────────────────┐
│  Container Registry │
│  westus2            │
│  (ACR Basic)        │
└─────────────────────┘
```

### New Setup (Single Region)

```
┌─────────────────────────────────────────┐
│         EASTUS CONSOLIDATED             │
│                                         │
│  ┌─────────────────┐   ┌─────────────┐ │
│  │  GitHub MCP     │   │  Key Vault  │ │
│  │  Server         │ → │  (single)   │ │
│  │  (ACI)          │   │             │ │
│  └─────────────────┘   └─────────────┘ │
│           ↓                             │
│  ┌─────────────────┐                   │
│  │  Container      │                   │
│  │  Registry       │                   │
│  │  (ACR Basic)    │                   │
│  └─────────────────┘                   │
└─────────────────────────────────────────┘
```

---

## ⚠️ Important Notes

1. **ACR Cost**: Container Registry Basic SKU is ~$5/month (not included in Azure free tier)
   
2. **Alternative**: Use Docker Hub (free) instead of ACR:
   ```bash
   # Push to Docker Hub
   docker tag github-mcp-server:latest username/github-mcp-server:latest
   docker push username/github-mcp-server:latest
   
   # Deploy from Docker Hub
   az container create \
       -g arca-consolidated \
       -n github-mcp-server \
       --image username/github-mcp-server:latest \
       ...
   ```

3. **Key Vault Migration**: Secrets need to be copied manually:
   ```bash
   # Export from old vault
   az keyvault secret show --vault-name arca-mcp-kv-dae --name github-token
   
   # Import to new vault
   az keyvault secret set --vault-name arca-consolidated-kv --name github-token --value "xxx"
   ```

---

## 🚀 Next Steps

1. **Complete container deployment** (Step 2-3 above)
2. **Update CoPaw config** (Step 4)
3. **Test new endpoint**
4. **Delete old resources** (Step 6)
5. **Consider Docker Hub** for $5/month savings

---

**Script Location**: `~/biomimetics/azure/deploy_github_mcp_eastus.sh`  
**Status**: Ready for manual execution  
**Owner**: User to complete deployment
