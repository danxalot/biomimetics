#!/bin/bash
# Dispatch a task to grok build (headless) in the BACKGROUND, so long agentic
# jobs don't hit the bridge timeout. grok runs with full local access; its output
# streams to a log the architect polls directly through the shared folder.
#
# Usage: dispatch_grok.sh <run_id> <prompt-file> [extra grok flags...]
set +e
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

RUN="$1"; shift
SRC="$1"; shift

LOGDIR="$HOME/biomimetics/.agent_bridge/grok_runs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/$RUN.log"
PIDF="$LOGDIR/$RUN.pid"
: > "$LOG"

nohup grok --prompt-file "$SRC" \
      --output-format plain \
      --permission-mode auto \
      --check \
      --cwd "$HOME/biomimetics" \
      --max-turns 80 "$@" >> "$LOG" 2>&1 &

echo $! > "$PIDF"
echo "grok run '$RUN' started (pid $(cat "$PIDF"))"
echo "prompt-file: $SRC"
echo "log: $LOG"
