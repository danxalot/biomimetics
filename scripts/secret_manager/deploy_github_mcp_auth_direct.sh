#!/bin/bash
#
# Deploy GitHub MCP Server with API Authentication to Koyeb
# Uses Koyeb's built-in Docker build (no Docker Hub required)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="$SCRIPT_DIR"
APP_NAME="github-mcp-server"
BUILDER_NAME="github-mcp-builder"

echo "🔐 GitHub MCP Auth Gateway - Koyeb Deployment (Direct)"
echo "======================================================"
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
    echo "   Set GITHUB_TOKEN environment variable"
    exit 1
fi

echo "✅ GitHub token configured: ${GITHUB_TOKEN:0:10}..."

# Create builder if it doesn't exist
echo ""
echo "🔨 Setting up Koyeb builder..."
if ! koyeb builder get "$BUILDER_NAME" &>/dev/null; then
    echo "✨ Creating builder: $BUILDER_NAME"
    koyeb builder create "$BUILDER_NAME" --type docker
else
    echo "✅ Builder exists: $BUILDER_NAME"
fi

# Deploy to Koyeb using local Docker build
echo ""
echo "🚀 Deploying to Koyeb..."

# Build locally and push to Koyeb registry
KOYEB_REGISTRY="ghcr.io/koyeb-community"
LOCAL_IMAGE="github-mcp-auth:$(date +%Y%m%d%H%M%S)"

echo "📦 Building Docker image..."
cd "$REDACTEDS_DIR"
docker build -f Dockerfile.github-mcp-auth -t "$LOCAL_IMAGE" .

# Login to Koyeb registry
echo ""
echo "🔐 Logging in to Koyeb registry..."
koyeb registry login

# Tag and push to Koyeb registry
KOYEB_IMAGE="ghcr.io/koyeb-community/$APP_NAME:$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')"
echo ""
echo "📤 Pushing to Koyeb registry: $KOYEB_IMAGE"
docker tag "$LOCAL_IMAGE" "$KOYEB_IMAGE"
docker push "$KOYEB_IMAGE"

# Deploy using Koyeb registry image
if koyeb app get "$APP_NAME" &>/dev/null; then
    echo "📦 Updating existing app: $APP_NAME"
    koyeb app update "$APP_NAME" \
        --docker "$KOYEB_IMAGE" \
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
        --docker "$KOYEB_IMAGE" \
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
sleep 15

# Get endpoint URL
ENDPOINT=$(koyeb app get "$APP_NAME" --format json 2>/dev/null | \
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
    echo "📝 Update Zed config (~/.config/zed/settings.json):"
    cat << EOF
{
  "context_servers": {
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
    echo ""
    
    # Save config snippet
    cat > "$REDACTEDS_DIR/github_mcp_zed_config.json" << EOFCONFIG
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
EOFCONFIG
    echo "💾 Zed config saved to: $REDACTEDS_DIR/github_mcp_zed_config.json"
    
else
    echo "❌ Could not retrieve endpoint URL"
    echo "   Check Koyeb dashboard: https://app.koyeb.com/apps"
    exit 1
fi
