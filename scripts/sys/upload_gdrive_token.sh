#!/bin/bash
# BiOS GDrive Token Uplink
# Staged for Azure Key Vault reactivation.
# 
# Usage: ./upload_gdrive_token.sh

TOKEN_PATH="/Users/danexall/biomimetics/.local_gdrive_token.json"
VAULT_NAME="arca-mcp-kv-dae"
SECRET_NAME="gdrive-oauth-token"

if [ ! -f "$TOKEN_PATH" ]; then
    echo "❌ Error: Local token file not found at $TOKEN_PATH"
    exit 1
fi

echo "📡 Attempting to push local GDrive token to Azure Key Vault ($VAULT_NAME)..."

# Security: Read token from file directly into the az command
TOKEN_VALUE=$(cat "$TOKEN_PATH")

az keyvault secret set \
    --vault-name "$VAULT_NAME" \
    --name "$SECRET_NAME" \
    --value "$TOKEN_VALUE" \
    --description "Google Drive OAuth Refresh Token (BiOS Zero-Touch)"

if [ $? -eq 0 ]; then
    echo "✅ Token successfully pushed to Azure Key Vault."
    echo "You can now delete the local fallback file: rm $TOKEN_PATH"
else
    echo "❌ Azure CLI Error: Deployment failed. Ensure subscription is active and you are logged in."
fi
