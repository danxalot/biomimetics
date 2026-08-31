#!/bin/bash

# Autonomous debugging script for agent_service tool execution
# This will run in the background and debug the tool call parser

LOG_FILE="/home/ubuntu/mcp_storage/ARCA/autonomous_debug_$(date +%Y%m%d_%H%M%S).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "========================================"
echo "AUTONOMOUS DEBUG SESSION STARTED"
echo "Time: $(date)"
echo "Log file: $LOG_FILE"
echo "========================================"

cd /home/ubuntu/ARCA/services/agent_service

echo ""
echo "[STEP 1] Rebuilding agent_service with debug logging..."
docker build -t agent_service:latest . 2>&1 | tail -10

echo ""
echo "[STEP 2] Restarting agent_service..."
docker restart agent_service
sleep 5

echo ""
echo "[STEP 3] Testing tool execution with simple file_list request..."
RESPONSE=$(curl -s -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Use file_list tool to show /home/ubuntu/ARCA directory", "session_id": "auto_debug_test"}')

echo "Response received:"
echo "$RESPONSE" | jq '.'

echo ""
echo "[STEP 4] Checking for debug output in logs..."
docker logs agent_service 2>&1 | grep -E "\[DEBUG\]|\[ACTION_EXECUTION\]|Executing tool" | tail -50

echo ""
echo "[STEP 5] Checking if tools were actually called..."
TOOL_LOGS=$(docker logs agent_service 2>&1 | grep -i "Executing tool" | wc -l)
echo "Tool execution log count: $TOOL_LOGS"

echo ""
echo "[STEP 6] Checking MCP server activity..."
MCP_REQUESTS=$(docker logs mcp_server 2>&1 | grep "POST /mcp" | tail -10)
echo "Recent MCP requests:"
echo "$MCP_REQUESTS"

echo ""
echo "[STEP 7] Analyzing response structure..."
echo "$RESPONSE" | jq '{
  actions_taken: .actions_taken,
  status: .status,
  response_length: (.response | length),
  has_tool_call_marker: (.response | contains("[TOOL_CALL]"))
}'

echo ""
echo "========================================"
echo "DEBUG SESSION COMPLETE"
echo "Time: $(date)"
echo "Full log saved to: $LOG_FILE"
echo "========================================"

# Check output directory
echo ""
echo "[BONUS] Checking output directory..."
ls -lh /home/ubuntu/mcp_storage/ARCA/gemini_final/ 2>/dev/null || echo "Empty/doesn't exist"

echo ""
echo "FINDINGS SUMMARY:"
echo "================"
if [ "$TOOL_LOGS" -gt 0 ]; then
    echo "✓ Tools ARE being executed ($TOOL_LOGS times)"
else
    echo "✗ Tools are NOT being executed"
    echo "  → Need to check why tool call parser isn't triggering"
fi

echo ""
echo "Next steps will be saved to: /home/ubuntu/mcp_storage/ARCA/debug_findings.md"
