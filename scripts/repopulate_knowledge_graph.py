#!/usr/bin/env python3
"""
Master Knowledge Graph Repopulation Script for ARCA.
Runs the full ingestion pipeline to rebuild the Neo4j Knowledge Graph.
REFACTORED: Now routes all operations via the MCP Server (Memory Service) API.
"""

import os
import sys
import logging
import requests
import json
import time
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("repopulation_master")

# Bridge configuration
MCP_URL = os.getenv("DATA_HUB_MCP_URL", "http://localhost:8086/mcp")
HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": "dev-key-bypass",
    "X-Genesis-Chain": "true",
    "X-Genesis-X-Chain": "true"
}

# Base ARCA path (for internal tool context if needed)
ARCA_ROOT = "/Users/danexall/Documents/VS Code Projects/ARCA"

def call_mcp_tool(name, arguments):
    logger.info(f"🛠️ Calling MCP Tool: {name}...")
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments
        },
        "id": 1
    }
    try:
        start_time = time.time()
        response = requests.post(MCP_URL, json=payload, headers=HEADERS, timeout=300)
        duration = time.time() - start_time
        
        if response.status_code != 200:
            logger.error(f"❌ HTTP Error {response.status_code}: {response.text}")
            return None
            
        result = response.json()
        if "error" in result:
            logger.error(f"❌ MCP Error: {result['error']}")
            return None
            
        logger.info(f"✅ {name} complete ({duration:.2f}s)")
        return result.get("result")
    except Exception as e:
        logger.error(f"❌ Request failed: {e}")
        return None

def run_pipeline():
    overall_start = time.time()
    logger.info("🚀 Starting Knowledge Graph Repopulation Pipeline via Memory Service...")

    # 1. Infrastructure Discovery
    logger.info("--- Step 1: Infrastructure Discovery ---")
    call_mcp_tool("discover_infrastructure", {
        "compose_path": "/app/docker-compose.oci.yml",
        "env_path": "/app/docker-compose.oci.yml"
    })

    # 2. Codebase Crawling
    logger.info("--- Step 2: Codebase Crawling ---")
    call_mcp_tool("crawl_codebase", {
        "start_dir": "/app" # The MCP server maps its own /app to ARCA_ROOT
    })

    # 3. Workflow Ingestion
    logger.info("--- Step 3: Workflow Ingestion ---")
    call_mcp_tool("scan_workflows", {})

    # 4. Logic & Agent Discovery
    logger.info("--- Step 4: Logic & Agent Discovery ---")
    call_mcp_tool("discover_logic", {})
    call_mcp_tool("discover_agents", {})

    # 5. Semantic Linking
    logger.info("--- Step 5: Semantic Graph Linking ---")
    call_mcp_tool("run_graph_linking", {})

    overall_duration = time.time() - overall_start
    logger.info(f"🏁 Knowledge Graph Repopulation Pipeline Complete. Total time: {overall_duration:.2f}s")

if __name__ == "__main__":
    run_pipeline()
