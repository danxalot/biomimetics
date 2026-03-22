#!/bin/bash
# Redeploy GitHub MCP with correct env var
# Updated: 2026-03-19 - Path corrected and environment variable support added

set -euo pipefail

# Configuration
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-arca-consolidated}"
ACR_NAME="${AZURE_ACR_NAME:-arcamcpconsolidated}"
CONTAINER_NAME="${CONTAINER_NAME:-github-mcp-server}"
ARCA_SECRETS_DIR="${ARCA_SECRETS_DIR:-/Users/danexall/Documents/VS Code Projects/ARCA/.secrets}"

# Get GitHub PAT from secrets directory
GITHUB_PAT=$(cat "$ARCA_SECRETS_DIR/github_token" | tr -d '\n')

echo "Configuration:"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  ACR: $ACR_NAME"
echo "  Container: $CONTAINER_NAME"
echo "  Secrets Dir: $ARCA_SECRETS_DIR"
echo ""

echo "Deleting existing container..."
az container delete --resource-group "$RESOURCE_GROUP" --name "$CONTAINER_NAME" --yes || true

echo "Creating new container with GITHUB_PERSONAL_ACCESS_TOKEN..."
az container create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_NAME" \
  --image "$ACR_NAME.azurecr.io/github-mcp-server:latest" \
  --dns-name-label github-mcp-server \
  --ports 8080 \
  --environment-variables GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_PAT" \
  --cpu 1 --memory 1 --os-type Linux \
  --output table

echo ""
echo "Container deployed. Getting FQDN..."
az container show --resource-group "$RESOURCE_GROUP" --name "$CONTAINER_NAME" --query "{fqdn:ipAddress.fqdn, status:instanceView.currentState.state}" -o table
