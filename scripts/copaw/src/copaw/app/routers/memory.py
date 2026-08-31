# -*- coding: utf-8 -*-
"""Memory router for CoPaw backend gateway to GCP Memory Orchestrator.

Proxies memory search and write requests to the stateless GCP Cloud Function.
"""
import logging
import os
import sys
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any

# --- Secret Fetcher Integration ---
from pathlib import Path
try:
    _scripts_root = str(Path(__file__).resolve().parents[5])
    if _scripts_root not in sys.path:
        sys.path.append(_scripts_root)
    from secret_manager.copaw_secret_fetcher import get_secret_async
except Exception as e:
    logger.warning(f"Could not initialize secret fetcher in memory router: {e}")
    async def get_secret_async(name: str) -> str | None: return None
# ----------------------------------


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])

GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
)

class MemorySearchRequest(BaseModel):
    query: str
    max_results: Optional[int] = 5
    min_confidence: Optional[float] = 0.1

class MemoryWriteRequest(BaseModel):
    content: str
    metadata: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = "copaw"

@router.post("/search")
async def search_memory(request: MemorySearchRequest):
    """Proxy semantic search to GCP Memory Orchestrator."""
    token = await get_secret_async("service-account-token")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GCP_GATEWAY_URL,
                json={
                    "operation": "search",
                    "query": request.query,
                    "user_id": "copaw",
                    "max_results": request.max_results,
                    "min_confidence": request.min_confidence,
                },
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"GCP memory search proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"GCP Memory Gateway error: {str(e)}")

@router.post("/write")
async def write_memory(request: MemoryWriteRequest):
    """Proxy memory storage to GCP Memory Orchestrator."""
    token = await get_secret_async("service-account-token")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GCP_GATEWAY_URL,
                json={
                    "operation": "write",
                    "content": request.content,
                    "metadata": request.metadata or {},
                    "user_id": request.user_id or "copaw",
                },
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"GCP memory write proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"GCP Memory Gateway error: {str(e)}")
