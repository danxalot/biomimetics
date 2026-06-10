# -*- coding: utf-8 -*-
"""API routes for dynamic MCP tool execution with JIT authentication."""

import asyncio
import base64
import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from ...config import load_config
from ...constant import WORKING_DIR

router = APIRouter(prefix="/mcp/tool", tags=["mcp_tool"])
logger = logging.getLogger(__name__)

# Strict Invariants
CREDENTIALS_SERVER_URL = "http://127.0.0.1:8089"
CREDENTIALS_API_KEY = ""
BIOS_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

class ToolExecuteRequest(BaseModel):
    """Request body for executing an MCP tool."""
    name: str = Field(..., description="The name of the tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")
    client_key: Optional[str] = Field(None, description="Specific MCP client key to target")

async def _get_auth_token(vault_name: str) -> Optional[str]:
    """Fetch secret from local Azure Credentials Server (Zero-Persistence)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{CREDENTIALS_SERVER_URL}/secrets/{vault_name}",
                headers={"X-API-Key": CREDENTIALS_API_KEY}
            )
            if resp.status_code == 200:
                return resp.json().get("value", "").strip()
            logger.error(f"Failed to fetch secret '{vault_name}': {resp.status_code}")
    except Exception as e:
        logger.error(f"Error connecting to Credentials Server: {e}")
    return None

@router.post("/execute")
async def execute_mcp_tool(
    request: Request,
    payload: ToolExecuteRequest = Body(...)
):
    """
    Dispatcher for MCP tool execution.
    Handles JIT secret retrieval and environment injection.
    """
    manager = request.app.state.mcp_manager
    if not manager:
        raise HTTPException(status_code=500, detail="MCP Manager not initialized")

    clients = await manager.get_clients()
    target_client = None

    # Find the client that provides this tool
    # If client_key is specified, use that one. Otherwise, poll active clients.
    for client in clients:
        if payload.client_key and getattr(client, "key", "") != payload.client_key:
            continue
        
        # Check if the client has this tool
        try:
            tools = await client.list_tools()
            
            # Identify the tool list (handle both raw response and attribute-based access)
            tool_list = []
            if isinstance(tools, list):
                tool_list = tools
            elif hasattr(tools, "tools"):
                tool_list = tools.tools
            elif isinstance(tools, dict) and "tools" in tools:
                tool_list = tools["tools"]
            
            if any(t.get("name") == payload.name if isinstance(t, dict) else getattr(t, "name", "") == payload.name for t in tool_list):
                target_client = client
                break
        except Exception as e:
            logger.error(f"Error listing tools for client '{getattr(client, 'name', 'unknown')}': {e}")
            continue

    if not target_client:
        raise HTTPException(
            status_code=404, 
            detail=f"Tool '{payload.name}' not found in any active MCP client"
        )

    logger.info(f"Executing tool '{payload.name}' via client '{getattr(target_client, 'name', 'unknown')}'")

    # Inject JIT secrets based on tool name or client type
    # This is a specialized mapping for CoPaw BIOS
    env_overrides = {
        "PATH": BIOS_PATH,
        "PYTHONPATH": str(WORKING_DIR / "scripts/copaw/src"),
    }

    # GCP/GDrive Specific
    if "gdrive" in payload.name.lower() or "google" in payload.name.lower():
        gcp_token = await _get_auth_token("gcp-credentials-json")
        if gcp_token:
            # We provide the raw JSON for tools that expect it as an env var or write to temp
            env_overrides["GOOGLE_APPLICATION_CREDENTIALS_JSON"] = gcp_token
            # Some tools might just want the token
            env_overrides["GCP_TOKEN"] = gcp_token

    # Notion Specific
    if "notion" in payload.name.lower():
        notion_token = await _get_auth_token("notion-api-key")
        if notion_token:
            env_overrides["NOTION_TOKEN"] = notion_token

    # GitHub Specific
    if "github" in payload.name.lower():
        github_token = await _get_auth_token("github-api-key")
        if github_token:
            env_overrides["GITHUB_TOKEN"] = github_token

    # Build the isolated environment
    # We start with the client's original env if available
    current_env = {}
    rebuild_info = getattr(target_client, "_copaw_rebuild_info", {})
    if rebuild_info and "env" in rebuild_info:
        current_env = dict(rebuild_info["env"])
    
    current_env.update(env_overrides)

    # Execute the tool
    try:
        # Use the underlying MCP session to execute the tool
        if hasattr(target_client, "session") and target_client.session:
            result = await target_client.session.call_tool(payload.name, payload.arguments)
            return {"status": "success", "result": result}
        else:
            # Fallback to get_callable_function if session is not directly accessible
            func = await target_client.get_callable_function(payload.name, wrap_tool_result=False)
            result = await func(**payload.arguments)
            return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
