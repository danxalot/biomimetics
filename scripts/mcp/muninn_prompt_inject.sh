#!/usr/bin/env bash
# Claude Code + Grok TUI UserPromptSubmit hook.
# Delegates to muninn_turn.py (local MuninnDB :8750 only).
set -euo pipefail
exec /usr/bin/env python3 /Users/danexall/biomimetics/scripts/mcp/muninn_turn.py inject
