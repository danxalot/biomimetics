#!/usr/bin/env bash
# Claude Code + Grok TUI Stop / AgentResponse hook.
# Delegates to muninn_turn.py (local MuninnDB :8750 only).
set -euo pipefail
exec /usr/bin/env python3 /Users/danexall/biomimetics/scripts/mcp/muninn_turn.py track
