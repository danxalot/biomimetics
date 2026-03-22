#!/bin/bash
# Phase 2 Setup Script
# Configures Cloudflare Tunnel, email daemon, and Obsidian sync

set -e

echo "=============================================="
echo "Phase 2: Secure Connectivity & Ingestion Setup"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create directories
echo -e "\n${YELLOW}Creating directories...${NC}"
mkdir -p ~/.arca
mkdir -p ~/.cloudflared
mkdir -p ~/Library/LaunchAgents

# Install Python dependencies
echo -e "\n${YELLOW}Installing Python dependencies...${NC}"
pip3 install -r phase2-requirements.txt

# Check cloudflared
echo -e "\n${YELLOW}Checking cloudflared...${NC}"
if command -v cloudflared &> /dev/null; then
    echo -e "${GREEN}✓ cloudflared installed$(NC)"
    cloudflared --version
else
    echo -e "${RED}✗ cloudflared not found${NC}"
    echo "Install with: brew install cloudflared"
    exit 1
fi

# Check for existing tunnel
echo -e "\n${YELLOW}Checking Cloudflare tunnel configuration...${NC}"
if [ -f ~/.cloudflared/copaw-tunnel.yml ]; then
    echo -e "${GREEN}✓ Tunnel config exists${NC}"
else
    echo -e "${YELLOW}Creating tunnel configuration...${NC}"
    # Tunnel config should be created manually via cloudflared tunnel command
    echo "Run: cloudflared tunnel run bfa05acf-f0f3-41b0-92ae-93325f8f1631"
fi

# Create launchd plist for webhook receiver
echo -e "\n${YELLOW}Creating launchd service for webhook receiver...${NC}"
cat > ~/Library/LaunchAgents/com.arca.copaw-webhook.plist << 'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arca.copaw-webhook</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/danexall/copaw-webhook-receiver.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/danexall</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/danexall/.arca/copaw-webhook.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/danexall/.arca/copaw-webhook.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PORT</key>
        <string>8000</string>
        <key>GCP_GATEWAY_URL</key>
        <string>https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator</string>
    </dict>
</dict>
</plist>
PLISTEOF

echo -e "${GREEN}✓ Webhook receiver plist created${NC}"

# Create launchd plist for email daemon
echo -e "\n${YELLOW}Creating launchd service for email daemon...${NC}"
cat > ~/Library/LaunchAgents/com.arca.email-daemon.plist << 'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arca.email-daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/danexall/email-ingestion-daemon.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/danexall</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/danexall/.arca/email-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/danexall/.arca/email-daemon.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>POLL_INTERVAL</key>
        <string>60</string>
        <key>GCP_GATEWAY_URL</key>
        <string>https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator</string>
        <key>WEBHOOK_RECEIVER_URL</key>
        <string>http://localhost:8000/email</string>
    </dict>
</dict>
</plist>
PLISTEOF

echo -e "${GREEN}✓ Email daemon plist created${NC}"

# Create cron job for Obsidian sync
echo -e "\n${YELLOW}Setting up cron job for Obsidian sync...${NC}"
CRON_JOB="0 * * * * /usr/bin/python3 /Users/danexall/obsidian-sync-skill.py >> /Users/danexall/.arca/obsidian-sync.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "obsidian-sync-skill"; then
    echo -e "${GREEN}✓ Obsidian sync cron job already exists${NC}"
else
    echo -e "${YELLOW}Adding cron job...${NC}"
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo -e "${GREEN}✓ Cron job added (runs hourly)${NC}"
fi

# Make scripts executable
echo -e "\n${YELLOW}Making scripts executable...${NC}"
chmod +x /Users/danexall/copaw-webhook-receiver.py
chmod +x /Users/danexall/email-ingestion-daemon.py
chmod +x /Users/danexall/obsidian-sync-skill.py

echo -e "${GREEN}✓ Scripts made executable${NC}"

# Summary
echo -e "\n${GREEN}=============================================="
echo "Setup Complete!"
echo "==============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. ${YELLOW}Start Cloudflare Tunnel:${NC}"
echo "   cloudflared tunnel run bfa05acf-f0f3-41b0-92ae-93325f8f1631"
echo ""
echo "2. ${YELLOW}Start webhook receiver:${NC}"
echo "   launchctl load ~/Library/LaunchAgents/com.arca.copaw-webhook.plist"
echo ""
echo "3. ${YELLOW}Start email daemon:${NC}"
echo "   launchctl load ~/Library/LaunchAgents/com.arca.email-daemon.plist"
echo ""
echo "4. ${YELLOW}Configure environment variables:${NC}"
echo "   - PROTONMAIL_USER, PROTONMAIL_PASS (for ProtonMail Bridge)"
echo "   - NOTION_API_KEY, NOTION_EMAIL_DB_ID (for Notion tracking)"
echo "   - OBSIDIAN_VAULT_PATH (path to SMB-mounted vault)"
echo ""
echo "5. ${YELLOW}Test Obsidian sync manually:${NC}"
echo "   python3 /Users/danexall/obsidian-sync-skill.py"
echo ""
echo "=============================================="
