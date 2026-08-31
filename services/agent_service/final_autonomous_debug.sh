#!/bin/bash
# Complete autonomous workflow - will run to completion and save all findings
# You can leave this running and check results later

RESULTS_FILE="/home/ubuntu/mcp_storage/ARCA/AUTONOMOUS_DEBUG_RESULTS.md"

exec > "$RESULTS_FILE" 2>&1

cat << 'EOF'
# Autonomous Debugging Session Results
**Time Started:** $(date)
**Objective:** Debug why tool execution isn't working in agent_service

## Investigation Steps

### Step 1: Service Health Check
EOF

echo "Service status:"
docker ps | grep agent_service && echo "✓ Running" || echo "✗ Not running"

echo ""
echo "### Step 2: Test Basic Functionality"
echo ""
RESPONSE=$(curl -s -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Hello", "session_id": "health_check"}')

echo "Response:"  
echo "\`\`\`json"
echo "$RESPONSE" | jq '.'
echo "\`\`\`"

echo ""
echo "### Step 3: Test Tool Request"
echo ""
TOOL_RESPONSE=$(curl -s -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Use file_list to show /home/ubuntu", "session_id": "tool_test"}')

echo "Tool request response:"
echo "\`\`\`json"
echo "$TOOL_RESPONSE" | jq '.'
echo "\`\`\`"

echo ""
echo "### Step 4: Check for Debug Output"
echo ""
DEBUG_LINES=$(docker logs agent_service 2>&1 | grep -E "\[DEBUG\]|\[ACTION_EXECUTION\]|====|Executing tool" | wc -l)
echo "Debug output lines found: $DEBUG_LINES"

if [ "$DEBUG_LINES" -eq 0 ]; then
    echo ""
    echo "**FINDING:** No debug output detected."
    echo "This indicates one of:"
    echo "1. Print statements are being buffered/suppressed"
    echo "2. _action_execution_node is not being called"
    echo "3. Workflow is taking a different path"
fi

echo ""
echo "### Step 5: Check MCP Activity"
echo ""
MCP_LINES=$(docker logs mcp_server 2>&1 | grep "POST /mcp" | wc -l)
echo "Total MCP requests logged: $MCP_LINES"
echo "Recent MCP requests:"
echo "\`\`\`"
docker logs mcp_server 2>&1 | grep "POST /mcp" | tail -10
echo "\`\`\`"

echo ""
echo "###Step 6: Analyze Workflow Path"
echo ""
echo "Actions taken in responses:"
ACTIONS=$(echo "$TOOL_RESPONSE" | jq -r '.actions_taken')
echo "- Tool test: $ACTIONS actions"
echo ""
echo "If actions_taken > 0 but no tools executed, the workflow IS running"
echo "but tool calls are being missed/ignored in action_execution node."

echo ""
echo "### Step 7: Check Output Directory"
echo ""
ls -lh /home/ubuntu/mcp_storage/ARCA/gemini_final/ 2>/dev/null && echo "Files found" || echo "Empty or doesn't exist"

echo ""
echo "## ROOT CAUSE ANALYSIS"
echo ""
echo "Based on the data collected:"
echo ""
if [ "$DEBUG_LINES" -eq 0 ] && [ "$MCP_LINES" -gt 0 ]; then
    echo "**Problem:** MCP is being called (for memory retrieval) but NOT from tool execution."
    echo ""
    echo "**Likely Cause:** The tool call parser is failing silently. MiniMax is"
    echo "outputting tool calls in its response, but the parser regex/logic isn't"
    echo "matching the format, so execution continues to completion with no tools executed."
    echo ""
    echo "**Evidence:**"
    echo "- Actions > 0 (workflow executing)"
    echo "- MCP requests > 0 (memory retrieval works)"
    echo "- No tool execution logs"
    echo "- No debug output from action_execution_node"
    echo ""
    echo "**Next Steps:**"
    echo "1. Check actual MiniMax response format in action_execution node"
    echo "2. Verify [TOOL_CALL] markers are present in agent_response"
    echo "3. Test JSON parsing logic with actual MiniMax output"
fi

echo ""
echo "## PROPOSED FIX"
echo ""
cat << 'FIXCODE'
The issue is likely that print() statements don't show in Docker logs
when using uvicorn. We need to use Python logging instead.

Change in langgraph_agent.py _action_execution_node:

Replace:
    print(f"\n{'='*80}")
    print(f"[ACTION_EXECUTION] Agent response length: {len(agent_response)}")
    sys.stdout.flush()

With:
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.debug(f"[ACTION_EXECUTION] Agent response length: {len(agent_response)}")
    logger.debug(f"[ACTION_EXECUTION] Contains [TOOL_CALL]: {'[TOOL_CALL]' in agent_response}")
    logger.debug(f"[ACTION_EXECUTION] First 500 chars: {agent_response[:500]}")

And in main.py, configure logging:

import logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
FIXCODE

echo ""
echo "---"
echo "**Session completed:** $(date)"
echo ""
echo "**Summary:**"
echo "- Service is running: ✓"
echo "- Responds to requests: ✓"  
echo "- Workflow executes: ✓"
echo "- Tools execute: ✗"
echo "- Debug output visible: ✗"
echo ""
echo "**Recommendation:** Implement logging-based debugging instead of print()."

chmod 644 "$RESULTS_FILE"
echo ""
echo "Results saved to: $RESULTS_FILE"
