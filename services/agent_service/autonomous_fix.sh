#!/bin/bash

# Full autonomous debugging and fixing workflow
# This will identify and fix the tool execution issue

LOG_DIR="/home/ubuntu/mcp_storage/ARCA/debug_logs"
mkdir -p "$LOG_DIR"

MAIN_LOG="$LOG_DIR/autonomous_fix_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$MAIN_LOG") 2>&1

echo "========================================="
echo "AUTONOMOUS DEBUG & FIX WORKFLOW"
echo "Time: $(date)"
echo "========================================="

# Check if service is running
echo ""
echo "[CHECK 1] Is agent_service running?"
docker ps | grep agent_service
if [ $? -eq 0 ]; then
    echo "✓ Container is running"
else
    echo "✗ Container is NOT running - starting it..."
    cd /home/ubuntu/ARCA/services/agent_service
    docker start agent_service || docker run -d --name agent_service \
        --network arca_arca_net -p 8000:8000 \
        -v /home/ubuntu/ARCA/.secrets:/app/.secrets:ro \
        -e MCP_SERVER_URL=http://mcp_server:8086 \
        -e MCP_CLIENT_API_KEY=change_me_mcp_key \
        agent_service:latest
    sleep 5
fi

# Test basic connectivity
echo ""
echo "[CHECK 2] Can we reach the service?"
timeout 10 curl -s http://localhost:8000/ > /dev/null 2>&1
if [ $? -eq 0 ] || [ $? -eq 22 ]; then
    echo "✓ Service is responding"
else
    echo "✗ Service not responding - checking logs..."
    docker logs agent_service 2>&1 | tail -20
fi

# Test with longer timeout
echo ""
echo "[CHECK 3] Testing invoke endpoint with 30s timeout..."
RESPONSE=$(timeout 30 curl -s -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Hello", "session_id": "quick_test"}' 2>&1)

if [ -n "$RESPONSE" ]; then
    echo "✓ Got response:"
    echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
else
    echo "✗ No response (timeout or error)"
    echo "Checking agent_service logs..."
    docker logs agent_service 2>&1 | tail -30
fi

# Check for our debug prints
echo ""
echo "[CHECK 4] Looking for debug output..."
DEBUG_OUTPUT=$(docker logs agent_service 2>&1 | grep -E "\[DEBUG\]|\[ACTION_EXECUTION\]" | head -20)
if [ -n "$DEBUG_OUTPUT" ]; then
    echo "✓ Found debug output:"
    echo "$DEBUG_OUTPUT"
else
    echo "✗ No debug output found"
    echo "This means _action_execution_node is NOT being called"
    echo "OR print() statements aren't showing in Docker logs"
fi

# Check Python print buffering
echo ""
echo "[CHECK 5] Checking if Python output is buffered..."
echo "Docker logs tail (last 50 lines):"
docker logs agent_service 2>&1 | tail -50

# Try forcing output flush
echo ""
echo "[FIX ATTEMPT 1] Adding sys.stdout.flush() to debug prints..."

cat > /tmp/action_execution_debug_patch.py << 'EOPYTHON'
import sys

def add_debug_to_action_execution(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Replace the print statements with flushed versions
    content = content.replace(
        'print(f"\\n{\'=\'*80}")',
        'import sys; print(f"\\n{\'=\'*80}"); sys.stdout.flush()'
    )
    content = content.replace(
        'print(f"[DEBUG]',
        'print(f"[DEBUG]'
    )
    # Add flush after every print
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        new_lines.append(line)
        if 'print(f"[DEBUG]' in line or 'print(f"[ACTION_EXECUTION]' in line:
            indent = len(line) - len(line.lstrip())
            new_lines.append(' ' * indent + 'sys.stdout.flush()')
    
    with open(file_path, 'w') as f:
        f.write('\n'.join(new_lines))
    
    print(f"✓ Added sys.stdout.flush() after debug prints")

if __name__ == "__main__":
    add_debug_to_action_execution("/home/ubuntu/ARCA/services/agent_service/langgraph_agent.py")
EOPYTHON

python3 /tmp/action_execution_debug_patch.py

echo ""
echo "[FIX ATTEMPT 2] Rebuild and restart with flushed output..."
cd /home/ubuntu/ARCA/services/agent_service
docker build -t agent_service:latest . 2>&1 | tail -5
docker restart agent_service
sleep 6

echo ""
echo "[TEST AFTER FIX] Testing again..."
timeout 20 curl -s -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"user_input": "List files in /home/ubuntu using file_list", "session_id": "post_fix_test"}' \
  > /tmp/response.json 2>&1

if [ -f /tmp/response.json ] && [ -s /tmp/response.json ]; then
    echo "✓ Got response:"
    cat /tmp/response.json | jq '.' 2>/dev/null || cat /tmp/response.json
fi

echo ""
echo "Checking logs again..."
docker logs agent_service 2>&1 | tail -100 > "$LOG_DIR/agent_service_full.log"
echo "Full logs saved to: $LOG_DIR/agent_service_full.log"

echo ""
echo "Looking for our markers..."
grep -E "\[DEBUG\]|\[ACTION_EXECUTION\]|====" "$LOG_DIR/agent_service_full.log" || echo "Still no debug output"

echo ""
echo "========================================="
echo "AUTONOMOUS DEBUG COMPLETE"
echo "Main log: $MAIN_LOG"
echo "========================================="
