#!/usr/bin/env python3
"""
Query the Observation Agent via MCP system_analysis tool to diagnose why the code maintainer agent hung on its last job.
"""
import asyncio
import json
import sys
import aiohttp

async def main():
    mcp_url = "http://localhost:8092/mcp"
    tool_name = "system_analysis"
    args = {
        "query": "Why did the code maintainer agent hang on its last job? Please review logs, resource status, and any relevant system state.",
        "depth": "root_cause"
    }
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args
        },
        "id": "observation-query"
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
                print("\n===== Observation Agent Analysis =====\n")
                print(json.dumps(result, indent=2))
                print("\n====================================\n")
                sys.exit(0)
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
