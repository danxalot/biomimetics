#!/bin/bash
# ==============================================================================
# BiOS Master Daily Pipeline
# Coordinates the sequential flow of document processing from ingestion to memory.
# Execution Order:
#   1. Failed Email Brief (Generates summary of yesterday's failures)
#   2. Vault Sweeper (Moves Notion-authorized staging items to GDrive Vault)
#   3. Semantic Tagger (Injects semantic tags into GDrive Vault documents)
#   4. Memory Sync (Pushes tagged documents from GDrive Vault to MuninnDB)
# ==============================================================================

set -euo pipefail

# Base directories
PROJECT_ROOT="/Users/danexall/biomimetics"
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

echo "============================================================"
echo "  BiOS Master Daily Pipeline Started at $(date)"
echo "============================================================"

cd "$PROJECT_ROOT"

echo -e "\n--- [Step 1/8] Generating Failed Email Brief ---"
"$PYTHON_BIN" scripts/email/daily_failed_email_brief.py || echo "Warning: Failed Email Brief encountered an error."

echo -e "\n--- [Step 2/8] Harvesting and Condensing Dev Artifacts ---"
"$PYTHON_BIN" scripts/archivist/artifact_harvester.py || fail "Artifact Harvester"
"$PYTHON_BIN" scripts/archivist/dev_artifact_condenser.py || fail "Dev Artifact Condenser"

echo -e "\n--- [Step 3/8] Executing Notion Vault Sweeper ---"
"$PYTHON_BIN" scripts/email/notion_vault_sweeper.py || fail "Vault Sweeper"

echo -e "\n--- [Step 4/8] Running Vault Condenser (Pillar Assimilation) ---"
"$PYTHON_BIN" scripts/archivist/vault_condenser.py || fail "Vault Condenser"

echo -e "\n--- [Step 4b/8] Chunking oversized vault notes ---"
"$PYTHON_BIN" scripts/archivist/vault_chunker.py || fail "Vault Chunker"

echo -e "\n--- [Step 4c/8] Serena memories + OpenCode enrichment ---"
"$PYTHON_BIN" scripts/memory/serena-memory-sync.py --once || echo "Warning: Serena/OpenCode sync skipped."

echo -e "\n--- [Step 5/8] Running Semantic LLM Tagger (partition delineation) ---"
"$PYTHON_BIN" scripts/archivist/semantic_llm_tagger.py || fail "Semantic Tagger"

echo -e "\n--- [Step 6/8] Synchronizing Partitioned Vault to Memory ---"
"$PYTHON_BIN" scripts/archivist/tagged_memory_sync.py || fail "Memory Sync"

echo -e "\n--- [Step 7/8] Regenerating Self-Building Overview (MOCs, trackers, index) ---"
if ! "$PYTHON_BIN" scripts/archivist/generate_overview.py 2>&1; then
  echo "Warning: Overview Generator encountered an error (traceback above)."
fi

echo -e "\n--- [Step 8/8] Building Human Dashboard (Cloudflare-ready HTML) ---"
if ! "$PYTHON_BIN" scripts/archivist/generate_dashboard.py 2>&1; then
  echo "Warning: Dashboard Generator encountered an error (traceback above)."
fi

echo -e "\n--- [Optional] Deploying Dashboard to Cloudflare (free tier) ---"
if ! "$PYTHON_BIN" scripts/deploy/deploy_dashboard_cf.py 2>&1; then
  echo "Note: Cloudflare deploy skipped/failed (non-fatal; traceback above)."
fi

echo -e "\n============================================================"
echo "  BiOS Master Daily Pipeline Completed at $(date)"
echo "============================================================"
