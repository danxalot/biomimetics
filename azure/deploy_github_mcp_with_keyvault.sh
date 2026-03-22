#!/bin/bash
# Deploy GitHub MCP Server with Key Vault Integration
# This script retrieves the GitHub token from the recovered Key Vault and deploys the container

set -e

echo "=== GitHub MCP Deployment with Key Vault Integration ==="
echo ""

# Step 1: Check if user is logged in
echo "Checking Azure login status..."
if ! az account show > /dev/null 2>&1; then
    echo "⚠️  Please log in with: az login"
    exit 1
fi

# Step 2: Get GitHub token from recovered Key Vault
echo "Retrieving GitHub token from Key Vault (arca-mcp-kv-dae)..."
GITHUB_TOKEN=$(az keyvault secret show \
    --vault-name arca-mcp-kv-dae \
    --name github-token \
    --query value \
    -o tsv 2>&1)

if [ $? -ne 0 ] || [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Failed to retrieve GitHub token from Key Vault"
    echo ""
    echo "Possible solutions:"
    echo "1. Log in with your user account: az login"
    echo "2. Grant service principal access to Key Vault:"
    echo "   az role assignment create --assignee <your-oid> --role 'Key Vault Administrator' --scope <vault-scope>"
    exit 1
fi

echo "✅ GitHub token retrieved successfully"
echo "Token: ${GITHUB_TOKEN:0:10}..."
echo ""

# Step 3: Get ACR credentials
echo "Getting Container Registry credentials..."
ACR_PASSWORD=$(az acr credential show \
    -n arcamcpconsolidated \
    -g arca-consolidated \
    --query passwords[0].value \
    -o tsv 2>&1)

if [ -z "$ACR_PASSWORD" ]; then
    echo "❌ Failed to get ACR password"
    exit 1
fi

echo "✅ ACR credentials retrieved"
echo ""

# Step 4: Deploy container
echo "Deploying GitHub MCP Server in eastus..."
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
    --environment-variables GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_TOKEN" \
    -o table

if [ $? -ne 0 ]; then
    echo "❌ Deployment failed"
    exit 1
fi

echo ""
echo "✅ Deployment successful!"
echo ""

# Step 5: Get deployment info
echo "Getting deployment information..."
sleep 10  # Wait for container to start

IP_ADDRESS=$(az container show \
    -g arca-consolidated \
    -n github-mcp-server \
    --query ipAddress.ip \
    -o tsv 2>&1)

echo ""
echo "=== Deployment Summary ==="
echo ""
echo "Container: github-mcp-server"
echo "Location: eastus (Consolidated)"
echo "IP Address: $IP_ADDRESS"
echo "Endpoint: http://$IP_ADDRESS:8080/mcp"
echo "Key Vault: arca-mcp-kv-dae (Recovered)"
echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Update CoPaw config (~/.copaw/config.json):"
echo "   \"github\": {"
echo "     \"url\": \"http://$IP_ADDRESS:8080/mcp\""
echo "   }"
echo ""
echo "2. Restart CoPaw:"
echo "   pkill -f 'copaw app'"
echo "   cd ~/biomimetics && nohup copaw app > ~/.copaw/copaw.log 2>&1 &"
echo ""
echo "3. Test GitHub MCP:"
echo "   copaw chats 'Create a test GitHub issue'"
echo ""
