#!/bin/sh
# Entrypoint script - runs both supergateway and auth gateway

# Start supergateway in background (GitHub MCP server)
# Listens on port 8081 internally
npx -y supergateway --stdio "npx -y @modelcontextprotocol/server-github" --port 8081 --host 127.0.0.1 &

# Wait for supergateway to start
sleep 3

# Start auth gateway in foreground (proxies to supergateway on 8081)
# Listens on port 8080 externally
export UPSTREAM_URL="http://127.0.0.1:8081"
python3 github_mcp_auth_gateway.py
