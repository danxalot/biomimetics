# Azure Secrets-Init Guide

## Overview

Biomimetics uses Azure Key Vault for centralized secret management. The `azure_secrets_init.py` script fetches secrets and injects them into all configured services.

## Azure Key Vault Setup

### 1. Create Key Vault

```bash
# Login to Azure
az login

# Create resource group (if needed)
az group create --name biomimetics-rg --location eastus

# Create Key Vault
az keyvault create \
  --name biomimetics-vault \
  --resource-group biomimetics-rg \
  --location eastus \
  --sku standard \
  --enable-rbac-authorization false
```

### 2. Add Secrets

```bash
# Notion API Key
az keyvault secret set \
  --vault-name biomimetics-vault \
  --name notion-api-key \
  --value "ntn_YOUR_NOTION_TOKEN_HERE"

# Gmail App Password
az keyvault secret set \
  --vault-name biomimetics-vault \
  --name gmail-app-password \
  --value "your-16-char-app-password"

# Proton Bridge Password
az keyvault secret set \
  --vault-name biomimetics-vault \
  --name proton-bridge-password \
  --value "your-bridge-password"

# MyCloud NAS Password
az keyvault secret set \
  --vault-name biomimetics-vault \
  --name mycloud-password \
  --value "your-nas-password"

# GCP Gateway URL
az keyvault secret set \
  --vault-name biomimetics-vault \
  --name gcp-gateway-url \
  --value "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"

# GitHub Webhook Secret
az keyvault secret set \
  --vault-name biomimetics-vault \
  --name github-webhook-secret \
  --value "your-github-webhook-secret-here"

# CoPaw Approvals Database ID
az keyvault secret set \
  --vault-name biomimetics-vault \
  --name copaw-approval-db-id \
  --value "your-copaw-approvals-db-id-here"

# GCP Service Account (JSON)
az keyvault secret set \
  --vault-name biomimetics-vault \
  --name gcp-service-account \
  --value "$(cat ~/.secrets/gcp_credentials.json | base64)"
```

### 3. Set Access Policy

```bash
# Get your Azure AD object ID
OBJECT_ID=$(az ad signed-in-user show --query id -o tsv)

# Grant secret permissions
az keyvault set-policy \
  --name biomimetics-vault \
  --object-id $OBJECT_ID \
  --secret-permissions get list set
```

## Running Secrets-Init

### Basic Usage

```bash
cd ~/biomimetics

# Authenticate with Azure (if not already)
az login

# Initialize all secrets
python3 azure/azure_secrets_init.py --refresh
```

### Custom Vault Name

```bash
python3 azure/azure_secrets_init.py --vault my-custom-vault
```

### Environment Variables

```bash
export AZURE_KEY_VAULT_NAME="biomimetics-vault"
export AZURE_SUBSCRIPTION_ID="your-subscription-id"
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"

python3 azure/azure_secrets_init.py
```

## What Gets Updated

| File/Service | Secret |
|--------------|--------|
| `config/omni_sync_config.json` | All secrets |
| Cloudflare Worker | `NOTION_API_KEY`, `GITHUB_WEBHOOK_SECRET` |
| Claude Desktop | Notion MCP config |
| Qwen Code | Notion MCP config |
| `secrets/azure_secrets.json` | Local backup (mode 600) |

## Verification

```bash
# Check config was updated
cat config/omni_sync_config.json | grep NOTION

# Check Cloudflare secret
cd cloudflare && wrangler secret list

# Check Notion MCP config
cat secrets/notion_mcp_config.json
```

## Troubleshooting

### "Azure authentication failed"

Run `az login` manually first, then retry.

### "Secret not found"

Verify secret names in Key Vault match exactly (case-sensitive, dashes not underscores).

### "Wrangler not found"

Install Cloudflare Wrangler: `npm install -g wrangler`

## Security Notes

- Local backup at `secrets/azure_secrets.json` has mode 0600 (owner read/write only)
- Secrets are never committed to git (`.gitignore` excludes them)
- Use Azure RBAC for team access control
- Rotate secrets regularly via Azure Portal or CLI
