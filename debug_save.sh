#!/bin/bash

# Test script to debug save_to_notion functionality

echo "=== Testing save_to_notion functionality ==="

# Kill any existing Jarvis processes
echo "Stopping existing Jarvis processes..."
pkill -f "jarvis_daemon.py" 2>/dev/null || true
sleep 2

# Start Jarvis in background and capture PID
echo "Starting Jarvis daemon..."
python3 /Users/danexall/biomimetics/scripts/copaw/jarvis_daemon.py > /tmp/jarvis_test.log 2>&1 &
JARVIS_PID=$!
echo "Jarvis started with PID: $JARVIS_PID"

# Wait for Jarvis to initialize
echo "Waiting for Jarvis to start..."
sleep 5

# Test the save_to_notion tool via the CoPaw API (what the frontend does)
echo -e "\nTesting save_to_notion via frontend API (POST to /api/agent/memory)..."
RESPONSE=$(curl -s -X POST "http://127.0.0.1:8088/api/agent/memory" \
  -H "Content-Type: application/json" \
  -d '{"tool": "save_to_notion", "args": {"title": "Test Travel Debug", "category": "travel", "content": "# Test Travel Itinerary\n\nThis is a test to verify the fix."}}' \
  -w "\nHTTP Status: %{http_code}\n")

echo "Response: $RESPONSE"

# Wait a bit for processing
echo -e "\nWaiting for processing..."
sleep 3

# Check CoPaw memory for the file
echo -e "\nChecking CoPaw memory for travel files:"
ls -la /Users/danexall/.copaw/memory/ | grep -i travel || echo "No travel files found in memory"

# List all memory files to see what we have
echo -e "\nAll memory files in CoPaw:"
ls -la /Users/danexall/.copaw/memory/

# Check the Jarvis logs for any errors or success messages
echo -e "\nChecking Jarvis logs for save_to_notion activity:"
grep -i "save_to_notion\|memory\|notion" /tmp/jarvis_test.log || echo "No save_to_notion logs found"

# Show recent Jarvis log entries
echo -e "\nRecent Jarvis log entries:"
tail -20 /tmp/jarvis_test.log

# Clean up by killing the Jarvis process
echo -e "\nCleaning up Jarvis process..."
kill $JARVIS_PID 2>/dev/null || true
echo "Jarvis process terminated."

echo -e "\n=== Test Complete ==="