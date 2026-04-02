# -*- coding: utf-8 -*-
"""Memory write tool - proxied to GCP Memory Orchestrator.

Allows the agent to explicitly record facts, decisions, or observations
to the long-term memory system (MuninnDB + MemU).
"""
import logging
import os
import sys

import httpx
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

# Add secrets wrapper to path
sys.path.insert(0, '/Users/danexall/biomimetics/config_copaw/bin')
try:
    from copaw_secrets_wrapper import fetch_secret
except ImportError:
    def fetch_secret(name): return None

logger = logging.getLogger(__name__)

GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
)


async def _gcp_memory_write(content: str, metadata: dict = None) -> ToolResponse:
    """Store a fact in the GCP Memory Orchestrator with authentication."""
    try:
        if metadata is None:
            metadata = {}
        
        # Ensure source is attributed to the agent
        metadata.setdefault("source", "copaw_agent")
        metadata.setdefault("type", "explicit_memory")

        # Retrieve the headless authorization token via the designated wrapper
        token = fetch_secret("service-account-token")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            resp = await client.post(
                GCP_GATEWAY_URL,
                json={
                    "operation": "memorize",
                    "content": content,
                    "metadata": metadata,
                    "user_id": "copaw",
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") == "success" or "id" in data:
            return ToolResponse(
                content=[TextBlock(type="text", text="Fact successfully recorded to long-term memory.")],
            )
        else:
            error_msg = data.get("error", "Unknown error")
            return ToolResponse(
                content=[TextBlock(type="text", text=f"Failed to record memory: {error_msg}")],
            )

    except Exception as e:
        logger.warning("GCP memory write error: %s", e)
        return ToolResponse(
            content=[TextBlock(type="text", text=f"Memory write failed: {e}")],
        )


def create_memory_write_tool(memory_manager=None):
    """Create a memorize tool function.
    
    Strictly proxies to the GCP Memory Orchestrator to enforce statelessness.
    Local MemoryManager is ignored.
    """

    async def memorize(
        content: str,
        importance: int = 5,
        category: str = "general",
    ) -> ToolResponse:
        """
        Store a new fact or observation in long-term memory.

        This tool persists information to the GCP Memory Orchestrator. 
        Use this to record important user preferences, completed tasks, 
        discovered facts, or significant decisions.

        Args:
            content (`str`):
                The fact or observation to be remembered.
            importance (`int`, optional):
                Priority from 1-10 (1=background, 10=critical). Defaults to 5.
            category (`str`, optional):
                Classification (e.g., 'preference', 'fact', 'todo'). 
                Defaults to 'general'.

        Returns:
            `ToolResponse`:
                Confirmation of storage and the assigned memory ID.
        """
        metadata = {
            "importance": importance,
            "category": category,
        }
        # Strictly use GCP Memory Orchestrator proxy
        return await _gcp_memory_write(content, metadata)

    return memorize
