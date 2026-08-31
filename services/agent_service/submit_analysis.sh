#!/bin/bash
# Submit comprehensive analysis to MiniMax for overnight processing

PROMPT_FILE="/home/ubuntu/ARCA/services/agent_service/comprehensive_analysis_prompt.txt"
OUTPUT_DIR="/home/ubuntu/mcp_storage/ARCA/gemini_final"
LOG_FILE="/home/ubuntu/mcp_storage/ARCA/analysis_$(date +%Y%m%d_%H%M%S).log"

echo "======================================"
echo "Starting Comprehensive ARCA Analysis"
echo "Time: $(date)"
echo "======================================"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Read the prompt
PROMPT=$(cat "$PROMPT_FILE")

# Submit to MiniMax via agent_service
echo "Submitting task to MiniMax M2..." | tee -a "$LOG_FILE"

curl -X POST http://localhost:8000/invoke \
  -H 'Content-Type: application/json' \
  -d "{
    \"user_input\": $(echo "$PROMPT" | jq -Rs .),
    \"session_id\": \"comprehensive_analysis_$(date +%Y%m%d_%H%M%S)\",
    \"context\": {
      \"priority\": \"critical\",
      \"output_directory\": \"$OUTPUT_DIR\",
      \"task_type\": \"comprehensive_analysis\"
    }
  }" 2>&1 | tee -a "$LOG_FILE"

echo ""
echo "======================================"
echo "Task submitted at: $(date)"
echo "Log file: $LOG_FILE"
echo "Output directory: $OUTPUT_DIR"
echo "======================================"
