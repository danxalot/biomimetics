#!/bin/bash
# Clear any zombie processes holding the BiOS Voice port
lsof -ti :8090 | xargs kill -9 2>/dev/null || true

# BiOS Voice Channel Activation Script
# Overrides default channels to only load 'voice' channel for terminal-based Gemini Live interactions.

export COPAW_ENABLED_CHANNELS=voice
export COPAW_LOG_LEVEL=INFO
export COPAW_WORKING_DIR=/Users/danexall/.copaw
export COPAW_API_PORT=8090

# Use the specific virtualenv python that has all dependencies
PYTHON_EXE="/Users/danexall/biomimetics/config_copaw/venv/bin/python3"

# Ensure we are in the correct directory for the Python module loading
cd /Users/danexall/biomimetics/scripts/copaw
export PYTHONPATH=$PYTHONPATH:$(pwd)/src

echo "--- BiOS Voice Channel Activation ---"
echo "Relay: ws://100.X.X.X:8765/ws/live"
echo "--------------------------------------"

# Launch the CoPaw application in terminal mode using the pinned venv
# Use port 8090 to avoid conflict with default 8088
$PYTHON_EXE -m copaw app --port 8090
