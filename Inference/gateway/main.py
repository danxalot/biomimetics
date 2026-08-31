#!/usr/bin/env python3
"""
ARCA LLM Gateway - Strict Router Implementation
Version: 2.1 (Rotation + Strict Names + Genesis Guard)
Date: January 15, 2026

Architecture:
- Single Entry Point for all AI traffic.
- STRICT ROTATION: Rotates through specific model variants with strict daily limits.
- PROXY Pattern: Forwards requests to specific backends (Google, Zhipu, Local).
- QUOTA Safety: Enforces limit of 20 requests per day per model variant.
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import httpx
import pytz
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# OpenClaw Integration
try:
    from openclaw_client import get_openclaw_client, openclaw_chat_completion

    OPENCLAW_AVAILABLE = True
except ImportError:
    OPENCLAW_AVAILABLE = False

# Model Configuration - Single Source of Truth
sys.path.insert(0, "/shared")
sys.path.insert(0, "/app/shared")
try:
    from shared.model_config import AVAILABLE_MODELS, DEFAULTS, ROLE_MODELS, get_model

    MODEL_CONFIG_LOADED = True
except ImportError as e:
    MODEL_CONFIG_LOADED = False
    ROLE_MODELS = {}
    DEFAULTS = {}
    AVAILABLE_MODELS = {}

    def get_model(key):
        return ""

    print(f"⚠️ Gateway: Could not import shared.model_config: {e}")


# --- Configuration & imports ---
sys.path.insert(0, "/shared")
sys.path.insert(0, "/app/shared")
try:
    from secrets_provider import secrets
except ImportError:
    # Fallback for local testing or cases where shared is not mounted
    class MockSecrets:
        def get(self, name):
            return os.getenv(name) or os.getenv(name.upper())

    secrets = MockSecrets()

# Configure Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("LLM_Gateway_Strict")

# --- Redis & Quota Configuration ---
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
redis_client = None

# --- GLOBAL INFERENCE LOCK ---
# Ensures only one request hits the local GPU at a time to prevent driver crashes
INFERENCE_LOCK = asyncio.Lock()

# --- CONSTANTS ---
NATIVE_SERVER_URL = (
    f"http://{os.environ.get('LOCAL_LLM_HOST', 'host.docker.internal')}:11435/v1"
)
VISION_SERVER_URL = NATIVE_SERVER_URL
GOOGLE_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# --- STRICT ROTATION MAP (User Defined) ---
# Logic: Primary -> Fallback 1 -> Fallback 2 -> ... (Limit: 20 req/day each)
STRICT_ROTATION = {
    # ALIBABA QWEN (Direct Access - No Rotation)
    "qwen-alibaba-1": [
        {"model": "qwen-max", "limit": 1000000, "provider": "alibaba_1"}
    ],
    "qwen-alibaba-2": [
        {"model": "qwen-max", "limit": 1000000, "provider": "alibaba_2"}
    ],
    "qwen-vl-alibaba-1": [
        {"model": "qwen-vl-max", "limit": 1000000, "provider": "alibaba_1"}
    ],
    "qwen-vl-alibaba-2": [
        {"model": "qwen-vl-max", "limit": 1000000, "provider": "alibaba_2"}
    ],
    # Qwen3 Variants (Mapped to Plus/Max for now until strictly named)
    "qwen3-inference": [
        {
            "model": "qwen-plus",
            "limit": 1000000,
            "provider": "alibaba_1",
        },  # Use Account 1 default
        {"model": "qwen-plus", "limit": 1000000, "provider": "alibaba_2"},
    ],
    "qwen3-vl-inference": [
        {"model": "qwen-vl-max", "limit": 1000000, "provider": "alibaba_1"}
    ],
    # GEMINI 3.1 FLASH LITE PREVIEW
    "gemini-3.1-flash-lite-preview": [
        {"model": "gemini-3.1-flash-lite-preview", "limit": 20, "provider": "google"}
    ],
    # GEMINI 3 FLASH (UserConfirmed: latest=3.0)
    "gemini-3-flash": [
        {"model": "gemini-flash-latest", "limit": 20, "provider": "google"},
        {"model": "gemini-3-flash-preview", "limit": 20, "provider": "google"},
    ],
    # GEMINI 3 FLASH LITE
    # (Inferred: flash-lite-latest corresponds to 3.0 series if flash-latest does)
    "gemini-3-flash-lite": [
        {"model": "gemini-flash-lite-latest", "limit": 20, "provider": "google"}
    ],
    # GEMINI 2.5 FLASH
    "gemini-2.5-flash": [
        {"model": "gemini-2.5-flash", "limit": 20, "provider": "google"},
        {
            "model": "gemini-2.5-flash-preview-09-2025",
            "limit": 20,
            "provider": "google",
        },
    ],
    # GEMINI 2.5 FLASH LITE
    "gemini-2.5-flash-lite": [
        {"model": "gemini-2.5-flash-lite", "limit": 20, "provider": "google"},
        {
            "model": "gemini-2.5-flash-lite-preview-09-2025",
            "limit": 20,
            "provider": "google",
        },
    ],
    # GEMINI 2.0 FLASH
    "gemini-2.0-flash": [
        {"model": "gemini-2.0-flash", "limit": 20, "provider": "google"},
        {"model": "gemini-2.0-flash-exp", "limit": 20, "provider": "google"},
        {"model": "gemini-2.0-flash-001", "limit": 20, "provider": "google"},
    ],
    # GEMINI 2.0 FLASH LITE
    "gemini-2.0-flash-lite": [
        {"model": "gemini-2.0-flash-lite", "limit": 20, "provider": "google"},
        {"model": "gemini-2.0-flash-lite-preview", "limit": 20, "provider": "google"},
        {
            "model": "gemini-2.0-flash-lite-preview-02-05",
            "limit": 20,
            "provider": "google",
        },
        {"model": "gemini-2.0-flash-lite-001", "limit": 20, "provider": "google"},
    ],
    # SPECIALIZED
    "gemini-robotics": [
        {"model": "gemini-robotics-er-1.5-preview", "limit": 20, "provider": "google"}
    ],
    # We will enable this IF the test passes, otherwise it might fail.
    # User asked to test it. If test fails, we can comment it out or leave as experimental.
    "gemini-2.0-flash-thinking": [
        {"model": "gemini-2.0-flash-thinking-exp", "limit": 20, "provider": "google"},
        {
            "model": "gemini-2.0-flash-thinking-exp-1219",
            "limit": 20,
            "provider": "google",
        },
    ],
    # GEMMA 3 FAMILY (Restored)
    "gemma-3-27b-it": [
        {"model": "gemma-3-27b-it", "limit": 14400, "provider": "google"}
    ],
    "gemma-3-12b-it": [
        {"model": "gemma-3-12b-it", "limit": 14400, "provider": "google"}
    ],
    "gemma-3-4b-it": [{"model": "gemma-3-4b-it", "limit": 14400, "provider": "google"}],
    "gemma-3-1b-it": [{"model": "gemma-3-1b-it", "limit": 14400, "provider": "google"}],
    # GLM / ZHIPU (Specific Names)
    "glm-4.6v-flash": [{"model": "glm-4.6v-flash", "limit": 100, "provider": "zhipu"}],
    "glm-4.7": [{"model": "glm-4.7", "limit": 100, "provider": "zhipu"}],
    # LOCAL OPS (Keep existing, High Limit)
    "deepseek-r1-distill-qwen-1.5b": [
        {
            "model": "DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M",
            "limit": 100000,
            "provider": "local",
        }
    ],
    "devstral-2": [{"model": "devstral-2", "limit": 100000, "provider": "local_v2"}],
    "maintainer": [{"model": "qwen3vl", "limit": 100000, "provider": "local_v2"}],
    "serena": [{"model": "qwen3vl", "limit": 100000, "provider": "local_v2"}],
    "qwen3-vl-2b": [{"model": "qwen3vl", "limit": 100000, "provider": "local_vision"}],
    "qwen 3 vl 2B q4kmgguf": [
        {"model": "qwen3vl", "limit": 100000, "provider": "local_vision"}
    ],
    "vision": [{"model": "qwen3vl", "limit": 100000, "provider": "local_vision"}],
    "qwen3vl": [{"model": "qwen3vl", "limit": 100000, "provider": "local_v2"}],
    "Qwen3VL-2B-Instruct-Q8_0.gguf": [
        {
            "model": "Qwen3VL-2B-Instruct-Q8_0.gguf",
            "limit": 100000,
            "provider": "local_v2",
        }
    ],
    "qwen3-4b-thinking": [
        {"model": "qwen3-4b-thinking", "limit": 100000, "provider": "local_v2"}
    ],
    "qwen-3-vl-Instruct-2B-Q8.gguf": [
        {
            "model": "Qwen3VL-2B-Instruct-Q8_0.gguf",
            "limit": 100000,
            "provider": "local_v2",
        }
    ],
    "qwen-3-vl-Instruct-0.6B-Q8.gguf": [
        {"model": "Qwen3-0.6B-Q4_K_M.gguf", "limit": 100000, "provider": "local_v2"}
    ],
    "Qwen3-0.6B-Q4_K_M.gguf": [
        {"model": "Qwen3-0.6B-Q4_K_M.gguf", "limit": 100000, "provider": "local_v2"}
    ],
    "ARCA_FAST_MODEL": [
        {"model": "Qwen3-0.6B-Q4_K_M.gguf", "limit": 100000, "provider": "local_v2"}
    ],
    "ARCA_OCI_OPS_MODEL": [
        {"model": "qwen3-vl-Instruct-0.6B", "limit": 100000, "provider": "local_v2"}
    ],
    # ARCA CHAT — routes Pythia-interpreted prompts through the same local LLM
    # No separate port needed; geometry_onnx_interpreter translates vectors to text
    "arca_chat": [{"model": "Qwen3VL-2B-Instruct-Q8_0.gguf", "limit": 100000, "provider": "local_v2"}],
    # OPENCLAW (Default Agent for All Chat)
    "openclaw-agent": [
        {"model": "openclaw-agent", "limit": 100000, "provider": "openclaw"}
    ],
    "openclaw": [
        {"model": "openclaw-agent", "limit": 100000, "provider": "openclaw_http"}
    ],
    # CLAUDE 4.5 / 4.6 (NEW PRIMARY)
    "claude-haiku-4-5": [
        {"model": "claude-haiku-4-5", "limit": 1000, "provider": "azure_foundry"}
    ],
    "claude-sonnet-4-5": [
        {"model": "claude-sonnet-4-5", "limit": 1000, "provider": "azure_foundry"}
    ],
    "claude-opus-4-6": [
        {"model": "claude-opus-4-6", "limit": 1000, "provider": "azure_foundry"}
    ],
}

AZURE_FOUNDRY_ENDPOINT = os.getenv(
    "AZURE_FOUNDRY_ENDPOINT",
    "https://arca-3412-resource.services.ai.azure.com/api/projects/arca-3412/chat/completions?api-version=2024-10-21-preview",
)
AZURE_FOUNDRY_KEY = (
    os.getenv("AZURE_FOUNDRY_KEY")
    or secrets.get("AZURE_FOUNDRY_KEY")
    or secrets.get("azure-foundry-key")
    or secrets.get("azure_foundry_key")
    or ""
)

ALIBABA_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


async def handle_alibaba_request(model_id: str, payload: dict, provider: str):
    """
    Handle requests to Alibaba Cloud (DashScope) via OpenAI-compatible endpoint.
    Supports two accounts: alibaba_1 and alibaba_2.
    """
    if provider == "alibaba_1":
        api_key = secrets.get("ALIBABA_API_KEY")
    elif provider == "alibaba_2":
        api_key = secrets.get("alibaba2_api_key")
    else:
        api_key = secrets.get("ALIBABA_API_KEY")  # Default

    if not api_key:
        logger.error(f"Missing API Key for {provider}")
        raise HTTPException(status_code=500, detail=f"Missing API Key for {provider}")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # DashScope expects model in payload
    payload["model"] = model_id

    # Enforce Qwen-specific params if needed?
    # Usually OpenAI compatible works out of the box.

    async with httpx.AsyncClient() as client:
        url = f"{ALIBABA_BASE_URL}/chat/completions"
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=120.0)
            if resp.status_code != 200:
                logger.error(f"Alibaba Error ({resp.status_code}): {resp.text}")
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.ReadTimeout:
            logger.error(f"Alibaba Timeout for {model_id}")
            raise HTTPException(status_code=504, detail="Upstream Timeout")
        except Exception as e:
            logger.error(f"Alibaba Exception: {e}")
            raise HTTPException(status_code=500, detail=str(e))


async def handle_azure_foundry_request(model_id: str, payload: dict):
    headers = {
        "Authorization": f"Bearer {AZURE_FOUNDRY_KEY}",
        "Content-Type": "application/json",
    }
    # Azure Foundry expects deployment name in the model field
    payload["model"] = model_id
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            AZURE_FOUNDRY_ENDPOINT, json=payload, headers=headers, timeout=120.0
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


# --- DEPENDENCIES ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global redis_client
    logger.info("🚀 Starting ARCA Strict Router Gateway v2.1...")

    try:
        redis_client = redis.from_url(
            REDIS_URL, encoding="utf-8", decode_responses=True
        )
        await redis_client.ping()
        logger.info("✅ Connected to Redis")
    except Exception as e:
        logger.warning(
            f"⚠️ Redis connection failed: {e}. Quota tracking disabled (FAIL OPEN)."
        )
        redis_client = None

    yield

    # Shutdown
    if redis_client:
        await redis_client.close()


app = FastAPI(title="ARCA Strict Gateway", version="2.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CORE LOGIC ---


async def check_quota_and_get_variant(model_group: str) -> Optional[dict]:
    """
    Checks quota for a model group using rotation logic.
    Returns the first available variant configuration, or None if all exhausted.
    """
    if model_group not in STRICT_ROTATION:
        return None

    variants = STRICT_ROTATION[model_group]
    today = datetime.now().strftime("%Y-%m-%d")

    for variant in variants:
        model_name = variant["model"]
        limit = variant.get("limit", 20)

        # Redis Key: quota:strict:MODEL_NAME:DATE
        # e.g. quota:strict:gemini-flash-latest:2026-01-15
        key = f"quota:strict:{model_name}:{today}"

        if not redis_client:
            return variant  # Fail open if Redis down

        # Check current usage
        current = await redis_client.get(key)
        current = int(current) if current else 0

        if current < limit:
            # Found a valid variant with quota!
            # Increment it NOW (pessimistic locking) to reserve the slot
            await redis_client.incr(key)
            if current == 0:
                await redis_client.expire(key, 90000)

            logger.info(
                f"✅ Quota OK: {model_group} -> {model_name} ({current + 1}/{limit})"
            )
            return variant
        else:
            logger.info(
                f"⚠️ Quota Exhausted: {model_name} ({current}/{limit}). Rotating..."
            )

    return None  # All variants exhausted


# --- ENDPOINTS ---


@app.get("/health")
async def health():
    # Deep check upstream native server
    status = "healthy"
    upstream = "unknown"
    try:
        async with httpx.AsyncClient() as client:
            # Ping the native server health
            resp = await client.get(
                f"http://{os.environ.get('LOCAL_LLM_HOST', 'host.docker.internal')}:11435/health",
                timeout=2.0,
            )
            if resp.status_code == 200:
                upstream = "available"
            else:
                upstream = "error"
                status = "degraded"
    except Exception:
        upstream = "down"
        status = "degraded"

    return {
        "status": status,
        "mode": "strict_router_v2.1",
        "rotation": "active",
        "upstream_host_11435": upstream,
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    requested_model = data.get("model")
    logger.info(f"Gateway Ingress: {requested_model}")

    # 0. Role-based resolution: if the model name matches a role in ROLE_MODELS,
    #    resolve it to the actual model name before routing.
    #    Skip if the model already has its own STRICT_ROTATION entry (e.g. arca_chat).
    genesis_agent = request.headers.get("X-Genesis-Agent", "")
    resolved_from_role = False
    if (
        MODEL_CONFIG_LOADED
        and requested_model in ROLE_MODELS
        and requested_model not in STRICT_ROTATION
    ):
        resolved_model = ROLE_MODELS[requested_model]
        logger.info(
            f"Role resolution: {requested_model} -> {resolved_model} (agent: {genesis_agent})"
        )
        requested_model = resolved_model
        resolved_from_role = True

    # 1. Routing & Rotation
    variant = await check_quota_and_get_variant(requested_model)

    if not variant:
        logger.warning(
            f"❌ Route Rejected: {requested_model} (Quota Exhausted or Unknown)"
        )
        if requested_model in STRICT_ROTATION:
            raise HTTPException(
                status_code=429,
                detail=f"Daily quota exhausted for all variants of {requested_model}",
            )
        else:
            raise HTTPException(
                status_code=404, detail=f"Unknown model: {requested_model}"
            )

    target_model = variant["model"]
    provider = variant.get("provider", "google")

    # 2. Genesis Verification (Header Check)
    # MANDATORY for all gateway calls as per Execution Firewall SOP
    chain_header = request.headers.get("X-Genesis-Chain")
    if not chain_header:
        logger.warning(
            f"❌ Access Denied: Missing X-Genesis-Chain header for {requested_model}"
        )
        raise HTTPException(
            status_code=403, detail="Genesis Chain Authorization Required"
        )

    # 3. Handle Provider
    try:
        if provider == "azure_foundry":
            return await handle_azure_foundry_request(target_model, data)
        elif provider == "openclaw" and OPENCLAW_AVAILABLE:
            # Route to OpenClaw agent (default for all chat) via WebSocket
            genesis_headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower().startswith("x-genesis-")
            }
            return await openclaw_chat_completion(
                data.get("messages", []), genesis_headers
            )
        elif provider == "openclaw_http":
            # Route to OpenClaw via OpenAI-compatible HTTP API
            return await handle_openclaw_http_request(
                target_model, data, request.headers
            )
        elif provider == "zhipu":
            return await handle_zhipu_request(target_model, data)
        elif provider in ["alibaba_1", "alibaba_2"]:
            return await handle_alibaba_request(target_model, data, provider)
        elif provider in ["local", "local_vision", "local_v2", "local_pythia"]:
            # Forward headers for local requests
            return await handle_local_request(
                target_model, data, provider, request.headers
            )
        else:  # Google
            return await handle_google_request(target_model, data)

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        logger.error(f"Upstream Error: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)} | {tb}")


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    """
    Proxy for embedding requests, enforcing the execution firewall.
    """
    chain_header = request.headers.get("X-Genesis-Chain")
    if not chain_header:
        logger.warning(
            "❌ Access Denied: Missing X-Genesis-Chain header for embeddings"
        )
        raise HTTPException(
            status_code=403, detail="Genesis Chain Authorization Required"
        )

    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Determine backend
    # Default: Local llama_cpp container (8081)
    # OCI: Remote embedding service (8082)
    OCI_EMBEDDING_URL = os.environ.get(
        "OCI_EMBEDDING_URL", "http://100.70.0.13:8082/v1/embeddings"
    )
    LOCAL_EMBEDDING_URL = "http://llama_cpp:8081/v1/embeddings"

    req_model = data.get("model", "")

    base_url = LOCAL_EMBEDDING_URL
    if (
        "-oci" in req_model.lower()
        or os.environ.get("USE_OCI_EMBEDDING", "false").lower() == "true"
    ):
        base_url = OCI_EMBEDDING_URL
        logger.info(f"Routing embedding request to OCI: {base_url}")

    if "qwen" in req_model.lower() and "embedding" in req_model.lower():
        return await handle_alibaba_embedding(data)

    # Extract headers to forward
    forward_headers = {"X-Genesis-Chain": chain_header}
    for key in ["X-Genesis-Signature", "X-Genesis-Agent"]:
        val = request.headers.get(key)
        if val:
            forward_headers[key] = val

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            base_url, json=data, headers=forward_headers, timeout=60.0
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


async def handle_alibaba_embedding(payload: dict):
    api_key = secrets.get("ALIBABA_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing Alibaba API Key")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{ALIBABA_BASE_URL}/embeddings"
    if "model" not in payload:
        payload["model"] = "text-embedding-v3"

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=60.0)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


async def handle_zhipu_request(model_id: str, payload: dict):
    api_key = secrets.get("zhipu_api_key") or secrets.get("bigmodel_api_key")
    if not api_key:
        api_key = "578f89f7cf854a90a6083dc04f33d656.jqhgtjeEsq5fODp9"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload["model"] = model_id
    if "max_tokens" in payload:
        del payload["max_tokens"]

    async with httpx.AsyncClient() as client:
        url = f"{ZHIPU_BASE_URL}/chat/completions"
        resp = await client.post(url, json=payload, headers=headers, timeout=60.0)
        if resp.status_code != 200:
            logger.error(f"Zhipu Error: {resp.text}")
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


async def handle_openclaw_http_request(
    model_id: str, payload: dict, headers: Optional[Any] = None
):
    url = os.getenv(
        "OPENCLAW_HTTP_URL", "http://100.117.154.85:18789/v1/chat/completions"
    )
    forward_headers = {}
    if headers:
        for key in [
            "X-Genesis-Chain",
            "X-Genesis-Signature",
            "X-Genesis-Agent",
            "X-Genesis-Session-ID",
            "X-Genesis-Task-ID",
        ]:
            val = headers.get(key)
            if val:
                forward_headers[key] = val
    token = secrets.get("openclaw_api_key")
    if token:
        forward_headers["Authorization"] = f"Bearer {token}"
    payload["model"] = "openclaw-agent"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, json=payload, headers=forward_headers, timeout=300.0
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


async def handle_local_request(
    model_id: str, payload: dict, provider: str, headers: Optional[Any] = None
):
    # local/local_v2/local_vision → port 11435 (maintainers)
    # local_pythia → port 11436 (Pythia chat interaction)
    if provider == "local_pythia":
        port = 11436
    else:
        port = 11435
    base_url = f"http://{os.environ.get('LOCAL_LLM_HOST', 'host.docker.internal')}:{port}/v1/chat/completions"
    payload["model"] = model_id
    forward_headers = {}
    if headers:
        for key in ["X-Genesis-Chain", "X-Genesis-Signature", "X-Genesis-Agent"]:
            val = headers.get(key)
            if val:
                forward_headers[key] = val
    async with INFERENCE_LOCK:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                base_url, json=payload, headers=forward_headers, timeout=300.0
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()


async def handle_google_request(model_id: str, payload: dict):
    payload["model"] = model_id
    if "gemma" in model_id.lower():
        sanitized_messages = []
        input_messages = payload.get("messages", [])
        for msg in input_messages:
            new_msg = msg.copy()
            role = new_msg.get("role")
            if role == "assistant":
                if "tool_calls" in new_msg:
                    del new_msg["tool_calls"]
                if new_msg.get("content") is None:
                    new_msg["content"] = ""
            elif role == "tool":
                new_msg["role"] = "user"
                content = new_msg.get("content", "")
                new_msg["content"] = f"```tool_output\n{content}\n```"
                if "tool_call_id" in new_msg:
                    del new_msg["tool_call_id"]
                if "name" in new_msg:
                    del new_msg["name"]
            sanitized_messages.append(new_msg)
        payload["messages"] = sanitized_messages
        messages = payload.get("messages", [])
        system_instructions = ""
        to_remove = []
        for i, msg in enumerate(messages):
            if msg["role"] == "system" or msg["role"] == "developer":
                content = msg.get("content", "")
                if isinstance(content, str):
                    system_instructions += f"{content}\n\n"
                to_remove.append(i)
        for i in reversed(to_remove):
            messages.pop(i)
        tool_desc = ""
        if "tools" in payload:
            tools = payload.pop("tools")
            if "tool_choice" in payload:
                del payload["tool_choice"]
            tool_desc = "\n\n### Available Tools\n"
            for t in tools:
                fn = t.get("function", {})
                tool_desc += f"- **{fn.get('name')}**: {fn.get('description')}\n"
                tool_desc += (
                    f"  Parameters: {json.dumps(fn.get('parameters'), indent=None)}\n"
                )
            tool_desc += '\n### Tool Usage Format\nTo use a tool, output JSON inside a block like this:\n```tool_code\n{"name": "func", "arguments": {"k": "v"}}\n```\n'
        if messages:
            user_msg = next((m for m in messages if m["role"] == "user"), None)
            if user_msg:
                full_injection = f"{system_instructions}{tool_desc}"
                if full_injection.strip():
                    if isinstance(user_msg["content"], str):
                        user_msg["content"] = (
                            f"{full_injection}\n\n{user_msg['content']}"
                        )
                    elif isinstance(user_msg["content"], list):
                        user_msg["content"].insert(
                            0, {"type": "text", "text": full_injection}
                        )
        else:
            if system_instructions or tool_desc:
                payload["messages"].append(
                    {"role": "user", "content": f"{system_instructions}{tool_desc}"}
                )

    is_stream = payload.get("stream", False)
    api_key = secrets.get("google_ai_studio") or secrets.get("google_api_key")
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        full_url = f"{GOOGLE_OPENAI_BASE}/chat/completions"
        async with httpx.AsyncClient() as client:
            if is_stream:

                async def stream_generator():
                    async with client.stream(
                        "POST", full_url, json=payload, headers=headers, timeout=60.0
                    ) as resp:
                        async for chunk in resp.aiter_bytes():
                            yield chunk

                return StreamingResponse(
                    stream_generator(), media_type="text/event-stream"
                )
            else:
                resp = await client.post(
                    full_url, json=payload, headers=headers, timeout=60.0
                )
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                response_json = resp.json()
                if "gemma" in model_id.lower():
                    try:
                        content = response_json["choices"][0]["message"]["content"]
                        import re
                        import uuid

                        json_text = None
                        match_md = re.search(
                            r"```tool_code\s*({.*?})\s*```", content, re.DOTALL
                        )
                        if match_md:
                            json_text = match_md.group(1).strip()
                        else:
                            match_xml = re.search(
                                r"<tool_code>(.*?)</tool_code>", content, re.DOTALL
                            )
                            if match_xml:
                                json_text = match_xml.group(1).strip()
                        if json_text:
                            try:
                                tool_data = json.loads(json_text)
                                synthetic_call = {
                                    "id": f"call_{uuid.uuid4().hex[:8]}",
                                    "type": "function",
                                    "function": {
                                        "name": tool_data.get("name"),
                                        "arguments": json.dumps(
                                            tool_data.get("arguments", {})
                                        ),
                                    },
                                }
                                msg_obj = response_json["choices"][0]["message"]
                                msg_obj["tool_calls"] = [synthetic_call]
                                response_json["choices"][0]["finish_reason"] = (
                                    "tool_calls"
                                )
                            except json.JSONDecodeError:
                                pass
                    except Exception:
                        pass
                return response_json
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models/config")
async def models_config(request: Request):
    """Expose current model-to-role assignments from model_config.py.
    Agents/nodes can query this to discover available models and roles."""
    chain_header = request.headers.get("X-Genesis-Chain")
    if not chain_header:
        raise HTTPException(
            status_code=403, detail="Genesis Chain Authorization Required"
        )
    if not MODEL_CONFIG_LOADED:
        return {"error": "model_config.py not loaded", "defaults": {}, "roles": {}}
    return {
        "defaults": {k: get_model(k) for k in DEFAULTS},
        "roles": ROLE_MODELS,
        "available_models": list(AVAILABLE_MODELS.keys()),
        "rotation_heads": list(STRICT_ROTATION.keys()),
    }


@app.get("/model-config")
async def get_model_config(request: Request):
    """
    Comprehensive model configuration endpoint with quota status.
    Returns SSOT model assignments, agent configs, and quota information.

    Query Parameters:
    - service: Optional service name to get service-specific overrides
    - include_agents: Include agent node configurations (default: true)
    - include_quotas: Include quota status (default: true)

    Usage:
        GET /model-config
        GET /model-config?service=ui_term
        GET /model-config?include_agents=false&include_quotas=true
    """
    chain_header = request.headers.get("X-Genesis-Chain")
    if not chain_header:
        raise HTTPException(
            status_code=403, detail="Genesis Chain Authorization Required"
        )

    if not MODEL_CONFIG_LOADED:
        return {"error": "model_config.py not loaded"}

    service_name = request.query_params.get("service", None)
    include_agents = (
        request.query_params.get("include_agents", "true").lower() == "true"
    )
    include_quotas = (
        request.query_params.get("include_quotas", "true").lower() == "true"
    )

    response = {
        "ssot": True,
        "source": "/shared/model_config.py",
        "service_override": service_name,
        "defaults": {k: get_model(k, service_name) for k in DEFAULTS},
        "role_models": ROLE_MODELS,
        "available_models": list(AVAILABLE_MODELS.keys()),
        "rotation_heads": list(STRICT_ROTATION.keys()),
    }

    if include_agents:
        try:
            # Import agent configs from shared module
            sys.path.insert(0, "/shared")
            sys.path.insert(0, "/app/shared")
            from shared.model_config import get_all_agent_configs

            response["agent_configs"] = get_all_agent_configs(service_name)
        except ImportError as e:
            response["agent_configs"] = {
                "error": f"Could not load agent configs: {str(e)}"
            }

    if include_quotas and redis_client:
        # Get quota status for all rotation heads
        today = datetime.now().strftime("%Y-%m-%d")
        quotas = {}
        for model_group, variants in STRICT_ROTATION.items():
            for variant in variants:
                model_name = variant["model"]
                limit = variant.get("limit", 20)
                key = f"quota:strict:{model_name}:{today}"
                try:
                    current = await redis_client.get(key)
                    current = int(current) if current else 0
                    quotas[model_name] = {
                        "used": current,
                        "limit": limit,
                        "remaining": max(0, limit - current),
                        "exhausted": current >= limit,
                    }
                except Exception:
                    quotas[model_name] = {
                        "used": 0,
                        "limit": limit,
                        "remaining": limit,
                        "error": "Redis unavailable",
                    }
        response["quotas"] = quotas

    return response


@app.get("/model-config/agent/{agent_name}")
async def get_agent_model_config(agent_name: str, request: Request):
    """
    Get configuration for a specific agent node.

    Path Parameters:
    - agent_name: Agent node name (e.g., "architect_agent", "engineer_agent")

    Query Parameters:
    - service: Optional service name for service-specific overrides

    Returns:
    - Agent configuration with resolved model name and metadata
    """
    chain_header = request.headers.get("X-Genesis-Chain")
    if not chain_header:
        raise HTTPException(
            status_code=403, detail="Genesis Chain Authorization Required"
        )

    if not MODEL_CONFIG_LOADED:
        raise HTTPException(status_code=503, detail="model_config.py not loaded")

    service_name = request.query_params.get("service", None)

    try:
        sys.path.insert(0, "/shared")
        sys.path.insert(0, "/app/shared")
        from shared.model_config import AGENT_NODES, get_agent_config

        if agent_name not in AGENT_NODES:
            raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_name}")

        config = get_agent_config(agent_name, service_name)
        return {
            "agent_name": agent_name,
            "service": service_name,
            "config": config,
            "ssot": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/model-config/roles")
async def get_role_models_config(request: Request):
    """
    Get role-based model mappings.
    Returns the ROLE_MODELS dictionary which maps agent roles to model names.

    Usage:
        GET /model-config/roles
        GET /model-config/roles?service=ui_term
    """
    chain_header = request.headers.get("X-Genesis-Chain")
    if not chain_header:
        raise HTTPException(
            status_code=403, detail="Genesis Chain Authorization Required"
        )

    if not MODEL_CONFIG_LOADED:
        raise HTTPException(status_code=503, detail="model_config.py not loaded")

    service_name = request.query_params.get("service", None)

    return {
        "roles": ROLE_MODELS,
        "service": service_name,
        "ssot": True,
        "note": "Roles are resolved by gateway at request time via STRICT_ROTATION",
    }


@app.post("/v1/system/context")
async def system_context(request: Request):
    """Query Neo4j via Universal Skill Frame pattern for system info.
    Body: {"subject": "<name>", "radius": 4}
    Returns the subgraph context around any Service, Module, Config, or Concept node."""
    chain_header = request.headers.get("X-Genesis-Chain")
    if not chain_header:
        raise HTTPException(
            status_code=403, detail="Genesis Chain Authorization Required"
        )
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    subject = data.get("subject", "")
    radius = min(int(data.get("radius", 4)), 6)  # Cap at 6 hops
    if not subject:
        raise HTTPException(status_code=400, detail="'subject' field required")

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://100.70.0.13:7688")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "arca_secure_password_change_me")

    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        with driver.session() as session:
            # First try exact match, then fuzzy
            result = session.run(
                "MATCH (start) "
                "WHERE start.name CONTAINS $subject OR start.path CONTAINS $subject "
                "WITH start LIMIT 1 "
                "CALL apoc.path.subgraphAll(start, {maxLevel: $radius}) "
                "YIELD nodes, relationships "
                "RETURN start, nodes, relationships",
                subject=subject,
                radius=radius,
            ).single()
            if not result:
                driver.close()
                return {
                    "subject": subject,
                    "found": False,
                    "message": f"'{subject}' not found in Knowledge Graph",
                }

            start_node = dict(result["start"])
            nodes = [dict(n) for n in result["nodes"]]
            rels = [
                {
                    "start": r.start_node.get("name", r.start_node.get("path", "?")),
                    "type": r.type,
                    "end": r.end_node.get("name", r.end_node.get("path", "?")),
                }
                for r in result["relationships"]
            ]
            driver.close()

            return {
                "subject": start_node.get("name") or start_node.get("path"),
                "type": list(result["start"].labels)[0]
                if result["start"].labels
                else "Unknown",
                "found": True,
                "context": {"node_count": len(nodes), "radius": radius},
                "graph": {"nodes": nodes, "relationships": rels},
            }
    except ImportError:
        return {"error": "neo4j driver not installed in gateway container"}
    except Exception as e:
        logger.error(f"Neo4j system context query failed: {e}")
        return {"error": str(e), "subject": subject}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
