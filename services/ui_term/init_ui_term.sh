#!/bin/bash
set -e

echo "🚀 Starting UI Term as user 'app'..."

# Drop privileges and start the application
# The base entrypoint.sh already handled Tailscale initialization
exec gosu app uvicorn main:app --host 0.0.0.0 --port ${USER_AGENT_PORT:-8085}
