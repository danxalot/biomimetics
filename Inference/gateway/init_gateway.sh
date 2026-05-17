#!/bin/bash
set -e

echo "🚀 Starting LLM Gateway as user 'app'..."

# Drop privileges and start the gateway application
# The base entrypoint.sh already handled Tailscale initialization
exec gosu app python main.py
