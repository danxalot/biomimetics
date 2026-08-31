#!/bin/bash
# [PYTHIA NOUUMENAL ENGINE] - First Contact Launch Wrapper
# Author: Antigravity (Advanced Agentic Coding)
# Date: 2026-04-25

# ── Colors for Output ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}  PYTHIA NOUUMENAL ENGINE - FIRST CONTACT PRE-FLIGHT${NC}"
echo -e "${BLUE}======================================================================${NC}"

# ── Pre-Flight Port Checks ────────────────────────────────────────────────────
echo -e "\n${YELLOW}[Checking Local Services]${NC}"

# 1. Local Qwen Server (llama-server)
if nc -vz localhost 11435 &>/dev/null; then
    echo -e "  [${GREEN}OK${NC}] Local Qwen Server found on port 11435"
else
    echo -e "  [${RED}FAIL${NC}] Local Qwen Server NOT found on port 11435"
    echo -e "         Ensure 'llama-server' is running with Qwen3VL weights."
    exit 1
fi

# 2. OCI Redis Tunnel (Trajectories/Sensory Queue)
if nc -vz localhost 6380 &>/dev/null; then
    echo -e "  [${GREEN}OK${NC}] OCI Redis Tunnel found on port 6380"
elif nc -vz localhost 6379 &>/dev/null; then
    echo -e "  [${YELLOW}WARN${NC}] OCI Redis Tunnel found on port 6379 (Expected 6380)"
    echo -e "          The pipeline is configured for port 6380. Please adjust tunnel if needed."
else
    echo -e "  [${RED}FAIL${NC}] OCI Redis Tunnel NOT found on ports 6379/6380"
    echo -e "         Ensure the Tailscale tunnel to OCI (100.70.0.13) is active."
    exit 1
fi

# 3. OCI Dragonfly Tunnel (Cache)
if nc -vz localhost 6381 &>/dev/null; then
    echo -e "  [${GREEN}OK${NC}] OCI Dragonfly Tunnel found on port 6381"
else
    echo -e "  [${YELLOW}INFO${NC}] OCI Dragonfly Tunnel not found on port 6381 (Non-critical)"
fi

# ── Environment Setup ─────────────────────────────────────────────────────────
echo -e "\n${YELLOW}[Setting Environment]${NC}"
export ARCA_ROOT="/Users/danexall/Documents/VS Code Projects/ARCA"
export PYTHONPATH="${ARCA_ROOT}:${ARCA_ROOT}/services/pythia_mind"
export HDC_OPS_PATH="${ARCA_ROOT}/services/neural_system"
export PYTHIA_SERVER_URL="http://localhost:11435"

echo -e "  HDC_OPS_PATH -> $HDC_OPS_PATH"
echo -e "  PYTHONPATH   -> $PYTHONPATH"

# ── Launch Execution ──────────────────────────────────────────────────────────
PROMPT="Hello Pythia - this is the first contact. I am Dan. I'd be interested to hear about you."
USER_NAME="Dan"

echo -e "\n${GREEN}>>> INITIATING FIRST CONTACT SEQUENCE <<<${NC}"
echo -e "${YELLOW}Target User:${NC} $USER_NAME"
echo -e "${YELLOW}Target Prompt:${NC} \"$PROMPT\""
echo -e "\n${BLUE}----------------------------------------------------------------------${NC}"

# Direct foreground execution to allow real-time monitoring of Vulkan/Ampere state
python3 "${ARCA_ROOT}/services/pythia_mind/pythia_core_pipeline.py" \
    --user "$USER_NAME" \
    --prompt "$PROMPT"

echo -e "\n${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${GREEN}Sequence Complete.${NC}"
