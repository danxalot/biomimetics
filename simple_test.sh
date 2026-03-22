#!/bin/bash

# Simple test to debug the save_to_notion issue

echo "=== Starting debug test ==="

# Kill existing Jarvis processes
echo "Stopping existing Jarvis processes..."
pkill -f "jarvis_daemon.py" 2>/dev/null || true
sleep 2

# Start Jarvis in background
echo "Starting Jarvis daemon..."
python3 /Users/danexall/biomimetics/scripts/copaw/jarvis_daemon.py > /tmp/jarvis.log 2>&1 &
JARVIS_PID=$!
echo "Jarvis started with PID: $JARVIS_PID"

# Wait for startup
echo "Waiting for Jarvis to initialize..."
sleep 5

# Test save_to_notion via frontend API (POST to agent/memory)
echo -e "\nTesting save_to_notion via frontend API..."
RESPONSE=$(curl -s -X POST "http://127.0.0.1:8088/api/agent/memory" \
  -H "Content-Type: application/json" \
  -d '{"tool": "save_to_notion", "args": {"title": "Debug Test", "category": "travel", "content": "# Debug Test\n\nThis is a debug test."}}' \
  -w "\nHTTP Status: %{http_code}\n")

echo "Response: $RESPONSE"

# Wait for processing
sleep 3

# Check memory directory
echo -e "\nChecking memory directory:"
ls -la /Users/danexall/.copaw/memory/

# Check Jarvis logs
echo -e "\nChecking Jarvis logs for save_to_notion:"
grep -i "save_to_notion\|NOTION_SAVED" /tmp/jarvis.log || echo "No save_to_notion logs found"

# Cleanup
echo -e "\nCleaning up..."
kill $JARVIS_PID 2>/dev/null || true
echo "Test complete."