"""
MCP Pythia Bridge Tool

Enables MCP agents to access Pythia's geometric reasoning and concept memory capabilities.
Wraps the geometry_onnx_interpreter_v2 REST API (:8096) via Tailscale mesh VPN.

Endpoints exposed:
- pythia_encode(text) → geometric encoding
- pythia_predict(concept) → attractor prediction
- pythia_surprise(observation) → novelty assessment
- pythia_resonate(query) → Kuramoto coherence check
- pythia_store_concept(name, vector) → concept memory write

Author: ARCA System
Date: March 2026
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# MCP FastMCP
try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("mcp.server.fastmcp not available")

# HTTP client
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    try:
        import requests

        REQUESTS_AVAILABLE = True
    except ImportError:
        REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Initialize FastMCP if available
if MCP_AVAILABLE:
    mcp = FastMCP("mcp-pythia-bridge")
else:
    mcp = None


# ============================================================================
# Configuration
# ============================================================================

# Pythia service endpoint - use Tailscale hostname resolution
PYTHIA_HOST = os.getenv("PYTHIA_HOST", "geometry-onnx-interpreter")
PYTHIA_PORT = int(os.getenv("PYTHIA_PORT", "8096"))
PYTHIA_BASE_URL = f"http://{PYTHIA_HOST}:{PYTHIA_PORT}"

# Alternative: Direct OCI access via Tailscale IP
OCI_TAILSCALE_IP = os.getenv("OCI_TAILSCALE_IP", "100.70.0.13")
OCI_DIRECT_URL = f"http://{OCI_TAILSCALE_IP}:{PYTHIA_PORT}"

# Fallback to localhost for local testing
LOCAL_URL = "http://localhost:8096"

# Timeout settings
DEFAULT_TIMEOUT = float(os.getenv("PYTHIA_TIMEOUT", "30.0"))


# ============================================================================
# Client Implementation
# ============================================================================


class PythiaBridgeClient:
    """
    Client for Pythia geometry_onnx_interpreter API

    Supports both httpx (async) and requests (sync) backends.
    Uses Tailscale hostname resolution when available.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        use_httpx: bool = True,
    ):
        """
        Initialize Pythia Bridge Client

        Args:
            base_url: Pythia service URL (defaults to PYTHIA_BASE_URL)
            timeout: Request timeout in seconds
            use_httpx: Prefer httpx for async support
        """
        self.base_url = base_url or PYTHIA_BASE_URL
        self.timeout = timeout
        self.use_httpx = use_httpx and HTTPX_AVAILABLE

        # Connection state
        self._client_async = None
        self._client_sync = None

        logger.info(f"🔮 PythiaBridgeClient initialized: {self.base_url}")

    def _get_sync_client(self):
        """Get synchronous HTTP client"""
        if self._client_sync is None:
            if REQUESTS_AVAILABLE:
                self._client_sync = requests.Session()
            elif HTTPX_AVAILABLE:
                self._client_sync = httpx.Client()
            else:
                raise RuntimeError("No HTTP client available (need httpx or requests)")
        return self._client_sync

    async def _get_async_client(self):
        """Get asynchronous HTTP client"""
        if self._client_async is None:
            if HTTPX_AVAILABLE:
                self._client_async = httpx.AsyncClient()
            else:
                raise RuntimeError("httpx not available for async requests")
        return self._client_async

    async def close(self):
        """Close HTTP clients"""
        if self._client_async:
            await self._client_async.aclose()
            self._client_async = None
        if self._client_sync:
            self._client_sync.close()
            self._client_sync = None

    # ========================================================================
    # Core Pythia API Methods
    # ========================================================================

    async def encode(self, text: str) -> Dict[str, Any]:
        """
        Encode text/concept into geometric representation

        Calls: POST /encode

        Args:
            text: Text or concept to encode

        Returns:
            Dict with vector_512, vector_2048, inference_time_ms
        """
        endpoint = f"{self.base_url}/encode"

        try:
            if HTTPX_AVAILABLE:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        endpoint, json={"text": text}, timeout=self.timeout
                    )
                    response.raise_for_status()
                    return response.json()
            elif REQUESTS_AVAILABLE:
                response = requests.post(
                    endpoint, json={"text": text}, timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            else:
                raise RuntimeError("No HTTP client available")

        except Exception as e:
            logger.error(f"Pythia encode failed: {e}")
            return {"error": str(e), "vector_512": None, "vector_2048": None}

    def encode_sync(self, text: str) -> Dict[str, Any]:
        """Synchronous wrapper for encode"""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.encode(text))

    async def predict_concept(self, concept: str) -> Dict[str, Any]:
        """
        Predict concept outcome using Pythia Oracle

        Calls: POST /predict/concept

        Args:
            concept: Concept name or description

        Returns:
            Dict with prediction, confidence, geometric_state
        """
        endpoint = f"{self.base_url}/predict/concept"

        try:
            if HTTPX_AVAILABLE:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        endpoint, json={"concept": concept}, timeout=self.timeout
                    )
                    response.raise_for_status()
                    return response.json()
            elif REQUESTS_AVAILABLE:
                response = requests.post(
                    endpoint, json={"concept": concept}, timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            else:
                raise RuntimeError("No HTTP client available")

        except Exception as e:
            logger.error(f"Pythia predict_concept failed: {e}")
            return {"error": str(e), "prediction": None}

    async def assess_surprise(self, observation: str) -> Dict[str, Any]:
        """
        Assess novelty/surprise of an observation

        Calls: POST /assess_surprise

        Args:
            observation: Observation or event description

        Returns:
            Dict with surprise_score (0-1), novelty_detected, curiosity_signal
        """
        endpoint = f"{self.base_url}/assess_surprise"

        try:
            if HTTPX_AVAILABLE:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        endpoint,
                        json={"observation": observation},
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    return response.json()
            elif REQUESTS_AVAILABLE:
                response = requests.post(
                    endpoint, json={"observation": observation}, timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            else:
                raise RuntimeError("No HTTP client available")

        except Exception as e:
            logger.error(f"Pythia assess_surprise failed: {e}")
            return {"error": str(e), "surprise_score": 0.0}

    async def resonate(self, query: str) -> Dict[str, Any]:
        """
        Query concept memory for resonant patterns

        Calls: POST /resonate

        Args:
            query: Query text or concept

        Returns:
            Dict with resonant_concepts, coherence_scores, kuramoto_phase
        """
        endpoint = f"{self.base_url}/resonate"

        try:
            if HTTPX_AVAILABLE:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        endpoint, json={"query": query}, timeout=self.timeout
                    )
                    response.raise_for_status()
                    return response.json()
            elif REQUESTS_AVAILABLE:
                response = requests.post(
                    endpoint, json={"query": query}, timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            else:
                raise RuntimeError("No HTTP client available")

        except Exception as e:
            logger.error(f"Pythia resonate failed: {e}")
            return {"error": str(e), "resonant_concepts": []}

    async def store_concept(
        self, name: str, vector: List[float], metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Store concept in Pythia memory

        Calls: POST /store/concept

        Args:
            name: Concept name/identifier
            vector: Concept vector (512-dim or 2048-dim)
            metadata: Optional metadata dict

        Returns:
            Dict with concept_id, stored, attractor_key
        """
        endpoint = f"{self.base_url}/store/concept"

        payload = {"name": name, "vector": vector, "metadata": metadata or {}}

        try:
            if HTTPX_AVAILABLE:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        endpoint, json=payload, timeout=self.timeout
                    )
                    response.raise_for_status()
                    return response.json()
            elif REQUESTS_AVAILABLE:
                response = requests.post(endpoint, json=payload, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            else:
                raise RuntimeError("No HTTP client available")

        except Exception as e:
            logger.error(f"Pythia store_concept failed: {e}")
            return {"error": str(e), "stored": False}

    async def store_attractor(
        self, name: str, state_vector: List[float]
    ) -> Dict[str, Any]:
        """
        Store attractor state in Pythia memory

        Calls: POST /store/attractor

        Args:
            name: Attractor name
            state_vector: State vector (32-dim multivector)

        Returns:
            Dict with attractor_id, stored, kuramoto_phase
        """
        endpoint = f"{self.base_url}/store/attractor"

        payload = {"name": name, "state_vector": state_vector}

        try:
            if HTTPX_AVAILABLE:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        endpoint, json=payload, timeout=self.timeout
                    )
                    response.raise_for_status()
                    return response.json()
            elif REQUESTS_AVAILABLE:
                response = requests.post(endpoint, json=payload, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            else:
                raise RuntimeError("No HTTP client available")

        except Exception as e:
            logger.error(f"Pythia store_attractor failed: {e}")
            return {"error": str(e), "stored": False}

    async def health_check(self) -> Dict[str, Any]:
        """
        Check Pythia service health

        Calls: GET /health

        Returns:
            Dict with status, version, uptime
        """
        endpoint = f"{self.base_url}/health"

        try:
            if HTTPX_AVAILABLE:
                async with httpx.AsyncClient() as client:
                    response = await client.get(endpoint, timeout=self.timeout)
                    response.raise_for_status()
                    return response.json()
            elif REQUESTS_AVAILABLE:
                response = requests.get(endpoint, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            else:
                raise RuntimeError("No HTTP client available")

        except Exception as e:
            logger.error(f"Pythia health check failed: {e}")
            return {"error": str(e), "status": "unhealthy"}


# ============================================================================
# MCP Tool Definitions
# ============================================================================

# Global client instance
_bridge_client: Optional[PythiaBridgeClient] = None


def get_bridge_client() -> PythiaBridgeClient:
    """Get or create the global PythiaBridgeClient instance"""
    global _bridge_client
    if _bridge_client is None:
        _bridge_client = PythiaBridgeClient()
    return _bridge_client


if MCP_AVAILABLE:

    @mcp.tool()
    async def pythia_encode(text: str) -> Dict[str, Any]:
        """
        Encode text or concept into geometric representation using Pythia

        Converts natural language into 512-dim or 2048-dim geometric vectors
        suitable for concept memory storage and similarity matching.

        Args:
            text: Text or concept description to encode

        Returns:
            Dict containing:
            - vector_512: 512-dimensional encoded vector
            - vector_2048: 2048-dimensional encoded vector
            - inference_time_ms: ONNX inference time
            - error: Present if encoding failed
        """
        client = get_bridge_client()
        start_time = time.time()

        result = await client.encode(text)

        # Add timing
        result["encoding_time_ms"] = (time.time() - start_time) * 1000

        logger.info(
            f"🔮 Pythia encoded '{text[:30]}...' in {result.get('encoding_time_ms', 0):.1f}ms"
        )

        return result

    @mcp.tool()
    async def pythia_predict(concept: str) -> Dict[str, Any]:
        """
        Predict concept outcome using Pythia Oracle

        Uses geometric reasoning to predict likely outcomes or associations
        for a given concept.

        Args:
            concept: Concept name or description to predict

        Returns:
            Dict containing:
            - prediction: Predicted outcome or association
            - confidence: Prediction confidence (0-1)
            - geometric_state: Internal geometric state
            - error: Present if prediction failed
        """
        client = get_bridge_client()
        start_time = time.time()

        result = await client.predict_concept(concept)

        # Add timing
        result["prediction_time_ms"] = (time.time() - start_time) * 1000

        logger.info(
            f"🔮 Pythia predicted '{concept[:30]}...' in {result.get('prediction_time_ms', 0):.1f}ms"
        )

        return result

    @mcp.tool()
    async def pythia_surprise(observation: str) -> Dict[str, Any]:
        """
        Assess novelty/surprise of an observation

        Determines how novel or unexpected an observation is compared
        to stored concept memories. High surprise indicates new learning
        opportunity.

        Args:
            observation: Observation or event description

        Returns:
            Dict containing:
            - surprise_score: Novelty score (0-1, higher = more surprising)
            - novelty_detected: Boolean indicating if this is novel
            - curiosity_signal: Strength of curiosity signal to emit
            - similar_concepts: List of similar known concepts
            - error: Present if assessment failed
        """
        client = get_bridge_client()
        start_time = time.time()

        result = await client.assess_surprise(observation)

        # Add timing
        result["assessment_time_ms"] = (time.time() - start_time) * 1000

        surprise_score = result.get("surprise_score", 0.0)
        logger.info(
            f"🔮 Pythia surprise '{observation[:30]}...': {surprise_score:.2f} "
            f"in {result.get('assessment_time_ms', 0):.1f}ms"
        )

        return result

    @mcp.tool()
    async def pythia_resonate(query: str) -> Dict[str, Any]:
        """
        Query concept memory for resonant patterns

        Searches stored concept memories for patterns that resonate with
        the query, returning coherence scores and Kuramoto phase data.

        Args:
            query: Query text or concept

        Returns:
            Dict containing:
            - resonant_concepts: List of matching concepts
            - coherence_scores: Coherence score for each match
            - kuramoto_phase: Phase coherence data
            - max_coherence: Highest coherence score found
            - error: Present if resonance query failed
        """
        client = get_bridge_client()
        start_time = time.time()

        result = await client.resonate(query)

        # Add timing
        result["resonance_time_ms"] = (time.time() - start_time) * 1000

        num_concepts = len(result.get("resonant_concepts", []))
        logger.info(
            f"🔮 Pythia resonate '{query[:30]}...': {num_concepts} concepts "
            f"in {result.get('resonance_time_ms', 0):.1f}ms"
        )

        return result

    @mcp.tool()
    async def pythia_store_concept(
        name: str,
        vector: Optional[List[float]] = None,
        text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Store concept in Pythia memory

        Stores a concept either by providing a pre-computed vector or by
        encoding text first.

        Args:
            name: Concept name/identifier
            vector: Optional pre-computed concept vector (512 or 2048 dim)
            text: Optional text to encode (used if vector not provided)
            metadata: Optional metadata dict

        Returns:
            Dict containing:
            - concept_id: Unique concept identifier
            - stored: Boolean indicating success
            - attractor_key: Redis key for attractor state
            - encoding_time_ms: Time to encode (if text provided)
            - error: Present if storage failed
        """
        client = get_bridge_client()
        start_time = time.time()

        # If text provided but not vector, encode first
        if text and not vector:
            encode_result = await client.encode(text)
            if "error" in encode_result:
                return {"error": f"Encoding failed: {encode_result['error']}"}
            vector = encode_result.get("vector_512") or encode_result.get("vector_2048")

        if not vector:
            return {"error": "Either vector or text must be provided"}

        result = await client.store_concept(name, vector, metadata or {})

        # Add timing
        result["storage_time_ms"] = (time.time() - start_time) * 1000

        logger.info(
            f"🔮 Pythia stored concept '{name}' in {result.get('storage_time_ms', 0):.1f}ms"
        )

        return result

    @mcp.tool()
    async def pythia_health() -> Dict[str, Any]:
        """
        Check Pythia service health

        Returns:
            Dict containing:
            - status: 'healthy' or 'unhealthy'
            - version: Service version
            - uptime: Service uptime
            - response_time_ms: Health check response time
        """
        client = get_bridge_client()
        start_time = time.time()

        result = await client.health_check()

        # Add timing
        result["response_time_ms"] = (time.time() - start_time) * 1000

        status = result.get("status", "unknown")
        logger.info(
            f"🔮 Pythia health check: {status} in {result.get('response_time_ms', 0):.1f}ms"
        )

        return result


# ============================================================================
# Tool Registry Integration
# ============================================================================


def register_with_tool_registry():
    """
    Register Pythia Bridge tools with the ToolRegistry

    This is called automatically when the module is imported by MCP server.
    """
    try:
        from tool_registry import ToolCategory, get_tool_registry, register_tool

        registry = get_tool_registry()

        # Register each tool with metadata
        @register_tool(
            category="geometry",
            description="Encode text or concept into geometric representation using Pythia",
            parameters={
                "text": {
                    "type": "string",
                    "description": "Text or concept to encode",
                    "optional": False,
                }
            },
            returns="Dict with vector_512, vector_2048, inference_time_ms",
        )
        def pythia_encode_registry(text: str) -> Dict[str, Any]:
            return get_bridge_client().encode_sync(text)

        logger.info(
            "✅ Pythia Bridge tools registered with ToolRegistry (category: geometry)"
        )

    except ImportError as e:
        logger.warning(f"Could not register Pythia Bridge with ToolRegistry: {e}")
    except Exception as e:
        logger.error(f"Error registering Pythia Bridge: {e}")


# Auto-register on import
register_with_tool_registry()
