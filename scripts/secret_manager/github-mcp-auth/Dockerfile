# GitHub MCP Server with Authentication
# Multi-stage build: supergateway + auth gateway

FROM node:20-alpine AS base

# Install GitHub MCP server and supergateway
RUN npm install -g @modelcontextprotocol/server-github supergateway

# Auth gateway stage
FROM python:3.11-slim AS auth

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn httpx

# Copy auth gateway
COPY github_mcp_auth_gateway.py .

# Expose auth gateway port
EXPOSE 8080

# Run auth gateway (which proxies to local supergateway)
CMD ["python3", "github_mcp_auth_gateway.py"]
