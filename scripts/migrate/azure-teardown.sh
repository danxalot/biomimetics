#!/bin/bash
#
# Azure Teardown Script - Stop GitHub MCP Billing
#
# This script safely tears down the GitHub MCP container in Azure
# while preserving the ACR and Key Vault for future use.
#
# Updated: 2026-03-19
#

set -euo pipefail

# Configuration
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-arca-consolidated}"
CONTAINER_NAME="${CONTAINER_NAME:-github-mcp-server}"

echo "=============================================="
echo "Azure Teardown - GitHub MCP Container"
echo "=============================================="
echo ""
echo "Configuration:"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Container: $CONTAINER_NAME"
echo ""

# Check Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo "ERROR: Azure CLI not found. Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo "ERROR: Not logged in to Azure. Run: az login"
    exit 1
fi

echo "Current Azure Subscription:"
az account show --query "{name:name, id:id}" -o table
echo ""

# Verify resource group exists
echo "Verifying resource group..."
if ! az group show --name "$RESOURCE_GROUP" &> /dev/null; then
    echo "WARNING: Resource group '$RESOURCE_GROUP' not found. Nothing to teardown."
    exit 0
fi
echo "✓ Resource group exists"

# Check if container exists
echo "Checking for container..."
CONTAINER_EXISTS=$(az container show --resource-group "$RESOURCE_GROUP" --name "$CONTAINER_NAME" --query "name" -o tsv 2>/dev/null || echo "")

if [ -z "$CONTAINER_EXISTS" ]; then
    echo "Container '$CONTAINER_NAME' not found in resource group '$RESOURCE_GROUP'"
    echo "It may have already been deleted or was never created."
    exit 0
fi

echo "✓ Container found: $CONTAINER_EXISTS"
echo ""

# Show container details before deletion
echo "Container Details:"
az container show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$CONTAINER_NAME" \
    --query "{name:name, location:location, status:instanceView.currentState.state, createdTime:instanceView.currentState.startTime}" \
    -o table
echo ""

# Confirm deletion
echo "=============================================="
echo "WARNING: This will permanently delete the container"
echo "=============================================="
echo ""
echo "The following will be DELETED:"
echo "  - Container Instance: $CONTAINER_NAME"
echo ""
echo "The following will be PRESERVED:"
echo "  - Container Registry: ${AZURE_ACR_NAME:-arcamcpconsolidated}"
echo "  - Key Vault: arca-mcp-kv-dae (in arca-rg)"
echo "  - All secrets and Docker images"
echo ""

# Auto-confirm if running in CI/CD or with --yes flag
if [ "${1:-}" != "--yes" ] && [ "${AUTO_CONFIRM:-}" != "true" ]; then
    echo -n "Type 'yes' to confirm deletion: "
    read -r CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Deletion cancelled."
        exit 0
    fi
fi

echo ""
echo "Deleting container..."
az container delete \
    --resource-group "$RESOURCE_GROUP" \
    --name "$CONTAINER_NAME" \
    --yes

echo ""
echo "Verifying deletion..."
sleep 5

CONTAINER_CHECK=$(az container show --resource-group "$RESOURCE_GROUP" --name "$CONTAINER_NAME" --query "name" -o tsv 2>/dev/null || echo "")

if [ -z "$CONTAINER_CHECK" ]; then
    echo "✓ Container successfully deleted"
else
    echo "⚠ Container still exists. Deletion may be in progress."
fi

echo ""
echo "=============================================="
echo "Teardown Complete!"
echo "=============================================="
echo ""
echo "Billing Impact:"
echo "  - ACI charges: STOPPED (was \$0 since container was stopped)"
echo "  - ACR charges: ~\$5/month (preserved for migration)"
echo "  - Key Vault: ~\$0 (within free tier)"
echo ""
echo "Next Steps:"
echo "  1. Deploy to Koyeb: ./scripts/migrate/deploy-to-koyeb.sh"
echo "  2. Update client configs with new endpoint"
echo "  3. (Optional) Delete ACR after migration: az acr delete -n arcamcpconsolidated -g $RESOURCE_GROUP"
echo ""
