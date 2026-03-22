#!/bin/bash
# Phase 6 Setup Script
# Omni-Sync Daemon for unified inbox and file pipeline

set -e

echo "=============================================="
echo "Phase 6: Unified Inbox & File Pipeline Setup"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Make scripts executable
chmod +x /Users/danexall/omni_sync.py

echo -e "\n${YELLOW}Step 1: Install Python dependencies${NC}"
pip3 install -r /Users/danexall/omni_sync_requirements.txt 2>&1 | tail -10
echo -e "${GREEN}✓ Dependencies installed${NC}"

echo -e "\n${YELLOW}Step 2: Create configuration file${NC}"
if [ ! -f /Users/danexall/omni_sync_config.json ]; then
    cp /Users/danexall/omni_sync_config.example.json /Users/danexall/omni_sync_config.json
    echo -e "${GREEN}✓ Config file created${NC}"
    echo "Edit /Users/danexall/omni_sync_config.json with your credentials"
else
    echo -e "${GREEN}✓ Config file exists${NC}"
fi

echo -e "\n${YELLOW}Step 3: Create state directory${NC}"
mkdir -p ~/.arca/omni_sync
echo -e "${GREEN}✓ State directory created${NC}"

echo -e "\n${YELLOW}Step 4: Create launchd service${NC}"
cp /Users/danexall/com.arca.omni-sync.plist ~/Library/LaunchAgents/
echo -e "${GREEN}✓ launchd service created${NC}"

echo -e "\n${YELLOW}Step 5: Test single sync cycle${NC}"
python3 /Users/danexall/omni_sync.py --config /Users/danexall/omni_sync_config.json --once 2>&1 | tail -20

# Summary
echo -e "\n${GREEN}=============================================="
echo "Phase 6 Setup Complete!"
echo "==============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. ${YELLOW}Configure credentials:${NC}"
echo "   Edit /Users/danexall/omni_sync_config.json"
echo "   - ProtonMail Bridge credentials"
echo "   - Gmail App Password"
echo "   - Notion API key and database ID"
echo "   - Google Drive credentials (optional)"
echo ""
echo "2. ${YELLOW}Start the daemon:${NC}"
echo "   launchctl load ~/Library/LaunchAgents/com.arca.omni-sync.plist"
echo ""
echo "3. ${YELLOW}Monitor logs:${NC}"
echo "   tail -f ~/.arca/omni_sync.log"
echo ""
echo "4. ${YELLOW}Test manually:${NC}"
echo "   python3 /Users/danexall/omni_sync.py --config /Users/danexall/omni_sync_config.json --once"
echo ""
echo "=============================================="
echo ""
echo "Features:"
echo "  ✅ ProtonMail sync (via Bridge)"
echo "  ✅ Gmail sync (via IMAP)"
echo "  ✅ Google Drive sync (via API)"
echo "  ✅ MyCloud Home SMB sync"
echo "  ✅ Notion inbox tracking"
echo "  ✅ Memory Gateway integration"
echo "  ✅ Duplicate prevention"
echo "  ✅ Background daemon mode"
echo ""
echo "=============================================="
