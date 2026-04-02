#!/bin/bash
# 
# Deploy Cloudflare Worker with Azure Secrets
# Dynamically fetches secrets from Azure Credentials Server and injects them
# into the Cloudflare Worker deployment.

set -euo pipefail

# Configuration
CLOUDFLARE_DIR="/Users/danexall/biomimetics/cloudflare"
SECRETS_PROVIDER_CMD="python3 /Users/danexall/biomimetics/scripts/secrets/azure_secrets_provider.py"

echo "=============================================="
echo "Cloudflare Worker Deployment with Azure Secrets"
echo "=============================================="

cd "$CLOUDFLARE_DIR"

echo "1. Fetching secrets from Azure Credentials Server..."

# Fetch Secrets
NOTION_API_KEY=$($SECRETS_PROVIDER_CMD --get notion-api-key 2>/dev/null || echo "")
GITHUB_WEBHOOK_SECRET=$($SECRETS_PROVIDER_CMD --get github-webhook-secret 2>/dev/null || echo "")
GEMINI_API_KEY=$($SECRETS_PROVIDER_CMD --get gemini-api-key 2>/dev/null || echo "")
GITHUB_TOKEN=$($SECRETS_PROVIDER_CMD --get github-token 2>/dev/null || echo "")

echo "2. Injecting secrets into Cloudflare..."

# We pipe the secret directly to wrangler secret put
if [ -n "$NOTION_API_KEY" ] && [[ "$NOTION_API_KEY" != *"not found"* ]]; then
    echo "$NOTION_API_KEY" | npx wrangler secret put NOTION_API_KEY
    echo "$NOTION_API_KEY" | npx wrangler secret put NOTION_TOKEN
    echo "✓ Injected NOTION_API_KEY and NOTION_TOKEN"
else
    echo "⚠ Warning: notion-api-key not found in Azure secrets."
fi

if [ -n "$GITHUB_WEBHOOK_SECRET" ] && [[ "$GITHUB_WEBHOOK_SECRET" != *"not found"* ]]; then
    echo "$GITHUB_WEBHOOK_SECRET" | npx wrangler secret put GITHUB_WEBHOOK_SECRET
    echo "✓ Injected GITHUB_WEBHOOK_SECRET"
else
    echo "⚠ Warning: github-webhook-secret not found in Azure secrets."
fi

if [ -n "$GEMINI_API_KEY" ] && [[ "$GEMINI_API_KEY" != *"not found"* ]]; then
    echo "$GEMINI_API_KEY" | npx wrangler secret put GEMINI_API_KEY
    echo "✓ Injected GEMINI_API_KEY as secret"
else
    echo "⚠ Warning: gemini-api-key not found in Azure secrets."
fi

if [ -n "$GITHUB_TOKEN" ] && [[ "$GITHUB_TOKEN" != *"not found"* ]]; then
    echo "$GITHUB_TOKEN" | npx wrangler secret put GITHUB_TOKEN
    echo "✓ Injected GITHUB_TOKEN as secret"
else
    echo "⚠ Warning: github-token not found in Azure secrets."
fi

echo "3. Deploying Worker..."
npx wrangler deploy

echo "✅ Deployment complete!"
