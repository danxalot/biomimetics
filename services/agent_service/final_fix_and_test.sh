#!/bin/bash
# Final autonomous script - implements logging fix, tests, and reports results

REPORT="/home/ubuntu/mcp_storage/ARCA/FINAL_DEBUG_REPORT.md"

exec > "$REPORT" 2>&1

echo "# Final Autonomous Debug & Fix Report"
echo "**Timestamp:** $(date)"
echo ""
echo "## Changes Implemented"
echo ""
echo "1. Added logging.basicConfig() to main.py"
echo "2. Replaced all print() statements in _action_execution_node with logger.debug()"
echo "3. Configured DEBUG level logging for complete visibility"
echo ""
echo "## Rebuild and Deploy"
echo ""

cd /home/ubuntu/ARCA/services/agent_service
echo "Building new image..."
docker build -t agent_service:latest . 2>&1 | tail -10

echo ""
echo "Restarting service..."
docker restart agent_service
sleep 6

echo ""
echo "## Testing Tool Execution"
echo ""
echo "### Test 1: Simple Request"
curl -s -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Use file_list to show /home/ubuntu/ARCA", "session_id": "final_test_1"}' | jq '.actions_taken, .status'

echo ""
echo "### Test 2: Checking Logs for Debug Output"
echo ""
docker logs agent_service 2>&1 | grep -E "ACTION_EXECUTION|DEBUG.*Found.*TOOL_CALL|Executing tool" | tail -30

echo ""
echo "## Results"
echo ""

DEBUG_COUNT=$(docker logs agent_service 2>&1 | grep "\[ACTION_EXECUTION\]" | wc -l)
TOOL_EXEC_COUNT=$(docker logs agent_service 2>&1 | grep "Executing tool" | wc -l)

echo "- Debug log lines found: $DEBUG_COUNT"
echo "- Tool execution log lines: $TOOL_EXEC_COUNT"
echo ""

if [ "$DEBUG_COUNT" -gt 0 ]; then
    echo "✅ **SUCCESS**: Debug logging is now visible!"
    echo ""
    echo "Sample debug output:"
    echo "\`\`\`"
    docker logs agent_service 2>&1 | grep -A 3 "\[ACTION_EXECUTION\]" | head -20
    echo "\`\`\`"
else
    echo "❌ **ISSUE**: Debug output still not visible"
    echo ""
    echo "This could mean:"
    echo "- Logging level not set correctly"
    echo "- Docker not capturing Python logs"
    echo "- Need to use PYTHONUNBUFFERED=1 environment variable"
fi

echo ""
echo "## MCP Server Activity"
echo ""
MCP_COUNT=$(docker logs mcp_server 2>&1 | grep "POST /mcp" | wc -l)
echo "Total MCP requests since start: $MCP_COUNT"

echo ""
echo "## Comprehensive Analysis Status"
echo ""
echo "Output directory:"
ls -lh /home/ubuntu/mcp_storage/ARCA/gemini_final/ 2>/dev/null

echo ""
echo "---"
echo "**Report completed:** $(date)"
echo "**Saved to:** $REPORT"

# Make readable
chmod 644 "$REPORT"

# Display to console too
cat "$REPORT"
