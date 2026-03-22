#!/bin/bash
# BiOS Master Ignition Script
# Brings all ARCA/Jarvis systems online in one go.

USER_ID=$(id -u)
LA=~/Library/LaunchAgents
LOG=~/biomimetics/logs/jarvis.log

echo "⚡ BiOS Master Ignition — Bringing systems online..."

# 1. Local Llama (Vulkan Qwen-VL on port 11435)
echo "  [1/5] Checking Llama.cpp server..."
if curl -s --max-time 2 http://localhost:11435/health >/dev/null 2>&1; then
    echo "    ✅ Llama server running on port 11435"
else
    launchctl bootstrap gui/$USER_ID $LA/com.bios.llamacpp-server.plist 2>/dev/null
    sleep 3
    curl -s --max-time 2 http://localhost:11435/health >/dev/null 2>&1 \
        && echo "    ✅ Llama server started on port 11435" \
        || echo "    ⚠️  Llama server not responding"
fi

# 2. Computer Use MCP (Vision/Gated Tools)
echo "  [2/5] Starting Computer Use MCP..."
launchctl bootstrap gui/$USER_ID $LA/com.arca.computer-use-mcp.plist 2>/dev/null
echo "    ✅ Computer Use MCP bootstrapped"

# 3. Serena Memory Sync (Codebase Memory) — headless, no browser
echo "  [3/5] Starting Serena memory sync..."
launchctl bootstrap gui/$USER_ID $LA/com.arca.serena-sync.plist 2>/dev/null
echo "    ✅ Serena sync bootstrapped"

# 4. CoPaw App (port 8088) — launch headless if not running
echo "  [4/5] Ensuring CoPaw on port 8088..."
if lsof -i :8088 -t >/dev/null 2>&1; then
    echo "    ✅ CoPaw running on port 8088"
else
    echo "    🔄 Starting CoPaw server..."
    nohup copaw app --host 127.0.0.1 --port 8088 >> ~/biomimetics/logs/copaw.log 2>&1 &
    sleep 4
    if lsof -i :8088 -t >/dev/null 2>&1; then
        echo "    ✅ CoPaw started on port 8088"
    else
        echo "    ❌ CoPaw failed to start — check ~/biomimetics/logs/copaw.log"
    fi
fi

# 5. Jarvis Daemon (Voice Interface)
echo "  [5/5] Starting Jarvis daemon..."
JARVIS_PID=$(pgrep -f "jarvis_daemon.py" 2>/dev/null | head -1)
if [ -n "$JARVIS_PID" ]; then
    echo "    ✅ Jarvis running (PID $JARVIS_PID)"
else
    nohup python3 ~/biomimetics/scripts/copaw/jarvis_daemon.py >> "$LOG" 2>&1 &
    sleep 2
    JARVIS_PID=$(pgrep -f "jarvis_daemon.py" 2>/dev/null | head -1)
    [ -n "$JARVIS_PID" ] \
        && echo "    ✅ Jarvis started (PID $JARVIS_PID)" \
        || echo "    ❌ Jarvis failed — check $LOG"
fi

# 6. Log Reviewer (periodic Notion sync)
echo "  [6/6] Starting log reviewer..."
launchctl bootstrap gui/$USER_ID $LA/com.arca.log-reviewer.plist 2>/dev/null
echo "    ✅ Log reviewer bootstrapped (runs every 6h)"

echo ""
echo "⚡ All BiOS systems are now online and synchronized."
