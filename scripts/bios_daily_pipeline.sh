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

set -e

# Base directories
PROJECT_ROOT="/Users/danexall/biomimetics"
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

echo "============================================================"
echo "  BiOS Master Daily Pipeline Started at $(date)"
echo "============================================================"

cd "$PROJECT_ROOT"

echo -e "\n--- [Step 1/4] Generating Failed Email Brief ---"
"$PYTHON_BIN" scripts/email/daily_failed_email_brief.py || echo "Warning: Failed Email Brief encountered an error."

echo -e "\n--- [Step 2/4] Executing Notion Vault Sweeper ---"
"$PYTHON_BIN" scripts/email/notion_vault_sweeper.py || echo "Warning: Vault Sweeper encountered an error."

echo -e "\n--- [Step 3/4] Running Semantic LLM Tagger ---"
"$PYTHON_BIN" scripts/archivist/semantic_llm_tagger.py || echo "Warning: Semantic Tagger encountered an error."

echo -e "\n--- [Step 4/4] Synchronizing Tagged Documents to Memory ---"
"$PYTHON_BIN" scripts/archivist/tagged_memory_sync.py || echo "Warning: Memory Sync encountered an error."

echo -e "\n============================================================"
echo "  BiOS Master Daily Pipeline Completed at $(date)"
echo "============================================================"
