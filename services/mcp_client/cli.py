#!/usr/bin/env python3
"""
ARCA MCP Client CLI
Executes MCP tools via the MCP Client Container infrastructure.
"""
import asyncio
import json
import argparse
import sys
import os
import aiohttp

# Ensure we can import from mcp_client.py
async def run_tool(tool_name: str, args: dict, mcp_url: str):
    # Tool Name Mapping (Client -> Server)
    if tool_name == "mcp_agent_dispatch":
        tool_name = "dispatch_agent"
        
    print(f"🔧 Invoking Tool: {tool_name} on {mcp_url}")
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args
        },
        "id": "cli-execution"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(mcp_url, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    print(f"❌ HTTP Error {response.status}: {text}")
                    sys.exit(1)
                
                result_json = await response.json()
                
                if "error" in result_json:
                    print(f"❌ RPC Error: {json.dumps(result_json['error'], indent=2)}")
                    sys.exit(1)
                    
                result = result_json.get("result", {})
                print(json.dumps(result, indent=2))
                sys.exit(0)
                
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP Client CLI")
    parser.add_argument("--tool", required=True, help="Name of the MCP tool to call")
    parser.add_argument("--args", required=True, help="JSON string of arguments")
    parser.add_argument("--url", default="http://localhost:8092/mcp", help="MCP Endpoint URL")
    
    args = parser.parse_args()
    
    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON arguments: {e}")
        sys.exit(1)
        
    asyncio.run(run_tool(args.tool, tool_args, args.url))
