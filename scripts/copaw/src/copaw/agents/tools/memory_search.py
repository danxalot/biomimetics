# -*- coding: utf-8 -*-
"""Memory search tool - proxied to GCP Memory Orchestrator.

When the local MemoryManager is unavailable (e.g. Pydantic config issues),
this tool falls back to querying the GCP Cloud Function Gateway directly,
which combines MuninnDB (working memory) and MemU (archive).
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
    # Fallback if wrapper is not in the expected path
    def fetch_secret(name): return None

logger = logging.getLogger(__name__)

GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
)


async def _gcp_memory_search(query: str, max_results: int, min_score: float) -> ToolResponse:
    """Query the GCP Memory Orchestrator with authentication."""
    try:
        # Retrieve the headless authorization token via the designated wrapper
        token = fetch_secret("service-account-token")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(
                GCP_GATEWAY_URL,
                json={
                    "operation": "search",
                    "query": query,
                    "user_id": "copaw",
                    "max_results": max_results,
                    "min_confidence": min_score,
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            return ToolResponse(
                content=[TextBlock(type="text", text="No relevant memories found.")],
            )

        lines = [f"Found {len(results)} memory result(s) from GCP orchestrator:\n"]
        for i, mem in enumerate(results[:max_results], 1):
            content = mem.get("content", "")
            confidence = mem.get("confidence", 0)
            source = mem.get("source", "unknown")
            if len(content) > 600:
                content = content[:597] + "..."
            lines.append(f"[{i}] [{source}] confidence={confidence:.2f}\n{content}\n")

        return ToolResponse(
            content=[TextBlock(type="text", text="\n".join(lines))],
        )

    except httpx.TimeoutException:
        logger.warning("GCP Memory Orchestrator timeout")
        return ToolResponse(
            content=[TextBlock(type="text", text="Memory search timed out.")],
        )
    except Exception as e:
        logger.warning("GCP memory search error: %s", e)
        return ToolResponse(
            content=[TextBlock(type="text", text=f"Memory search error: {e}")],
        )


def create_memory_search_tool(memory_manager=None):
    """Create a memory_search tool function.
    
    Strictly proxies to the GCP Memory Orchestrator to enforce statelessness.
    Local MemoryManager is ignored.
    """

    async def memory_search(
        query: str,
        max_results: int = 5,
        min_score: float = 0.1,
    ) -> ToolResponse:
        """
        Search memory semantically for relevant context.

        Searches the GCP Memory Orchestrator (MuninnDB + MemU). 
        Use this before answering questions about prior work, decisions, 
        dates, people, preferences, or todos.

        Args:
            query (`str`):
                The semantic search query to find relevant memory snippets.
            max_results (`int`, optional):
                Maximum number of search results to return. Defaults to 5.
            min_score (`float`, optional):
                Minimum similarity score for results. Defaults to 0.1.

        Returns:
            `ToolResponse`:
                Search results with source, confidence, and content.
        """
        # Strictly use GCP Memory Orchestrator proxy
        return await _gcp_memory_search(query, max_results, min_score)

    return memory_search
