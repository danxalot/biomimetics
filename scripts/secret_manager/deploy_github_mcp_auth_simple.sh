#!/bin/bash
#
# Deploy GitHub MCP Server with API Authentication to Koyeb
# Simple deployment using existing Docker Hub repo
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="$SCRIPT_DIR"
APP_NAME="github-mcp-server"
IMAGE_NAME="danxalot/github-mcp-server"
TAG="auth-$(date +%Y%m%d%H%M%S)"

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
    echo "   Set GITHUB_TOKEN environment variable"
    exit 1
fi

echo "✅ GitHub token configured: ${GITHUB_TOKEN:0:10}..."

# Build Docker image
echo ""
echo "🔨 Building Docker image..."
cd "$REDACTEDS_DIR"
docker build -f Dockerfile.github-mcp-auth -t "$IMAGE_NAME:$TAG" .

# Tag as latest too
docker tag "$IMAGE_NAME:$TAG" "$IMAGE_NAME:auth"

echo ""
echo "📦 Image built successfully"
echo "   $IMAGE_NAME:$TAG"
echo "   $IMAGE_NAME:auth"
echo ""
echo "⚠️  Next steps (manual push to Docker Hub):"
echo ""
echo "   1. Login to Docker Hub:"
echo "      docker login"
echo ""
echo "   2. Push the image:"
echo "      docker push $IMAGE_NAME:$TAG"
echo "      docker push $IMAGE_NAME:auth"
echo ""
echo "   3. Deploy to Koyeb:"
echo "      koyeb app update $APP_NAME --docker $IMAGE_NAME:auth"
echo "      koyeb app update $APP_NAME --env API_KEY='$API_KEY'"
echo "      koyeb app update $APP_NAME --env GITHUB_TOKEN='$GITHUB_TOKEN'"
echo ""
echo "💾 Saving deployment commands..."

# Save deployment commands
cat > "$REDACTEDS_DIR/deploy_commands.sh" << EOF
#!/bin/bash
# Deployment commands for GitHub MCP Auth Gateway

IMAGE_NAME="$IMAGE_NAME"
TAG="$TAG"
API_KEY="$API_KEY"
GITHUB_TOKEN="${GITHUB_TOKEN:0:10}..."
APP_NAME="$APP_NAME"

echo "Pushing to Docker Hub..."
docker push \$IMAGE_NAME:\$TAG
docker push \$IMAGE_NAME:auth

echo "Deploying to Koyeb..."
koyeb app update \$APP_NAME \
    --docker \$IMAGE_NAME:auth \
    --env API_KEY="$API_KEY" \
    --env GITHUB_TOKEN="$GITHUB_TOKEN" \
    --env PORT="8080" \
    --ports 8080:http \
    --instance-type nano \
    --regions fra

echo "Done!"
EOF

chmod +x "$REDACTEDS_DIR/deploy_commands.sh"
echo "✅ Deployment script saved: $REDACTEDS_DIR/deploy_commands.sh"

# Save Zed config
cat > "$REDACTEDS_DIR/github_mcp_zed_config.json" << EOF
{
  "mcp_servers": {
    "github": {
      "url": "https://github-mcp-server-arca-vsa-3c648978.koyeb.app/sse",
      "transport": "sse",
      "headers": {
        "X-API-Key": "$API_KEY"
      }
    }
  }
}
EOF

echo "💾 Zed config saved: $REDACTEDS_DIR/github_mcp_zed_config.json"
echo ""
echo "📋 After pushing to Docker Hub and deploying, update Zed config with the API key above."
