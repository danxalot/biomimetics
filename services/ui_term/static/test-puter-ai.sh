#!/bin/bash

# Test script for Puter AI prototype
# Usage: ./test-puter-ai.sh

echo "🚀 ARCA Puter AI Prototype Test"
echo "================================"
echo ""

# Check if MCP server is running
echo "Checking MCP server..."
if curl -s http://localhost:8086/health > /dev/null; then
    echo "✅ MCP server is running on port 8086"
else
    echo "❌ MCP server not running. Start it with:"
    echo "   docker-compose up mcp_server"
    exit 1
fi

echo ""
echo "Starting local web server..."
echo "Visit: http://localhost:8080/puter-ai-prototype.html"
echo ""
echo "Note: Running locally will use Mock AI (Puter.js not available)"
echo "For real AI, deploy to puter.com with: puter deploy"
echo ""

# Start server
python3 -m http.server 8080
