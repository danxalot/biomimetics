#!/bin/bash
# Wake_Jarvis - Single Launch for BiOS Architecture
# Launches: CoPaw (with Serena MCP) + React Frontend + Jarvis Daemon
# Ensures no duplicate processes via lock-file and process guards

echo "⚡ Waking BiOS Architecture..."

# -------------------------------------------------
# 1) Kill any stale Jarvis/CoPaw/frontend processes
# -------------------------------------------------
pkill -f 'jarvis_daemon.py' >/dev/null 2>&1
pkill -f 'vite' >/dev/null 2>&1
pkill -f 'npm.*dev' >/dev/null 2>&1

# Remove stale lock file if it exists
rm -f ~/.jarvis.lock

sleep 1

# -------------------------------------------------
# 2) Start CoPaw (Serena MCP) in background
# -------------------------------------------------
echo "🚀 Launching CoPaw + Serena MCP..."
cd /Users/danexall/biomimetics && source ~/.copaw/venv/bin/activate &
copaw app >/tmp/copaw.log 2>&1 &
COPAP_PID=$!

# -------------------------------------------------
# 3) Start React frontend
# -------------------------------------------------
echo "🌐 Launching React Frontend..."
cd /Users/danexall/biomimetics/gemini-live-voice &
npm run dev >/tmp/frontend.log 2>&1 &
FRONT_PID=$!

# -------------------------------------------------
# 4) Start Jarvis daemon (will enforce its own lock-file)
# -------------------------------------------------
echo "🎙️ Launching Jarvis Daemon..."
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/danexall/biomimetics/scripts/copaw/jarvis_daemon.py >/tmp/jarvis.log 2>&1 &
JARVIS_PID=$!

# -------------------------------------------------
# 5) Wait a moment for everything to bind
# -------------------------------------------------
sleep 5

# -------------------------------------------------
# 6) Quick health-check
# -------------------------------------------------
# 6) Quick health-checkn
# -------------------------------------------------necho '--- Health Check ---'nJARVIS_COUNT=$(pgrep -f jarvis_daemon.py | wc -l)n[[ $JARVIS_COUNT -eq 1 ]] && echo '✅ Jarvis: 1 instance' || echo '❌ Jarvis: $JARVIS_COUNT instances'nCOPAP_COUNT=$(pgrep -f "copaw app" | wc -l)n[[ $COPAP_COUNT -eq 1 ]] && echo '✅ CoPaw: 1 instance' || echo '❌ CoPaw: $COPAP_COUNT instances'nFRONT_COUNT=$(pgrep -f vite | wc -l)n[[ $FRONT_COUNT -ge 1 ]] && echo '✅ Frontend: running' || echo '❌ Frontend: $FRONT_COUNT instances'nif nc -z localhost 8088 2>/dev/null; thenn    echo '✅ CoPaw port 8088 open'nelsen    echo '❌ CoPaw port 8088 closed'nfin
echo ''
echo '✅ All services launched. Say "Jarvis, engage all systems" to wake the BIOS.'
echo ''
echo "Process IDs:"
echo "   CoPaw: $COPAP_PID"
echo "   Frontend: $FRONT_PID"
echo "   Jarvis: $JARVIS_PID"
