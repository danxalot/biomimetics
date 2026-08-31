#!/bin/bash
#
# Deploy GitHub MCP Server with API Authentication to Koyeb
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="$SCRIPT_DIR"
DOCKERFILE="$REDACTEDS_DIR/Dockerfile.github-mcp-auth"
APP_NAME="github-mcp-server"
IMAGE_NAME="danxalot/github-mcp-server:auth"

echo "🔐 GitHub MCP Auth Gateway - Koyeb Deployment"
echo "=============================================="
echo ""

# Check Koyeb login
if ! koyeb app list &>/dev/null; then
    echo "❌ Not logged in to Koyeb"
    echo "Run: koyeb login"
    exit 1
fi

echo "✅ Logged in to Koyeb"

# Generate or use existing API key
if [ -f "$REDACTEDS_DIR/github_mcp_api_key" ]; then
    API_KEY=$(cat "$REDACTEDS_DIR/github_mcp_api_key")
    echo "✅ Using existing API key: ${API_KEY:0:8}..."
else
    API_KEY=$(openssl rand -hex 32)
    echo "$API_KEY" > "$REDACTEDS_DIR/github_mcp_api_key"
    chmod 600 "$REDACTEDS_DIR/github_mcp_api_key"
    echo "🔑 Generated new API key: ${API_KEY:0:8}..."
    echo "   Saved to: $REDACTEDS_DIR/github_mcp_api_key"
fi

# Get GitHub token from Azure Key Vault or environment
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$GITHUB_TOKEN" ]; then
    if command -v az &>/dev/null; then
        GITHUB_TOKEN=$(az keyvault secret show \
            --vault-name arca-mcp-kv-dae \
            --name github-token \
            --query value -o tsv 2>/dev/null || echo "")
    fi
fi

if [ -z "$GITHUB_TOKEN" ]; then
    echo "⚠️  GITHUB_TOKEN not set and not found in Azure Key Vault"
    echo "   Set GITHUB_TOKEN environment variable or add to Azure Key Vault"
    exit 1
fi

echo "✅ GitHub token configured: ${GITHUB_TOKEN:0:10}..."

# Build Docker image
echo ""
echo "🔨 Building Docker image..."
cd "$REDACTEDS_DIR"
docker build -f Dockerfile.github-mcp-auth -t "$IMAGE_NAME" .

# Push to Docker Hub
echo ""
echo "📤 Pushing to Docker Hub..."
docker push "$IMAGE_NAME"

# Deploy to Koyeb
echo ""
echo "🚀 Deploying to Koyeb..."

# Check if app exists
if koyeb app get "$APP_NAME" &>/dev/null; then
    echo "📦 Updating existing app: $APP_NAME"
    koyeb app update "$APP_NAME" \
        --docker "$IMAGE_NAME" \
        --env GITHUB_TOKEN="$GITHUB_TOKEN" \
        --env API_KEY="$API_KEY" \
        --env PORT="8080" \
        --ports 8080:http \
        --instance-type nano \
        --regions fra \
        --name "$APP_NAME"
else
    echo "✨ Creating new app: $APP_NAME"
    koyeb app create "$APP_NAME" \
        --docker "$IMAGE_NAME" \
        --env GITHUB_TOKEN="$GITHUB_TOKEN" \
        --env API_KEY="$API_KEY" \
        --env PORT="8080" \
        --ports 8080:http \
        --instance-type nano \
        --regions fra
fi

# Wait for deployment
echo ""
echo "⏳ Waiting for deployment..."
sleep 10

# Get endpoint URL
ENDPOINT=$(koyeb app get "$APP_NAME" --format json | \
    python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('services', [{}])[0].get('endpoints', [{}])[0].get('url', ''))" 2>/dev/null || echo "")

if [ -n "$ENDPOINT" ]; then
    echo ""
    echo "✅ Deployment complete!"
    echo ""
    echo "📡 Endpoint: https://$ENDPOINT"
    echo "🔐 SSE URL: https://$ENDPOINT/sse"
    echo "🔑 API Key: ${API_KEY:0:8}... (full key in $REDACTEDS_DIR/github_mcp_api_key)"
    echo ""
    echo "📋 Test authentication:"
    echo "   # Without API key (should fail):"
    echo "   curl -I https://$ENDPOINT/sse"
    echo ""
    echo "   # With API key (should succeed):"
    echo "   curl -H 'X-API-Key: $API_KEY' -I https://$ENDPOINT/sse"
    echo ""
    echo "📝 Update Zed config (~/.zed/settings.json):"
    echo "   {"
    echo "     \"mcp_servers\": {"
    echo "       \"github\": {"
    echo "         \"url\": \"https://$ENDPOINT/sse\","
    echo "         \"transport\": \"sse\","
    echo "         \"headers\": {"
    echo "           \"X-API-Key\": \"$API_KEY\""
    echo "         }"
    echo "       }"
    echo "     }"
    echo "   }"
    echo ""
    
    # Save config snippet
    cat > "$REDACTEDS_DIR/github_mcp_zed_config.json" << EOF
{
  "mcp_servers": {
    "github": {
      "url": "https://$ENDPOINT/sse",
      "transport": "sse",
      "headers": {
        "X-API-Key": "$API_KEY"
      }
    }
  }
}
EOF
    echo "💾 Zed config saved to: $REDACTEDS_DIR/github_mcp_zed_config.json"
    
else
    echo "❌ Could not retrieve endpoint URL"
    echo "   Check Koyeb dashboard: https://app.koyeb.com/apps"
    exit 1
fi
