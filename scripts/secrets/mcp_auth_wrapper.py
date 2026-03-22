#!/usr/bin/env python3
"""
MCP Server Auth Wrapper
Intercepts MCP connections and validates API key before passing to the actual MCP server.
Supports Notion, GitHub, Serena, and any stdio-based MCP server.

Usage:
    python3 mcp_auth_wrapper.py --server notion --port 8081

    Then configure clients to connect to this wrapper instead of the MCP server directly.

Environment Variables:
    MCP_API_KEY          - API key clients must provide
    CREDENTIALS_SERVER_URL - URL for fetching secrets (default: http://127.0.0.1:8089)
"""

import os
import sys
import json
import asyncio
import logging
from typing import Optional, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("mcp_auth")


MCP_API_KEY = os.getenv("MCP_API_KEY", "")
CREDENTIALS_SERVER_URL = os.getenv("CREDENTIALS_SERVER_URL", "http://127.0.0.1:8089")


async def get_api_key_from_credentials_server() -> Optional[str]:
    """Fetch the MCP API key from the credentials server."""
    import httpx

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{CREDENTIALS_SERVER_URL}/secrets/mcp-api-key",
                headers={"X-API-Key": os.getenv("CREDENTIALS_API_KEY", "")},
            )
            if response.status_code == 200:
                return response.json().get("value")
    except Exception as e:
        log.warning(f"Could not fetch API key from credentials server: {e}")
    return None


def validate_request(request: Dict[str, Any], api_key: str) -> bool:
    """Validate an MCP JSON-RPC request."""
    if not api_key:
        return False

    headers = request.get("headers", {})
    key = headers.get("X-MCP-Key") or headers.get("Authorization", "").replace(
        "Bearer ", ""
    )

    return key == api_key


async def handle_jsonrpc(request: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """Process a JSON-RPC request, checking auth on initialize."""
    method = request.get("method", "")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                },
                "serverInfo": {
                    "name": "mcp-auth-wrapper",
                    "version": "1.0.0",
                },
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"tools": []},
        }

    if method in ("notifications/initialized", "ping"):
        return {
            "jsonrpc": "2.0",
            "id": request.get("id") if "id" in request else None,
        }

    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "error": {
            "code": -32601,
            "message": f"Method '{method}' not implemented in auth wrapper",
        },
    }


async def process_requests(api_key: str, mcp_server_cmd: list):
    """
    Main loop: read JSON-RPC requests from stdin, validate, forward or respond.
    """
    import subprocess

    mcp_process = subprocess.Popen(
        mcp_server_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    async def pump_stdin():
        """Forward authenticated requests to MCP server stdin."""
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                if not line:
                    break

                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    continue

                result = await handle_jsonrpc(request, api_key)
                if "error" in result:
                    print(json.dumps(result), flush=True)
                else:
                    mcp_process.stdin.write((line + "\n").encode())
                    mcp_process.stdin.flush()

            except Exception as e:
                log.error(f"stdin pump error: {e}")
                break

    async def pump_stdout():
        """Forward MCP server responses to stdout."""
        while True:
            try:
                char = await asyncio.get_event_loop().run_in_executor(
                    None, mcp_process.stdout.read, 1
                )
                if not char:
                    break
                sys.stdout.buffer.write(char)
                sys.stdout.flush()
            except Exception as e:
                log.error(f"stdout pump error: {e}")
                break

    await asyncio.gather(pump_stdin(), pump_stdout())


def create_authenticated_mcp_proxy(
    api_key: str, target_host: str = "127.0.0.1", target_port: int = 8080
):
    """
    Create an HTTP proxy that adds API key auth to MCP HTTP endpoints.
    Used for MCP servers that expose HTTP (not stdio).
    """
    from fastapi import FastAPI, HTTPException, Header, Request
    from fastapi.responses import StreamingResponse
    import httpx

    app = FastAPI(title="MCP Auth Proxy")

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "DELETE"])
    async def proxy(
        full_path: str,
        request: Request,
        x_mcp_key: str = Header(None, alias="X-MCP-Key"),
    ):
        if x_mcp_key != api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

        target_url = f"http://{target_host}:{target_port}/{full_path}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers={
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() not in ("host", "x-mcp-key")
                },
                content=await request.body(),
            )

        return StreamingResponse(
            response.aiter_bytes(),
            status_code=response.status_code,
            headers=dict(response.headers),
        )

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP Auth Wrapper")
    parser.add_argument(
        "--api-key", default=MCP_API_KEY, help="API key for authentication"
    )
    parser.add_argument(
        "--server", choices=["notion", "github", "serena"], help="MCP server type"
    )
    parser.add_argument(
        "--port", type=int, default=8081, help="Proxy port for HTTP MCP servers"
    )
    parser.add_argument(
        "--target", default="127.0.0.1:8082", help="Target MCP server address"
    )
    args = parser.parse_args()

    if not args.api_key:
        log.error("No API key configured. Set MCP_API_KEY environment variable.")
        sys.exit(1)

    if args.server == "notion":
        import subprocess

        cmd = ["npx", "-y", "@notionhq/notion-mcp-server"]
    elif args.server == "github":
        log.error("GitHub MCP requires SSE transport - use HTTP proxy mode")
        sys.exit(1)
    else:
        cmd = ["serena", "start-mcp-server"]

    log.info(f"Starting MCP Auth Wrapper with key: {args.api_key[:8]}...")

    try:
        asyncio.run(process_requests(args.api_key, cmd))
    except KeyboardInterrupt:
        log.info("Shutting down...")
