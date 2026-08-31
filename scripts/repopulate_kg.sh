#!/bin/bash
# BiOS Knowledge Graph One-Click Repopulation
# Rebuilds the Neo4j Knowledge Graph by crawling infra, code, and workflows.

echo "🚀 Starting BiOS Knowledge Graph Repopulation..."

# 1. Ensure MCP Server is running locally
echo "🔍 Checking local MCP Server..."
if ! curl -s http://localhost:8086/health > /dev/null; then
    echo "⚠️ MCP Server not running. Attempting to start..."
    cd "/Users/danexall/Documents/VS Code Projects/ARCA/services/mcp_server"
    # Note: Using the OCI Neo4j URI directly for the bridge
    NEO4J_URI="bolt://100.70.0.13:7688" ARCA_ROOT="/Users/danexall/Documents/VS Code Projects/ARCA" MCP_CERT_DIR="/Users/danexall/biomimetics/logs/certs" docker compose up -d
    sleep 5
fi

# 2. Run the Repopulation Pipeline
echo "🧠 Running ingestion pipeline..."
python3 "/Users/danexall/biomimetics/scripts/repopulate_knowledge_graph.py"

echo "✅ Repopulation complete. Use 'mcp_graph_visualizer' to verify."
