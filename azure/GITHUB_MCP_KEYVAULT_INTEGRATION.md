# GitHub MCP Server - Key Vault Integration

**Date**: 2026-03-19  
**Status**: Ready for Deployment  
**Key Vault**: `arca-mcp-kv-dae` (Recovered)

---

## 📋 Overview

The GitHub MCP Server has been configured to use secrets from the **recovered Azure Key Vault** (`arca-mcp-kv-dae`).

### Recovered Key Vaults

| Key Vault | Location | Resource Group | Status |
|-----------|----------|----------------|--------|
| `arca-mcp-kv-dae` | eastus | `arca-rg` | ✅ Recovered |
| `arca-mcp-kv-dae2` | eastus | `arca-rg` | ✅ Recovered (Backup) |

### Secrets Available (67 total)

| Secret | Purpose |
|--------|---------|
| `github-token` | GitHub API authentication |
| `notion-api-key` | Notion integration |
| `gcp-credentials-json` | Google Cloud service account |
| `gcp-gateway-url` | GCP Cloud Functions endpoint |
| `gemini-api-key` | Google Gemini API |
| `gmail-app-password` | Gmail IMAP access |
| `proton-bridge-password` | ProtonMail Bridge auth |
| `mycloud-password` | MyCloud NAS credentials |
| `github-webhook-secret` | Webhook signature validation |
| ...and 57 more |

---

## 🚀 Deployment Instructions

### Option 1: Automated Script (Recommended)

```bash
# Navigate to script
cd ~/biomimetics/azure

# Run deployment script
./deploy_github_mcp_with_keyvault.sh
```

**What the script does**:
1. Checks Azure login status
2. Retrieves GitHub token from Key Vault
3. Gets Container Registry credentials
4. Deploys GitHub MCP container in eastus
5. Provides new endpoint URL
6. Updates CoPaw configuration automatically

### Option 2: Manual Deployment

```bash
# 1. Log in with your user account
az login

# 2. Get GitHub token from Key Vault
GITHUB_TOKEN=$(az keyvault secret show \
    --vault-name arca-mcp-kv-dae \
    --name github-token \
    --query value \
    -o tsv)

# 3. Get ACR password
ACR_PASSWORD=$(az acr credential show \
    -n arcamcpconsolidated \
    -g arca-consolidated \
    --query passwords[0].value \
    -o tsv)

# 4. Deploy container
az container create \
    -g arca-consolidated \
    -n github-mcp-server \
    --image arcamcpconsolidated.azurecr.io/github-mcp-server:latest \
    --os-type Linux \
    --cpu 1 \
    --memory 1 \
    --ports 8080 \
    --ip-address Public \
    --registry-login-server arcamcpconsolidated.azurecr.io \
    --registry-username arcamcpconsolidated \
    --registry-password "$ACR_PASSWORD" \
    --environment-variables GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_TOKEN"
```

---

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  EASTUS CONSOLIDATED                         │
│                                                              │
│  ┌─────────────────┐         ┌─────────────────────┐       │
│  │  GitHub MCP     │ ──────→ │  Key Vault          │       │
│  │  Server         │  Token  │  arca-mcp-kv-dae    │       │
│  │  (ACI)          │         │  (67 secrets)       │       │
│  └─────────────────┘         └─────────────────────┘       │
│           ↓                                                │
│  ┌─────────────────┐                                       │
│  │  Container      │                                       │
│  │  Registry       │                                       │
│  │  (ACR)          │                                       │
│  └─────────────────┘                                       │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Post-Deployment

### Update CoPaw Configuration

After deployment, update `~/.copaw/config.json` with the new endpoint:

```json
{
  "mcp_servers": {
    "github": {
      "url": "http://<NEW_IP>:8080/mcp",
      "transport": "http",
      "headers": {
        "X-MCP-Tools": "issues,pull_requests"
      },
      "description": "GitHub Issues and PRs (Azure ACI - EastUS with Key Vault)"
    }
  }
}
```

### Restart CoPaw

```bash
# Stop CoPaw
pkill -f "copaw app"

# Restart from biomimetics directory
cd ~/biomimetics
nohup copaw app > ~/.copaw/copaw.log 2>&1 &
```

### Test GitHub MCP

```bash
# In CoPaw chat
"Create a GitHub issue for testing the Key Vault integration"
```

---

## 🔐 Security Notes

### Key Vault Access

The service principal (`1b04765e-4482-467c-b799-ee6251542ffe`) currently **does not have access** to the recovered Key Vault.

**To grant access**:

```bash
# Log in as subscription owner
az login

# Get your object ID
USER_OID=$(az ad signed-in-user show --query id -o tsv)

# Grant Key Vault Administrator role
az role assignment create \
    --assignee $USER_OID \
    --role "Key Vault Administrator" \
    --scope /subscriptions/2371dae1-f860-4c5b-a5a9-820b3cce0f35/resourceGroups/arca-rg/providers/Microsoft.KeyVault/vaults/arca-mcp-kv-dae
```

### Secret Management

- Secrets are injected as environment variables (not mounted from Key Vault)
- Container restarts will require redeployment with updated secrets
- For automatic secret rotation, consider using Azure Managed Identity

---

## 📈 Monitoring

### Check Container Status

```bash
az container show -g arca-consolidated -n github-mcp-server -o table
```

### View Logs

```bash
az container logs -g arca-consolidated -n github-mcp-server --tail 50
```

### Check Key Vault Access

```bash
az keyvault secret list --vault-name arca-mcp-kv-dae -o table
```

---

## 🎯 Summary

| Component | Status | Details |
|-----------|--------|---------|
| **Key Vault** | ✅ Recovered | `arca-mcp-kv-dae` (67 secrets) |
| **Backup Vault** | ✅ Recovered | `arca-mcp-kv-dae2` |
| **Resource Group** | ✅ Created | `arca-rg` (eastus) |
| **GitHub MCP** | ⏳ Pending | Awaiting deployment with Key Vault |
| **CoPaw Config** | ✅ Ready | Will update after deployment |
| **Deployment Script** | ✅ Created | `azure/deploy_github_mcp_with_keyvault.sh` |

---

**Next Step**: Run `./deploy_github_mcp_with_keyvault.sh` to complete the deployment.
