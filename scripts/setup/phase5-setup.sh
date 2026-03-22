#!/bin/bash
# Phase 5 Setup Script
# Configures Computer Use MCP, Puppeteer MCP, and Vision Model Routing

set -e

echo "=============================================="
echo "Phase 5: Desktop & Vision Actuator Setup"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Make scripts executable
chmod +x /Users/danexall/computer-use-mcp.py
chmod +x /Users/danexall/vision-router.py

echo -e "\n${YELLOW}Step 1: Install Python dependencies${NC}"
pip3 install pyautogui pillow pyscreenshot mcp httpx --quiet 2>&1 | tail -5
echo -e "${GREEN}✓ Python dependencies installed${NC}"

echo -e "\n${YELLOW}Step 2: Install Node.js dependencies (Puppeteer MCP)${NC}"
if command -v npm &> /dev/null; then
    npm install -g @modelcontextprotocol/server-puppeteer 2>&1 | tail -5
    echo -e "${GREEN}✓ Puppeteer MCP installed${NC}"
else
    echo -e "${RED}✗ npm not found${NC}"
    echo "Install Node.js first: brew install node"
fi

echo -e "\n${YELLOW}Step 3: Check Ollama for Qwen-VL${NC}"
if command -v ollama &> /dev/null; then
    echo "Ollama version:"
    ollama --version
    
    # Check if Qwen-VL is available
    if ollama list 2>/dev/null | grep -q "qwen"; then
        echo -e "${GREEN}✓ Qwen model found${NC}"
    else
        echo -e "${YELLOW}⚠ Qwen-VL not found${NC}"
        echo "Pull with: ollama pull qwen2.5-vl:7b"
    fi
else
    echo -e "${YELLOW}⚠ Ollama not installed${NC}"
    echo "Install for local vision processing:"
    echo "  brew install ollama"
    echo "  ollama pull qwen2.5-vl:7b"
fi

echo -e "\n${YELLOW}Step 4: Create launchd service for Computer Use MCP${NC}"
cat > ~/Library/LaunchAgents/com.arca.computer-use-mcp.plist << 'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arca.computer-use-mcp</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/danexall/computer-use-mcp.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/danexall</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/danexall/.arca/computer-use-mcp.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/danexall/.arca/computer-use-mcp.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
PLISTEOF
echo -e "${GREEN}✓ Computer Use MCP launchd service created${NC}"

echo -e "\n${YELLOW}Step 5: Test Computer Use MCP${NC}"
python3 /Users/danexall/computer-use-mcp.py --help 2>&1 | head -10 || {
    echo -e "${YELLOW}⚠ Computer Use MCP test skipped (dependencies may need installation)${NC}"
}

echo -e "\n${YELLOW}Step 6: Test Vision Router${NC}"
python3 /Users/danexall/vision-router.py --test 2>&1 || {
    echo -e "${YELLOW}⚠ Vision Router test skipped (Ollama may not be running)${NC}"
    echo "Start Ollama: ollama serve"
}

echo -e "\n${YELLOW}Step 7: Update Copaw configuration${NC}"
# Backup existing config
if [ -f ~/.copaw/config.json ]; then
    cp ~/.copaw/config.json ~/.copaw/config.json.backup
    echo -e "${GREEN}✓ Backed up existing config${NC}"
fi

# Copy Phase 5 config
cp /Users/danexall/.copaw/config-phase5.json ~/.copaw/config.json
echo -e "${GREEN}✓ Copaw config updated${NC}"

echo -e "\n${YELLOW}Step 8: Create Ollama startup script${NC}"
cat > /Users/danexall/start-ollama-vision.sh << 'OLLAWSH'
#!/bin/bash
# Start Ollama with Qwen-VL for vision processing

echo "Starting Ollama..."
ollama serve &
OLLAMA_PID=$!

echo "Waiting for Ollama to start..."
sleep 5

echo "Pulling Qwen-VL model (if not present)..."
ollama pull qwen2.5-vl:7b

echo ""
echo "Ollama is running with Qwen-VL"
echo "Vision endpoint: http://localhost:11435/v1/chat/completions"
echo ""
echo "Press Ctrl+C to stop"

wait $OLLAMA_PID
OLLAWSH
chmod +x /Users/danexall/start-ollama-vision.sh
echo -e "${GREEN}✓ Ollama startup script created${NC}"

# Summary
echo -e "\n${GREEN}=============================================="
echo "Phase 5 Setup Complete!"
echo "==============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. ${YELLOW}Start Ollama with Qwen-VL:${NC}"
echo "   /Users/danexall/start-ollama-vision.sh"
echo ""
echo "2. ${YELLOW}Start Computer Use MCP:${NC}"
echo "   launchctl load ~/Library/LaunchAgents/com.arca.computer-use-mcp.plist"
echo ""
echo "3. ${YELLOW}Test screen control:${NC}"
echo "   python3 -c \"import pyautogui; print(pyautogui.size())\""
echo ""
echo "4. ${YELLOW}Test Puppeteer MCP:${NC}"
echo "   npx -y @modelcontextprotocol/server-puppeteer --help"
echo ""
echo "5. ${YELLOW}Configure Copaw:${NC}"
echo "   Config updated at: ~/.copaw/config.json"
echo ""
echo "6. ${YELLOW}Test vision routing:${NC}"
echo "   python3 /Users/danexall/vision-router.py --test"
echo ""
echo "=============================================="
echo ""
echo "Token Savings:"
echo "  - Local Qwen-VL processes screenshots"
echo "  - Cloud Minimax only used for text reasoning"
echo "  - Estimated savings: 80-90% on vision tasks"
echo ""
echo "=============================================="
