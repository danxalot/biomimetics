#!/bin/bash
# Deploy GitHub MCP with Supergateway to Azure ACI
# Updated: 2026-03-19 - Path corrected and environment variable support added

set -euo pipefail

# Configuration
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-arca-consolidated}"
ACR_NAME="${AZURE_ACR_NAME:-arcamcpconsolidated}"
CONTAINER_NAME="${CONTAINER_NAME:-github-mcp-sse}"
DNS_LABEL="${DNS_LABEL:-github-mcp-sse}"
ARCA_SECRETS_DIR="${ARCA_SECRETS_DIR:-/Users/danexall/Documents/VS Code Projects/ARCA/.secrets}"
GITHUB_PAT_FILE="$ARCA_SECRETS_DIR/github_token"

echo "Configuration:"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  ACR: $ACR_NAME"
echo "  Container: $CONTAINER_NAME"
echo "  Secrets Dir: $ARCA_SECRETS_DIR"
echo ""

echo "Getting GitHub PAT..."
if [ ! -f "$GITHUB_PAT_FILE" ]; then
    echo "ERROR: GitHub token not found at $GITHUB_PAT_FILE"
    exit 1
fi
GITHUB_PAT=$(cat "$GITHUB_PAT_FILE" | tr -d '\n')

echo "Getting ACR credentials..."
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query passwords[0].value --output tsv)

echo "Deploying to Azure ACI..."
az container create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_NAME" \
  --image "$ACR_NAME.azurecr.io/github-mcp-sse:latest" \
  --dns-name-label "$DNS_LABEL" \
  --ports 8080 \
  --registry-login-server "$ACR_NAME.azurecr.io" \
  --registry-username "$ACR_NAME" \
  --registry-password "$ACR_PASSWORD" \
  --environment-variables GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_PAT" \
  --cpu 2 \
  --memory 2 \
  --os-type Linux \
  --output table

echo ""
echo "Getting FQDN..."
FQDN=$(az container show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_NAME" \
  --query "ipAddress.fqdn" \
  --output tsv)

echo ""
echo "=============================================="
echo "GitHub MCP SSE Server Deployed!"
echo "=============================================="
echo ""
echo "SSE Endpoint: https://$FQDN/sse"
echo "Message Endpoint: https://$FQDN/message"
echo ""
echo "Add to Copaw config:"
cat << EOF

{
  "mcp_servers": {
    "github-remote": {
      "url": "https://$FQDN/sse",
      "transport": "sse",
      "description": "GitHub MCP via Azure ACI (24/7)"
    }
  }
}
EOF
echo ""
echo "=============================================="
