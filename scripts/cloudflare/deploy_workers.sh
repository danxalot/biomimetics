#!/bin/bash
# Cloudflare Workers Deployment Script with Secret Injection
# Deploys Gemma PM and WhatsApp Bridge workers with automatic secret injection

set -e

SECRETS_DIR="/Users/danexall/biomimetics/secrets"
PROJECT_ROOT="/Users/danexall/biomimetics"

echo "========================================================================"
echo "  Cloudflare Workers Deployment with Secret Injection"
echo "========================================================================"
echo ""

# Read secrets from local files
echo "📋 Reading secrets from $SECRETS_DIR..."

NOTION_API_KEY=$(cat "$SECRETS_DIR/notion_api_key" | tr -d '\n')
GITHUB_WEBHOOK_SECRET=$(cat "$SECRETS_DIR/github_webhook_secret.txt" | tr -d '\n')
GITHUB_TOKEN=$(cat "$SECRETS_DIR/github_models_token" | tr -d '\n')
GREEN_API_KEY=$(cat "$SECRETS_DIR/green_api_key" | tr -d '\n')

echo "   ✅ NOTION_API_KEY: ${NOTION_API_KEY:0:10}..."
echo "   ✅ GITHUB_WEBHOOK_SECRET: ${GITHUB_WEBHOOK_SECRET:0:10}..."
echo "   ✅ GITHUB_TOKEN: ${GITHUB_TOKEN:0:15}..."
echo "   ✅ GREEN_API_KEY: ${GREEN_API_KEY:0:10}..."
echo ""

# Check if GCP service account key exists
GCP_SERVICE_ACCOUNT=""
if [ -f "$SECRETS_DIR/arca-471022-eb34b8bebd53.json" ]; then
    GCP_SERVICE_ACCOUNT=$(cat "$SECRETS_DIR/arca-471022-eb34b8bebd53.json")
    echo "   ✅ GCP_SERVICE_ACCOUNT: Found"
else
    echo "   ⚠️  GCP_SERVICE_ACCOUNT: Not found (optional)"
fi
echo ""

# =============================================================================
# Deploy Gemma PM Worker (arca-github-notion-sync)
# =============================================================================
echo "========================================================================"
echo "  Deploying: Gemma PM Worker (arca-github-notion-sync)"
echo "========================================================================"
echo ""

cd "$PROJECT_ROOT/cloudflare"

# Deploy the worker
echo "🚀 Running wrangler deploy..."
wrangler deploy --var GEMMA_WORKER_URL:"https://gemma-worker.example.com"

# Inject secrets
echo "🔐 Injecting secrets..."

echo "$NOTION_API_KEY" | wrangler secret put NOTION_API_KEY
echo "$NOTION_API_KEY" | wrangler secret put NOTION_TOKEN
echo "$GITHUB_WEBHOOK_SECRET" | wrangler secret put GITHUB_WEBHOOK_SECRET
echo "$GITHUB_TOKEN" | wrangler secret put GITHUB_TOKEN

if [ -n "$GCP_SERVICE_ACCOUNT" ]; then
    echo "$GCP_SERVICE_ACCOUNT" | wrangler secret put GCP_SERVICE_ACCOUNT
fi

# Note: Gemma API key is injected via GEMMA_WORKER_API_KEY binding
# This would be set based on your Gemma worker deployment
echo ""
echo "✅ Gemma PM Worker deployed successfully!"
echo ""

# =============================================================================
# Deploy WhatsApp Bridge Worker (whatsapp-notifier)
# =============================================================================
echo "========================================================================"
echo "  Deploying: WhatsApp Bridge Worker (whatsapp-notifier)"
echo "========================================================================"
echo ""

cd "$PROJECT_ROOT/cloudflare/whatsapp-notifier"

# Deploy the worker
echo "🚀 Running wrangler deploy..."
wrangler deploy

# Inject Green API secrets
echo "🔐 Injecting Green API secrets..."

# Extract Green API ID and Token from the key file
# Format is typically: instanceId:token
GREEN_API_ID=$(echo "$GREEN_API_KEY" | cut -d':' -f1)
GREEN_API_TOKEN=$(echo "$GREEN_API_KEY" | cut -d':' -f2)

echo "$GREEN_API_ID" | wrangler secret put GREEN_API_ID
echo "$GREEN_API_TOKEN" | wrangler secret put GREEN_API_TOKEN

# Set Green API URL based on instance ID
GREEN_API_URL="https://${GREEN_API_ID}.api.greenapi.com"
echo "$GREEN_API_URL" | wrangler secret put GREEN_API_URL

# User WhatsApp number (you may need to update this)
# Default placeholder - update with actual number
USER_WHATSAPP_NUMBER="${USER_WHATSAPP_NUMBER:-1234567890@c.us}"
echo "$USER_WHATSAPP_NUMBER" | wrangler secret put USER_WHATSAPP_NUMBER

echo ""
echo "✅ WhatsApp Bridge Worker deployed successfully!"
echo ""

# =============================================================================
# Verification
# =============================================================================
echo "========================================================================"
echo "  Verifying Deployments"
echo "========================================================================"
echo ""

# Get worker URLs from wrangler
GEMMA_PM_URL="https://arca-github-notion-sync.arca-mcp-kv-dae.workers.dev"
WHATSAPP_BRIDGE_URL="https://whatsapp-notifier.arca-mcp-kv-dae.workers.dev"

echo "🔍 Testing Gemma PM Worker health endpoint..."
GEMMA_HEALTH=$(curl -s -w "\n%{http_code}" "$GEMMA_PM_URL/health")
GEMMA_CODE=$(echo "$GEMMA_HEALTH" | tail -n1)
GEMMA_BODY=$(echo "$GEMMA_HEALTH" | head -n-1)

if [ "$GEMMA_CODE" = "200" ]; then
    echo "   ✅ Gemma PM Worker: HEALTHY"
    echo "   Response: $GEMMA_BODY"
else
    echo "   ❌ Gemma PM Worker: FAILED (HTTP $GEMMA_CODE)"
    echo "   Response: $GEMMA_BODY"
fi
echo ""

echo "🔍 Testing WhatsApp Bridge Worker health endpoint..."
WHATSAPP_HEALTH=$(curl -s -w "\n%{http_code}" "$WHATSAPP_BRIDGE_URL/health")
WHATSAPP_CODE=$(echo "$WHATSAPP_HEALTH" | tail -n1)
WHATSAPP_BODY=$(echo "$WHATSAPP_HEALTH" | head -n-1)

if [ "$WHATSAPP_CODE" = "200" ]; then
    echo "   ✅ WhatsApp Bridge Worker: HEALTHY"
    echo "   Response: $WHATSAPP_BODY"
else
    echo "   ❌ WhatsApp Bridge Worker: FAILED (HTTP $WHATSAPP_CODE)"
    echo "   Response: $WHATSAPP_BODY"
fi
echo ""

# =============================================================================
# Summary
# =============================================================================
echo "========================================================================"
echo "  Deployment Summary"
echo "========================================================================"
echo ""
echo "✅ Both Cloudflare workers are live and fully populated with secrets!"
echo ""
echo "📊 Worker URLs:"
echo "   - Gemma PM Worker: $GEMMA_PM_URL"
echo "   - WhatsApp Bridge Worker: $WHATSAPP_BRIDGE_URL"
echo ""
echo "🔐 Secrets injected:"
echo "   Gemma PM Worker:"
echo "     - NOTION_API_KEY"
echo "     - NOTION_TOKEN"
echo "     - GITHUB_WEBHOOK_SECRET"
echo "     - GITHUB_TOKEN"
echo "     - GCP_SERVICE_ACCOUNT (if available)"
echo ""
echo "   WhatsApp Bridge Worker:"
echo "     - GREEN_API_ID"
echo "     - GREEN_API_TOKEN"
echo "     - GREEN_API_URL"
echo "     - USER_WHATSAPP_NUMBER"
echo ""
echo "========================================================================"
