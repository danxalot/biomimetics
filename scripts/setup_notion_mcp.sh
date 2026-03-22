#!/bin/bash
#
# Notion MCP Server Setup for Biomimetics
# Installs and configures Notion MCP for Claude Desktop and other MCP clients
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIOMIMETICS_DIR="$(dirname "$SCRIPT_DIR")"
SECRETS_DIR="$BIOMIMETICS_DIR/secrets"

echo "Notion MCP Server Setup"
echo "======================="
echo ""

# Check for Azure secrets
if [ -f "$SECRETS_DIR/azure_secrets.json" ]; then
    echo "✓ Found Azure secrets backup"
    NOTION_TOKEN=$(python3 -c "import json; print(json.load(open('$SECRETS_DIR/azure_secrets.json')).get('NOTION_API_KEY', ''))")
else
    echo "✗ No Azure secrets found. Run azure_secrets_init.py first."
    echo ""
    echo "Usage: python3 ../azure/azure_secrets_init.py"
    exit 1
fi

if [ -z "$NOTION_TOKEN" ]; then
    echo "✗ NOTION_API_KEY not found in secrets"
    exit 1
fi

# Create Notion MCP config
MCP_CONFIG=$(cat <<EOF
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "$NOTION_TOKEN"
      }
    }
  }
}
EOF
)

# Install Notion MCP globally
echo "Installing Notion MCP Server..."
npm install -g @notionhq/notion-mcp-server 2>/dev/null || {
    echo "✓ Notion MCP already installed or using npx"
}

# Update Claude Desktop config
CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [ -f "$CLAUDE_CONFIG" ]; then
    echo "Updating Claude Desktop config..."
    python3 << PYTHON
import json

with open("$CLAUDE_CONFIG", 'r') as f:
    config = json.load(f)

config['mcpServers'] = config.get('mcpServers', {})
config['mcpServers']['notion'] = $MCP_CONFIG['mcpServers']['notion']

with open("$CLAUDE_CONFIG", 'w') as f:
    json.dump(config, f, indent=2)

print("✓ Updated: $CLAUDE_CONFIG")
PYTHON
else
    echo "Creating Claude Desktop config..."
    mkdir -p "$(dirname "$CLAUDE_CONFIG")"
    echo "$MCP_CONFIG" > "$CLAUDE_CONFIG"
    echo "✓ Created: $CLAUDE_CONFIG"
fi

# Update Qwen config if exists
QWEN_CONFIG="$HOME/.qwen/settings.json"
if [ -f "$QWEN_CONFIG" ]; then
    echo "Updating Qwen config..."
    python3 << PYTHON
import json

with open("$QWEN_CONFIG", 'r') as f:
    config = json.load(f)

config['mcpServers'] = config.get('mcpServers', {})
config['mcpServers']['notion'] = $MCP_CONFIG['mcpServers']['notion']

with open("$QWEN_CONFIG", 'w') as f:
    json.dump(config, f, indent=2)

print("✓ Updated: $QWEN_CONFIG")
PYTHON
fi

# Save MCP config to secrets directory
echo "$MCP_CONFIG" > "$SECRETS_DIR/notion_mcp_config.json"
echo "✓ Saved: $SECRETS_DIR/notion_mcp_config.json"

echo ""
echo "Notion MCP Server configured!"
echo ""
echo "To test:"
echo "  npx -y @notionhq/notion-mcp-server"
echo ""
echo "Restart Claude Desktop or Qwen to load the Notion MCP integration."
