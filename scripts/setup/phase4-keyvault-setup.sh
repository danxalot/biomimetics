#!/bin/bash
# Azure Key Vault Setup for GitHub PAT
# Creates Key Vault and stores GitHub Personal Access Token

set -e

echo "=============================================="
echo "Azure Key Vault Setup for GitHub PAT"
echo "=============================================="

# Configuration
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-arca-mcp-services}"
LOCATION="${AZURE_LOCATION:-westus2}"
KEY_VAULT_NAME="${AZURE_KEY_VAULT_NAME:-arca-vault-$(openssl rand -hex 4)}"
GITHUB_PAT_SECRET_NAME="github-pat"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "\n${YELLOW}Configuration:${NC}"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Location: $LOCATION"
echo "  Key Vault: $KEY_VAULT_NAME"
echo ""

# Step 1: Create Resource Group (if not exists)
echo -e "\n${YELLOW}Step 1: Ensuring Resource Group exists...${NC}"
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output table

# Step 2: Create Key Vault
echo -e "\n${YELLOW}Step 2: Creating Key Vault...${NC}"
az keyvault create \
  --name "$KEY_VAULT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku standard \
  --output table || {
    echo -e "${RED}Key Vault may already exist${NC}"
  }

# Step 3: Store GitHub PAT
echo -e "\n${YELLOW}Step 3: Storing GitHub PAT...${NC}"
echo -n "Enter your GitHub Personal Access Token: "
read -s GITHUB_PAT
echo ""

if [ -z "$GITHUB_PAT" ]; then
    echo -e "${RED}GitHub PAT cannot be empty${NC}"
    exit 1
fi

az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name "$GITHUB_PAT_SECRET_NAME" \
  --value "$GITHUB_PAT" \
  --description "GitHub Personal Access Token for MCP Server" \
  --output table

echo -e "\n${GREEN}✓ GitHub PAT stored in Key Vault${NC}"

# Step 4: Set Key Vault access policy for current user
echo -e "\n${YELLOW}Step 4: Setting access policy...${NC}"
CURRENT_USER=$(az account show --query "user.name" --output tsv)

az keyvault set-policy \
  --name "$KEY_VAULT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --upn "$CURRENT_USER" \
  --secret-permissions get list set delete \
  --output table

echo -e "\n${GREEN}✓ Access policy configured${NC}"

# Summary
echo ""
echo "=============================================="
echo "Key Vault Setup Complete!"
echo "=============================================="
echo ""
echo "Key Vault Details:"
echo "  Name: $KEY_VAULT_NAME"
echo "  Secret: $GITHUB_PAT_SECRET_NAME"
echo ""
echo "To retrieve the PAT:"
echo "  az keyvault secret show --vault-name $KEY_VAULT_NAME --name $GITHUB_PAT_SECRET_NAME"
echo ""
echo "=============================================="
