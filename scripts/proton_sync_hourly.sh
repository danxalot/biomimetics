#!/bin/bash
#
# ARCA ProtonMail Hourly Sync
# Wrapper script for launchd to run ProtonMail sync
#

set -euo pipefail

LOG_FILE="$HOME/.arca/proton_sync_wrapper.log"
SCRIPT_PATH="$HOME/.copaw/backfill_claws.py"
PYTHON_PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting ProtonMail sync..."

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    log "WARNING: Ollama not running. Starting Ollama..."
    # Try to start Ollama (if installed via brew)
    if command -v ollama &> /dev/null; then
        ollama serve &
        sleep 5
    fi
fi

# Check if Proton Bridge is accessible
if ! nc -z 127.0.0.1 1143 2>/dev/null; then
    log "WARNING: Proton Bridge not accessible on port 1143"
    log "Ensure Proton Mail Bridge is running and configured"
fi

# Run the sync script
if [ -f "$SCRIPT_PATH" ]; then
    $PYTHON_PATH "$SCRIPT_PATH" 2>&1 | tee -a "$LOG_FILE"
    log "ProtonMail sync completed"
else
    log "ERROR: Script not found at $SCRIPT_PATH"
    exit 1
fi

log "Wrapper cycle complete"
exit 0
