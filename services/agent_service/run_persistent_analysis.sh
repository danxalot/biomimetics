#!/bin/bash

# Persistent Comprehensive Analysis Runner
# This script runs the analysis with automatic checkpointing and resumption

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_ID="comprehensive_analysis_persistent_$(date +%Y%m%d_%H%M%S)"
LOG_DIR="/home/ubuntu/mcp_storage/ARCA/logs"
LOG_FILE="${LOG_DIR}/persistent_analysis_$(date +%Y%m%d_%H%M%S).log"

# Create log directory
mkdir -p "$LOG_DIR"

echo "========================================"
echo "Persistent Comprehensive Analysis"
echo "========================================"
echo "Task ID: $TASK_ID"
echo "Log file: $LOG_FILE"
echo "Start time: $(date)"
echo "========================================"
echo ""

# Run with Python directly (inside Docker or on host)
python3 "${SCRIPT_DIR}/persistent_task_runner.py" \
    --task-id "$TASK_ID" \
    --agent-url "http://localhost:8000" \
    2>&1 | tee "$LOG_FILE"

EXIT_CODE=$?

echo ""
echo "========================================"
echo "Task completed with exit code: $EXIT_CODE"
echo "End time: $(date)"
echo "========================================"

# Check output files
echo ""
echo "Generated files:"
ls -lh /home/ubuntu/mcp_storage/ARCA/gemini_final/ 2>/dev/null || echo "No files generated"

exit $EXIT_CODE
