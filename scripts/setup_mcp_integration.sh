#!/bin/bash
#
# MCP Integration Setup for Biomimetics & ARCA
# Configures Zed and Antigravity with GitHub MCP (Azure) and Notion MCP (GCP)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIOMIMETICS_DIR="$(dirname "$SCRIPT_DIR")"
SECRETS_DIR="$BIOMIMETICS_DIR/secrets"

echo "=========================================="
echo "MCP Integration Setup"
echo "=========================================="
echo ""
echo "This script will configure:"
echo "  ✓ Zed Editor"
echo "  ✓ Antigravity"
echo "  ✓ GitHub MCP (Azure SSE)"
echo "  ✓ Notion MCP (GCP)"
echo "  ✓ GCP Gateway (Memory Orchestrator)"
echo ""

# Check for Azure secrets
if [ -f "$SECRETS_DIR/azure_secrets.json" ]; then
    echo "✓ Found Azure secrets backup"
    NOTION_TOKEN=$(python3 -c "import json; print(json.load(open('$SECRETS_DIR/azure_secrets.json')).get('NOTION_API_KEY', ''))")
else
    echo "⚠ No Azure secrets found in $SECRETS_DIR"
    echo "  Using default token from config (update if needed)"
    NOTION_TOKEN="[NOTION_TOKEN_REDACTED]"
fi

if [ -z "$NOTION_TOKEN" ]; then
    echo "✗ NOTION_API_KEY not found"
    echo "  Run: python3 ../azure/azure_secrets_init.py"
    exit 1
fi

# Configuration values
GITHUB_MCP_URL="http://github-mcp-sse.westus2.azurecontainer.io:8080/sse"
GCP_GATEWAY_URL="https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
NOTION_DB_ID="3284d2d9fc7c811188deeeaba9c5f845"

echo ""
echo "Configuration:"
echo "  GitHub MCP: $GITHUB_MCP_URL"
echo "  GCP Gateway: $GCP_GATEWAY_URL"
echo "  Notion DB: $NOTION_DB_ID"
echo ""

# =========================================================
# Zed Editor Configuration
# =========================================================
echo "Configuring Zed Editor..."

ZED_CONFIG_DIR="$HOME/.zed"
ZED_CONFIG_FILE="$ZED_CONFIG_DIR/settings.json"

mkdir -p "$ZED_CONFIG_DIR"

# Create Zed config
cat > "$ZED_CONFIG_FILE" << EOF
{
  "mcp_servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "$NOTION_TOKEN"
      }
    },
    "github": {
      "url": "$GITHUB_MCP_URL",
      "transport": "sse",
      "description": "GitHub MCP via Azure ACI (24/7 remote access)",
      "restricted_tools": [
        "github.create_issue",
        "github.update_issue",
        "github.search_issues",
        "github.get_issue",
        "github.create_pull_request",
        "github.list_pull_requests",
        "github.get_pull_request",
        "github.get_repository"
      ],
      "require_approval_for": [
        "github.create_issue",
        "github.update_issue",
        "github.create_pull_request"
      ]
    }
  },
  "agent_servers": {
    "BiOS_PM": {
      "type": "custom",
      "command": "python3",
      "args": ["~/.copaw/bios_orchestrator.py"],
      "env": {
        "NOTION_DB_ID": "$NOTION_DB_ID",
        "GCP_GATEWAY": "$GCP_GATEWAY_URL"
      }
    }
  },
  "gcp_gateway": {
    "url": "$GCP_GATEWAY_URL",
    "enabled": true,
    "projects": ["biomimetics", "arca"]
  }
}
EOF

echo "✓ Zed Editor configured: $ZED_CONFIG_FILE"

# =========================================================
# Antigravity Configuration
# =========================================================
echo ""
echo "Configuring Antigravity..."

ANTIGRAVITY_DIR="$BIOMIMETICS_DIR/.antigravity"
ANTIGRAVITY_CONFIG="$ANTIGRAVITY_DIR/settings.json"

mkdir -p "$ANTIGRAVITY_DIR"

# Create Antigravity config
cat > "$ANTIGRAVITY_CONFIG" << EOF
{
  "mcp_servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "$NOTION_TOKEN"
      },
      "tools": [
        "search_notion",
        "get_page",
        "create_page",
        "update_page",
        "query_database"
      ]
    },
    "github": {
      "url": "$GITHUB_MCP_URL",
      "transport": "sse",
      "tools": [
        "github.create_issue",
        "github.update_issue",
        "github.search_issues",
        "github.get_issue",
        "github.create_pull_request",
        "github.list_pull_requests",
        "github.get_pull_request",
        "github.get_repository"
      ],
      "require_approval_for": [
        "github.create_issue",
        "github.update_issue",
        "github.create_pull_request"
      ]
    }
  },
  "gcp_gateway": {
    "url": "$GCP_GATEWAY_URL",
    "enabled": true,
    "projects": ["biomimetics", "arca"]
  }
}
EOF

echo "✓ Antigravity configured: $ANTIGRAVITY_CONFIG"

# =========================================================
# Backup configs to secrets directory
# =========================================================
echo ""
echo "Creating backups in secrets directory..."

cp "$ZED_CONFIG_FILE" "$SECRETS_DIR/zed_settings_backup.json" 2>/dev/null || true
cp "$ANTIGRAVITY_CONFIG" "$SECRETS_DIR/antigravity_settings_backup.json" 2>/dev/null || true

echo "✓ Backups created"

# =========================================================
# Test GitHub MCP SSE Endpoint
# =========================================================
echo ""
echo "Testing GitHub MCP SSE endpoint..."

if curl -s --connect-timeout 5 "$GITHUB_MCP_URL" > /dev/null 2>&1; then
    echo "✓ GitHub MCP SSE endpoint reachable"
else
    echo "⚠ GitHub MCP SSE endpoint not reachable"
    echo "  Check Azure container status:"
    echo "  az container show -g arca-mcp-services -n github-mcp-sse"
fi

# =========================================================
# Test GCP Gateway
# =========================================================
echo ""
echo "Testing GCP Gateway..."

if curl -s --connect-timeout 5 -X POST "$GCP_GATEWAY_URL" \
    -H "Content-Type: application/json" \
    -d '{"action": "ping"}' > /dev/null 2>&1; then
    echo "✓ GCP Gateway reachable"
else
    echo "⚠ GCP Gateway not reachable"
    echo "  Check GCP Cloud Function deployment"
fi

# =========================================================
# Summary
# =========================================================
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Configured Files:"
echo "  • Zed: $ZED_CONFIG_FILE"
echo "  • Antigravity: $ANTIGRAVITY_CONFIG"
echo ""
echo "Next Steps:"
echo "  1. Restart Zed Editor to load new config"
echo "  2. Restart Antigravity to load new config"
echo "  3. Test Notion MCP: Search for a page"
echo "  4. Test GitHub MCP: List repositories"
echo "  5. Test GCP Gateway: Query memory"
echo ""
echo "Troubleshooting:"
echo "  • GitHub MCP: az container logs -g arca-mcp-services -n github-mcp-sse"
echo "  • Notion MCP: npx -y @notionhq/notion-mcp-server"
echo "  • GCP Gateway: Check Cloud Functions console"
echo ""
echo "Documentation: docs/MCP_INTEGRATION_STATUS.md"
echo ""
