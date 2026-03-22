#!/bin/bash
# Phase 4 Complete Setup Script
# Configures Azure GitHub MCP, Serena, and Tool Guard

set -e

echo "=============================================="
echo "Phase 4: Autonomous IDE Setup"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Make scripts executable
chmod +x /Users/danexall/phase4-azure-deploy.sh
chmod +x /Users/danexall/phase4-keyvault-setup.sh
chmod +x /Users/danexall/serena-memory-sync.py
chmod +x /Users/danexall/copaw-tool-guard.py

echo -e "\n${YELLOW}Step 1: Azure Key Vault Setup${NC}"
echo "Run: /Users/danexall/phase4-keyvault-setup.sh"
echo ""

echo -e "\n${YELLOW}Step 2: Azure GitHub MCP Deployment${NC}"
echo "Run: /Users/danexall/phase4-azure-deploy.sh"
echo ""

echo -e "\n${YELLOW}Step 3: Initialize Serena MCP${NC}"
echo "Running: uvx mcp-server-serena --help"
uvx mcp-server-serena --help 2>&1 | head -20 || {
    echo -e "${YELLOW}⚠ Serena not available via uvx${NC}"
    echo "Install with: pip install mcp-server-serena"
}

echo -e "\n${YELLOW}Step 4: Create Serena memories directory${NC}"
mkdir -p ~/.serena/memories
echo -e "${GREEN}✓ Created ~/.serena/memories${NC}"

echo -e "\n${YELLOW}Step 5: Install Serena sync dependencies${NC}"
pip3 install httpx --quiet 2>&1 | tail -3

echo -e "\n${YELLOW}Step 6: Configure Copaw${NC}"
# Backup existing config
if [ -f ~/.copaw/config.json ]; then
    cp ~/.copaw/config.json ~/.copaw/config.json.backup
    echo -e "${GREEN}✓ Backed up existing config${NC}"
fi

# Copy Phase 4 config
cp /Users/danexall/.copaw/config-phase4.json ~/.copaw/config.json
echo -e "${GREEN}✓ Copaw config updated${NC}"

echo -e "\n${YELLOW}Step 7: Create launchd service for Serena sync${NC}"
cat > ~/Library/LaunchAgents/com.arca.serena-sync.plist << 'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arca.serena-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/danexall/serena-memory-sync.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/danexall</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/danexall/.arca/serena-sync.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/danexall/.arca/serena-sync.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>GCP_GATEWAY_URL</key>
        <string>https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator</string>
        <key>SERENA_SYNC_INTERVAL</key>
        <string>300</string>
    </dict>
</dict>
</plist>
PLISTEOF

echo -e "${GREEN}✓ Serena sync launchd service created${NC}"

echo -e "\n${YELLOW}Step 8: Create Notion approval database template${NC}"
cat > /Users/danexall/notion-approval-db-template.json << 'DBEOF'
{
  "parent": { "type": "workspace", "workspace": true },
  "title": [
    { "type": "text", "text": { "content": "Copaw Tool Approvals" } }
  ],
  "properties": {
    "Name": { "title": {} },
    "Status": { "select": { "options": [
      { "name": "Pending", "color": "yellow" },
      { "name": "Approved", "color": "green" },
      { "name": "Denied", "color": "red" }
    ]} },
    "Tool": { "rich_text": {} },
    "Arguments": { "rich_text": {} },
    "Context": { "rich_text": {} },
    "Approval ID": { "rich_text": {} },
    "Requested": { "date": {} },
    "Approved/Denied": { "date": {} }
  }
}
DBEOF

echo -e "${GREEN}✓ Notion template created${NC}"
echo "Create database in Notion using this template, then set NOTION_APPROVAL_DB_ID"

# Summary
echo -e "\n${GREEN}=============================================="
echo "Phase 4 Setup Complete!"
echo "==============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. ${YELLOW}Set up Azure Key Vault:${NC}"
echo "   /Users/danexall/phase4-keyvault-setup.sh"
echo ""
echo "2. ${YELLOW}Deploy GitHub MCP to Azure:${NC}"
echo "   /Users/danexall/phase4-azure-deploy.sh"
echo ""
echo "3. ${YELLOW}Start Serena sync service:${NC}"
echo "   launchctl load ~/Library/LaunchAgents/com.arca.serena-sync.plist"
echo ""
echo "4. ${YELLOW}Create Notion approval database:${NC}"
echo "   - Use the template at: /Users/danexall/notion-approval-db-template.json"
echo "   - Set NOTION_APPROVAL_DB_ID environment variable"
echo ""
echo "5. ${YELLOW}Configure environment variables:${NC}"
echo "   export AZURE_RESOURCE_GROUP=arca-mcp-services"
echo "   export AZURE_KEY_VAULT_NAME=arca-vault"
echo "   export NOTION_APPROVAL_DB_ID=your-database-id"
echo "   export TELEGRAM_BOT_TOKEN=your-bot-token (optional)"
echo "   export TELEGRAM_CHAT_ID=your-chat-id (optional)"
echo ""
echo "6. ${YELLOW}Test the workflow:${NC}"
echo "   - Create a task in Notion with 'Plan Feature' action"
echo "   - Copaw will query MemU for architecture context"
echo "   - GitHub MCP creates issue in Azure"
echo "   - Serena provides code intelligence"
echo "   - High-risk actions require Notion/Telegram approval"
echo ""
echo "=============================================="
