#!/bin/bash
# Simple GitHub MCP redeploy

set -e

RESOURCE_GROUP="arca-mcp-services"
ACR_NAME="arcamcpregistry"
CONTAINER_NAME="github-mcp-server"
GITHUB_PAT_FILE="/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/github_token"

# Read PAT
GITHUB_PAT=$(cat "$GITHUB_PAT_FILE" | tr -d '\n')

echo "Deleting old container..."
az container delete \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_NAME" \
  --yes \
  --output table

echo "Creating new container..."

# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query username --output tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query passwords[0].value --output tsv)

az container create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_NAME" \
  --image "$ACR_NAME.azurecr.io/github-mcp-server:latest" \
  --dns-name-label github-mcp-server \
  --ports 8080 \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --secure-environment-variables GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_PAT" \
  --cpu 1 \
  --memory 1 \
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
echo "GitHub MCP Server Deployed!"
echo "=============================================="
echo "FQDN: $FQDN"
echo "URL: http://$FQDN:8080"
echo ""
echo "Test: curl http://$FQDN:8080/health"
echo "=============================================="
