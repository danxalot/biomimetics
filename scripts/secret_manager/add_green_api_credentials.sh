#!/bin/bash
# Add Green API credentials to Azure Key Vault
# Run this script after setting up Azure CLI authentication

set -euo pipefail

# Green API credentials from /Users/danexall/biomimetics/secrets/green_api_key
GREEN_API_ID="7107560335"
GREEN_API_URL="https://7107.api.greenapi.com"
GREEN_API_TOKEN=""  # Read from green_api_key file

# Azure Key Vault name
KEY_VAULT_NAME="arca-mcp-kv-dae"

echo "=== Adding Green API Credentials to Azure Key Vault ==="
echo ""

# Read token from green_api_key file
GREEN_API_KEY_FILE="/Users/danexall/biomimetics/secrets/green_api_key"
if [ -f "$GREEN_API_KEY_FILE" ]; then
    # Extract apiTokenInstance from the file
    GREEN_API_TOKEN=$(grep -v "^#" "$GREEN_API_KEY_FILE" | grep -v "^apiUrl" | grep -v "^mediaUrl" | grep -v "^idInstance" | grep -v "^Name" | tr -d '[:space:]')
    
    if [ -z "$GREEN_API_TOKEN" ]; then
        echo "❌ Could not extract apiTokenInstance from green_api_key file"
        exit 1
    fi
else
    echo "❌ Green API key file not found: $GREEN_API_KEY_FILE"
    exit 1
fi

echo "📋 Credentials extracted:"
echo "   GREEN_API_ID: $GREEN_API_ID"
echo "   GREEN_API_URL: $GREEN_API_URL"
echo "   GREEN_API_TOKEN: ${GREEN_API_TOKEN:0:10}...${GREEN_API_TOKEN: -10}"
echo ""

# Check Azure CLI authentication
if ! az account show &>/dev/null; then
    echo "❌ Azure CLI not authenticated. Run: az login"
    exit 1
fi

echo "✅ Azure CLI authenticated"
echo ""

# Add secrets to Key Vault
echo "🔐 Adding secrets to Azure Key Vault ($KEY_VAULT_NAME)..."
echo ""

echo "   Adding green-api-id..."
az keyvault secret set \
    --vault-name "$KEY_VAULT_NAME" \
    --name "green-api-id" \
    --value "$GREEN_API_ID" \
    --description "Green API instance ID for WhatsApp bridge"

echo "   Adding green-api-url..."
az keyvault secret set \
    --vault-name "$KEY_VAULT_NAME" \
    --name "green-api-url" \
    --value "$GREEN_API_URL" \
    --description "Green API base URL for WhatsApp bridge"

echo "   Adding green-api-token..."
az keyvault secret set \
    --vault-name "$KEY_VAULT_NAME" \
    --name "green-api-token" \
    --value "$GREEN_API_TOKEN" \
    --description "Green API token instance for WhatsApp bridge"

echo ""
echo "✅ Green API credentials added to Azure Key Vault"
echo ""
echo "Next steps:"
echo "1. Deploy Cloudflare Worker: cd cloudflare/whatsapp-notifier && wrangler deploy"
echo "2. Set Worker secrets: wrangler secret put GREEN_API_ID (etc.)"
echo "3. Configure Green API webhook URL in Green API dashboard"
echo "4. Test: curl -X POST https://your-worker.workers.dev/test -H 'Content-Type: application/json' -d '{\"message\":\"Test\"}'"
