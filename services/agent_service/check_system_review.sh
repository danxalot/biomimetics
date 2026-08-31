#!/bin/bash
# Monitor system review progress

echo "=== SYSTEM REVIEW PROGRESS ==="
echo ""

# Check if checkpoint exists
CHECKPOINT="/home/ubuntu/mcp_storage/ARCA/checkpoints/system_review.json"

if [ ! -f "$CHECKPOINT" ]; then
    echo "❌ No checkpoint found yet"
    exit 1
fi

echo "📊 Checkpoint Status:"
python3 << 'PYTHON_EOF'
import json
from datetime import datetime

with open('/home/ubuntu/mcp_storage/ARCA/checkpoints/system_review.json', 'r') as f:
    state = json.load(f)

print(f"  Task ID: {state['task_id']}")
print(f"  Last updated: {state['timestamp']}")
print(f"  Current subtask: {state['state'].get('current_subtask', 'None')}")
print(f"  Completed: {len(state['state']['completed_subtasks'])}/9")
print(f"  Failed: {len(state['state']['failed_subtasks'])}")

if state['state']['completed_subtasks']:
    print("\n✅ Completed subtasks:")
    for task in state['state']['completed_subtasks']:
        print(f"  - {task['name']} ({task['completed_at']})")

if state['state']['failed_subtasks']:
    print("\n❌ Failed subtasks:")
    for task in state['state']['failed_subtasks']:
        print(f"  - {task['name']}: {task['error']}")
PYTHON_EOF

echo ""
echo "📁 Output files:"
if [ -d "/home/ubuntu/mcp_storage/ARCA/system_review" ]; then
    ls -lh /home/ubuntu/mcp_storage/ARCA/system_review/ 2>/dev/null || echo "  No files yet"
else
    echo "  Directory not created yet"
fi

echo ""
echo "📋 Recent log:"
LOG=$(ls -t /home/ubuntu/mcp_storage/ARCA/logs/system_review_*.log 2>/dev/null | head -1)
if [ -n "$LOG" ]; then
    echo "  Log file: $LOG"
    tail -10 "$LOG"
else
    echo "  No log file found"
fi
