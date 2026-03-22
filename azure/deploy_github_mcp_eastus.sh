#!/bin/bash
# Phase 4: Deploy GitHub MCP in EastUS

set -e

echo "=== PHASE 4: DEPLOY GITHUB MCP IN EASTUS ==="
echo ""

# Get GitHub token from old Key Vault
echo "Getting GitHub token from Key Vault..."
GITHUB_TOKEN=$(az keyvault secret show --vault-name arca-mcp-kv-dae --name github-token --query value -o tsv 2>/dev/null)

if [ -z "$GITHUB_TOKEN" ]; then
    echo "ERROR: Could not retrieve GitHub token"
    exit 1
fi

echo "Token retrieved: ${GITHUB_TOKEN:0:10}..."

# Get ACR password
echo "Getting ACR password..."
ACR_PASSWORD=$(az acr credential show -n arcamcpconsolidated -g arca-consolidated --query passwords[0].value -o tsv 2>/dev/null)

if [ -z "$ACR_PASSWORD" ]; then
    echo "ERROR: Could not retrieve ACR password"
    exit 1
fi

echo "ACR password retrieved: ${ACR_PASSWORD:0:10}..."
echo ""

# Deploy GitHub MCP Server
echo "Deploying github-mcp-server in eastus..."
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
    --environment-variables GITHUB_TOKEN="$GITHUB_TOKEN" \
    -o table

echo ""
echo "Getting deployment status..."
az container show -g arca-consolidated -n github-mcp-server --query "{status:instanceView.currentState.state, ip:ipAddress.ip}" -o table

echo ""
echo "✅ GitHub MCP Server deployed in eastus!"
