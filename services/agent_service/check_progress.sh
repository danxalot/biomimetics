#!/bin/bash

# Monitor Persistent Analysis Progress

echo "========================================"
echo "Persistent Analysis Progress Monitor"
echo "========================================"
echo ""

# Check if task is running
if pgrep -f "persistent_task_runner.py" > /dev/null; then
    echo "✅ Task is RUNNING (PID: $(pgrep -f persistent_task_runner.py))"
else
    echo "⚠️  Task is NOT running"
fi

echo ""
echo "=== Latest Log Activity ==="
tail -30 /home/ubuntu/mcp_storage/ARCA/logs/overnight_*.log 2>/dev/null | grep -E "INFO.*subtask|✅|❌|Checkpoint" | tail -10

echo ""
echo "=== Checkpoint Status ==="
if [ -f /home/ubuntu/mcp_storage/ARCA/checkpoints/comprehensive_analysis_overnight.json ]; then
    echo "Last checkpoint:"
    cat /home/ubuntu/mcp_storage/ARCA/checkpoints/comprehensive_analysis_overnight.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f\"  Timestamp: {data['timestamp']}\")
print(f\"  Current subtask: {data['state']['current_subtask']}/8\")
print(f\"  Completed: {len(data['state']['completed_subtasks'])}\")
for task in data['state']['completed_subtasks']:
    print(f\"    ✅ {task['name']} - {task['completed_at']}\")
" 2>/dev/null || cat /home/ubuntu/mcp_storage/ARCA/checkpoints/comprehensive_analysis_overnight.json
else
    echo "No checkpoint found"
fi

echo ""
echo "=== Output Files Generated ==="
ls -lh /home/ubuntu/mcp_storage/ARCA/gemini_final/ 2>/dev/null || echo "No files yet"

echo ""
echo "========================================"
echo "To view full logs: tail -f /home/ubuntu/mcp_storage/ARCA/logs/overnight_*.log"
echo "To stop task: pkill -f persistent_task_runner.py"
echo "To resume task: cd /home/ubuntu/ARCA/services/agent_service && python3 persistent_task_runner.py --task-id comprehensive_analysis_overnight --resume"
echo "========================================"
