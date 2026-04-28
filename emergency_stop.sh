#!/bin/bash
# BiOS Swarm Emergency Stop (Professional PID-Based)
# Targeted graceful shutdown of the Serena autonomous poller.

PID_FILE="/Users/danexall/biomimetics/.serena.pid"
HALT_FILE="/Users/danexall/biomimetics/.swarm_halt"

echo "🚨 SWARM EMERGENCY STOP INITIATED 🚨"

# 1. Check for Active Workers via PID file
if [ -f "$PID_FILE" ]; then
    SERENA_PID=$(cat "$PID_FILE")
    echo "  [1/3] Active Serena Worker detected (PID: $SERENA_PID)."
    
    # 2. Graceful Shutdown (SIGTERM)
    echo "  [2/3] Sending SIGTERM (Graceful Shutdown)..."
    kill -15 "$SERENA_PID" 2>/dev/null
    
    # Wait and check
    for i in {1..3}; do
        if ! ps -p "$SERENA_PID" > /dev/null; then
            echo "    ✅ Worker exited gracefully."
            break
        fi
        echo "    ...waiting for exit ($i/3)..."
        sleep 1
    done
    
    # 3. Escalation (SIGKILL)
    if ps -p "$SERENA_PID" > /dev/null; then
        echo "  [!] Worker still active. Escalating to SIGKILL (kill -9)..."
        kill -9 "$SERENA_PID" 2>/dev/null
        sleep 1
    fi
    
    # Clean up PID file if worker didn't
    rm -f "$PID_FILE"
else
    echo "  [1/3] No active Serena Worker PID file found. Skipping kills."
fi

# 4. Set the Swarm Halt Flag
echo "  [3/3] Setting Swarm Halt Flag (.swarm_halt)..."
touch "$HALT_FILE"

echo ""
echo "CRITICAL: Swarm halted. Only the autonomous poller is blocked."
echo "Master Agents and UI controls (bios-up.sh) remain operational."
echo "To resume the poller, remove $HALT_FILE."
