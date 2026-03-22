#!/bin/bash
#
# Deploy GitHub MCP to Koyeb via Git (No Docker Hub Required)
#
# This script uses Koyeb's Git-based deployment:
# - Pulls code directly from GitHub
# - Builds container on Koyeb infrastructure
# - No Docker Hub account needed
#

set -euo pipefail

echo "=============================================="
echo "GitHub MCP Deployment: Git-Based (Koyeb)"
echo "=============================================="
echo ""

# Configuration
ARCA_SECRETS_DIR="${ARCA_SECRETS_DIR:-/Users/danexall/Documents/VS Code Projects/ARCA/.secrets}"
GITHUB_MCP_DIR="${GITHUB_MCP_DIR:-/Users/danexall/github-mcp-super-gateway}"
KOYEB_APP_NAME="${KOYEB_APP_NAME:-github-mcp-server}"
KOYEB_TOKEN="${KOYEB_TOKEN:-ov7hvgjlgi7m3yqil12aufkgoeejj2gqbtnkq8q7voz29m011nphncevyuqbva4g}"
GITHUB_REPO="${GITHUB_REPO:-github.com/danxalot/biomimetics}"
GIT_BRANCH="${GIT_BRANCH:-main}"
GIT_PATH="${GIT_PATH:-github-mcp-super-gateway}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Step 1: Prerequisites Check${NC}"
echo "─────────────────────────────────────────"

# Check for Koyeb CLI
if ! command -v koyeb &> /dev/null; then
    echo -e "${RED}✗ Koyeb CLI not found${NC}"
    echo ""
    echo "Install with: brew tap koyeb/tap && brew install koyeb/tap/koyeb"
    exit 1
fi
KOYEB_VERSION=$(koyeb version 2>&1)
echo -e "${GREEN}✓ Koyeb CLI: $KOYEB_VERSION${NC}"

# Check Koyeb auth with organization token
if ! koyeb app list --token "$KOYEB_TOKEN" &> /dev/null; then
    echo -e "${RED}✗ Koyeb authentication failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Authenticated to Koyeb (organization token)${NC}"

# Check for Dockerfile
if [ ! -f "$GITHUB_MCP_DIR/Dockerfile" ]; then
    echo -e "${RED}✗ Dockerfile not found at $GITHUB_MCP_DIR${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Dockerfile found: $GITHUB_MCP_DIR/Dockerfile${NC}"

# Check for GitHub token (for environment variable)
if [ ! -f "$ARCA_SECRETS_DIR/github_token" ]; then
    echo -e "${RED}✗ GitHub token not found${NC}"
    exit 1
fi
GITHUB_PAT=$(cat "$ARCA_SECRETS_DIR/github_token" | tr -d '\n')
echo -e "${GREEN}✓ GitHub token found${NC}"

echo ""
echo -e "${YELLOW}Step 2: Deploy via Git${NC}"
echo "─────────────────────────────────────────"
echo "Repository: $GITHUB_REPO"
echo "Branch: $GIT_BRANCH"
echo "Dockerfile Path: $GIT_PATH/Dockerfile"
echo ""

# Check if app exists
if koyeb apps get "$KOYEB_APP_NAME" --token "$KOYEB_TOKEN" &> /dev/null; then
    echo "App exists, creating service..."
    
    # Create new service in existing app with Git builder
    koyeb services create main \
        --app "$KOYEB_APP_NAME" \
        --token "$KOYEB_TOKEN" \
        --git "$GITHUB_REPO" \
        --git-branch "$GIT_BRANCH" \
        --git-builder docker \
        --git-docker-dockerfile "$GIT_PATH/Dockerfile" \
        --env GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_PAT" \
        --port 8080:http \
        --route /:8080 \
        --instance-type free
else
    echo "Creating new app with Git deployment..."
    
    # Create new app with Git builder
    koyeb apps create "$KOYEB_APP_NAME" --token "$KOYEB_TOKEN"
    
    koyeb services create main \
        --app "$KOYEB_APP_NAME" \
        --token "$KOYEB_TOKEN" \
        --git "$GITHUB_REPO" \
        --git-branch "$GIT_BRANCH" \
        --git-builder docker \
        --git-dockerfile "$GIT_PATH/Dockerfile" \
        --env GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_PAT" \
        --port 8080:http \
        --route /:8080 \
        --instance-type free
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Deployment failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Deployment initiated${NC}"

echo ""
echo -e "${YELLOW}Step 3: Wait for Build${NC}"
echo "─────────────────────────────────────────"
echo "Waiting for Koyeb to build from Git (this may take 3-5 minutes)..."
sleep 60

# Get deployment status
DEPLOYMENT_STATUS=$(koyeb app get "$KOYEB_APP_NAME" --token "$KOYEB_TOKEN" --format json 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin)['services'][0]['deployments'][0]['status'])" 2>/dev/null || echo "BUILDING")
echo "Deployment status: $DEPLOYMENT_STATUS"

if [ "$DEPLOYMENT_STATUS" != "SUCCESSFUL" ]; then
    echo -e "${YELLOW}⚠ Build may still be in progress${NC}"
    echo "Check status at: https://app.koyeb.com/apps/$KOYEB_APP_NAME"
    echo ""
    echo "View build logs:"
    echo "  koyeb service logs $KOYEB_APP_NAME/main --token $KOYEB_TOKEN"
fi

echo ""
echo -e "${YELLOW}Step 4: Get Endpoint URL${NC}"
echo "─────────────────────────────────────────"

ENDPOINT_URL=$(koyeb app get "$KOYEB_APP_NAME" --token "$KOYEB_TOKEN" --format json 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin)['services'][0]['endpoints'][0]['url'])" 2>/dev/null || echo "UNKNOWN")

if [ "$ENDPOINT_URL" != "UNKNOWN" ]; then
    echo -e "${GREEN}✓ Service deployed${NC}"
    echo "  App: $KOYEB_APP_NAME"
    echo "  URL: https://$ENDPOINT_URL"
    echo "  SSE Endpoint: https://$ENDPOINT_URL/sse"
    echo "  MCP Endpoint: https://$ENDPOINT_URL/mcp"
else
    echo -e "${YELLOW}⚠ Could not retrieve endpoint URL${NC}"
    echo "Check at: https://app.koyeb.com/apps/$KOYEB_APP_NAME"
    ENDPOINT_URL="YOUR-APP.koyeb.app"
fi

echo ""
echo -e "${YELLOW}Step 5: Test Endpoint${NC}"
echo "─────────────────────────────────────────"
echo "Testing SSE endpoint..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "https://$ENDPOINT_URL/sse" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ Endpoint responding (HTTP $HTTP_CODE)${NC}"
else
    echo -e "${YELLOW}⚠ Endpoint not yet ready (HTTP $HTTP_CODE)${NC}"
    echo "Build may still be in progress. Check logs:"
    echo "  koyeb service logs $KOYEB_APP_NAME/main --token $KOYEB_TOKEN"
fi

echo ""
echo "=============================================="
echo -e "${GREEN}Deployment Complete!${NC}"
echo "=============================================="
echo ""
echo "New GitHub MCP Endpoint:"
echo "  https://$ENDPOINT_URL/sse"
echo ""
echo "Update your configurations:"
echo ""
echo "1. Zed Editor (~/.zed/settings.json):"
echo '   {'
echo '     "mcp_servers": {'
echo '       "github": {'
echo "         \"url\": \"https://$ENDPOINT_URL/sse\","
echo '         "transport": "sse"'
echo '       }'
echo '     }'
echo '   }'
echo ""
echo "2. Antigravity (~/biomimetics/.antigravity/settings.json):"
echo '   {'
echo '     "mcp_servers": {'
echo '       "github": {'
echo "         \"url\": \"https://$ENDPOINT_URL/sse\","
echo '         "transport": "sse"'
echo '       }'
echo '     }'
echo '   }'
echo ""
echo "3. CoPaw (~/.copaw/config.json):"
echo '   {'
echo '     "mcp_servers": {'
echo '       "github": {'
echo "         \"url\": \"https://$ENDPOINT_URL/sse\","
echo '         "transport": "sse"'
echo '       }'
echo '     }'
echo '   }'
echo ""
echo "=============================================="
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Update client configurations (see above)"
echo "2. Test GitHub MCP from Zed/Antigravity"
echo "3. Delete Azure container to stop billing:"
echo "   cd ~/biomimetics && ./scripts/migrate/azure-teardown.sh --yes"
echo ""
echo "View build logs:"
echo "  koyeb service logs $KOYEB_APP_NAME/main --token $KOYEB_TOKEN"
echo ""
