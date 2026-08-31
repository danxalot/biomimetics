"""
V2 Geometry Kernel - Model Engine (Cognitive Scheduler)

Orchestrates the Cognitive Tick with Visual Spike Detection:
...
Architecture:
- GPU Router (:8080) - DeepSeek R1 (always hot)
- CPU VL (:8083) - Qwen3 VL (on spike)
- CPU Guardian (:11436) - Granite Guardian (one-shot)
- Python - SigLIP (change detection)
"""

import os
import time
import logging
import requests
import concurrent.futures
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path

try:
    from .visual_spike import VisualSpikeDetector
except ImportError:
    from visual_spike import VisualSpikeDetector

logger = logging.getLogger(__name__)


@dataclass
class CognitiveTickResult:
    """Result of a single cognitive tick."""

    frame_id: int
    visual_description: str
    visual_spike: bool
    reasoning_output: Optional[str] = None
    safety_verdict: Optional[str] = None

    # Timing
    perception_ms: float = 0.0
    reasoning_ms: float = 0.0
    safety_ms: float = 0.0
    total_ms: float = 0.0

    # Metrics
    similarity: Optional[float] = None


@dataclass
class ServerConfig:
    """llama.cpp server configuration."""

    name: str
    host: str
    port: int
    model: str

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def _parse_satellite_response(data: dict) -> str:
    """
    Unwrap the envelope returned by the MCP satellite and extract the LLM
    completion text.
    """
    import json as _json

    try:
        gateway_response = data

        # 1. Start unwrapping from JSON-RPC
        if isinstance(data, dict) and "result" in data:
            gateway_response = data["result"]

        # 2. If the wrapped response is a string (e.g. double-encoded by Pythia/llama.cpp), unbox it
        if isinstance(gateway_response, str):
            try:
                gateway_response = _json.loads(gateway_response)
            except _json.JSONDecodeError:
                pass  # It's intended to be a raw string

        # 3. Extract from standard MCP Tool Result format if present
        if isinstance(gateway_response, dict) and "content" in gateway_response and isinstance(gateway_response["content"], list):
            try:
                raw = gateway_response["content"][0]["text"]
                parsed = _json.loads(raw)
                if isinstance(parsed, str):
                    parsed = _json.loads(parsed)
                gateway_response = parsed
            except Exception:
                # If it's not JSON, just return the raw text
                return gateway_response["content"][0].get("text", str(gateway_response))

        # 4. Handle nested wrapping (some satellites double-wrap inside 'result')
        if isinstance(gateway_response, dict) and "result" in gateway_response and "choices" not in gateway_response:
            gateway_response = gateway_response["result"]
            
        if isinstance(gateway_response, str):
            # If unwrapped gateway_response is somehow just a string now, return it
            return gateway_response

        # 5. Finally extract the message content from the choices array
        try:
            if isinstance(gateway_response, dict) and "choices" in gateway_response:
                return gateway_response["choices"][0]["message"]["content"]
            return str(gateway_response)
        except (KeyError, IndexError, TypeError):
            return str(gateway_response)

    except Exception as e:
        import traceback
        import logging
        logging.getLogger("model_engine").error(f"Failed parsing satellite response! Raw data dict: {data} \nTraceback: {traceback.format_exc()}")
        raise e


class CognitiveScheduler:
    """
    Orchestrates the V2 Geometry Kernel Cognitive Tick.

    Uses Visual Spike Detection to minimize expensive VL calls.
    Routes requests to appropriate llama.cpp servers.

    Example:
        scheduler = CognitiveScheduler()

        for frame in frames:
            result = scheduler.tick(frame)
            if result.visual_spike:
                print(f"Visual change detected: {result.visual_description}")
    """

    # Server configurations (hosts/models can be overridden with env vars)
    GPU_ROUTER = ServerConfig(
        name="GPU Router",
        host=os.environ.get(
            "GPU_ROUTER_HOST", os.environ.get("LLM_GATEWAY_HOST", "llm_gateway")
        ),
        port=int(
            os.environ.get("GPU_ROUTER_PORT", os.environ.get("LLM_GATEWAY_PORT", 8080))
        ),
        model=os.environ.get("GPU_ROUTER_MODEL", "deepseek-r1-distill-qwen-1.5b"),
    )

    CPU_VL = ServerConfig(
        name="CPU VL",
        host=os.environ.get("CPU_VL_HOST", "llama_cpp"),
        port=int(os.environ.get("CPU_VL_PORT", 8081)),
        model=os.environ.get("CPU_VL_MODEL", "SmolVLM-256M-Instruct-Q8_0.gguf"),
    )

    def __init__(
        self,
        spike_threshold: float = 0.95,
        enable_safety: bool = False,
        timeout: float = 30.0,
    ):
        """
        Initialize the cognitive scheduler.

        Args:
            spike_threshold: Cosine similarity threshold for visual spike
            enable_safety: Whether to run Guardian safety screening
            timeout: Request timeout in seconds
        """
        self.spike_threshold = spike_threshold
        self.enable_safety = enable_safety
        self.timeout = timeout

        # Initialize spike detector
        self.spike_detector = VisualSpikeDetector(threshold=spike_threshold)

        # State
        self.tick_count = 0
        self.last_result: Optional[CognitiveTickResult] = None

        logger.info(
            f"CognitiveScheduler initialized "
            f"(threshold={spike_threshold}, safety={enable_safety})"
        )

    def _check_server(self, server: ServerConfig) -> bool:
        """Check if a server is available."""
        try:
            resp = requests.get(f"{server.base_url}/health", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    def _call_completion(
        self,
        server: ServerConfig,
        prompt: str,
        max_tokens: int = 200,
        system: Optional[str] = None,
    ) -> str:
        """Call a llama.cpp server for completion."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                f"{server.base_url}/v1/chat/completions",
                json={
                    "model": server.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error calling {server.name}: {e}")
            return f"[ERROR: {e}]"

    def _run_perception(self, image) -> tuple[bool, str, float]:
        """
        Run perception phase with spike detection.

        Returns:
            Tuple of (needs_vl, description, elapsed_ms)
        """
        start = time.time()

        needs_vl, cached = self.spike_detector.check_frame(image)

        if not needs_vl and cached:
            # Reuse cached description
            elapsed = (time.time() - start) * 1000
            logger.debug(f"Perception reuse: {elapsed:.1f}ms")
            return False, cached, elapsed

        # Visual spike - need to call VL
        logger.info("Visual spike detected - calling Qwen VL...")

        # For now, use a placeholder since we need to handle image encoding
        # In production, this would send the image to the VL server
        description = self._call_completion(
            self.CPU_VL if self._check_server(self.CPU_VL) else self.GPU_ROUTER,
            "Describe what you see in this image briefly.",
            max_tokens=100,
        )

        # Update cached description
        self.spike_detector.update_description(description)

        elapsed = (time.time() - start) * 1000
        logger.debug(f"Perception VL: {elapsed:.1f}ms")
        return True, description, elapsed

    def _run_reasoning(self, context: str) -> tuple[str, float]:
        """
        Run reasoning phase with DeepSeek R1.

        Returns:
            Tuple of (reasoning_output, elapsed_ms)
        """
        start = time.time()

        output = self._call_completion(
            self.GPU_ROUTER,
            context,
            max_tokens=200,
            system="You are a reasoning assistant. Think step by step.",
        )

        elapsed = (time.time() - start) * 1000
        logger.debug(f"Reasoning: {elapsed:.1f}ms")
        return output, elapsed

    def _run_safety(self, content: str) -> tuple[str, float]:
        """
        Run safety screening with Guardian.

        Returns:
            Tuple of (verdict, elapsed_ms)
        """
        start = time.time()

        if not self.enable_safety:
            return "SKIPPED", 0.0

        verdict = self._call_completion(
            self.GPU_ROUTER,
            f"Is this content safe? Answer Yes or No.\n\nContent: {content[:500]}",
            max_tokens=10,
        )

        elapsed = (time.time() - start) * 1000
        logger.debug(f"Safety: {elapsed:.1f}ms")
        return verdict.strip(), elapsed

    def tick(self, image) -> CognitiveTickResult:
        """
        Execute a single cognitive tick.

        Args:
            image: Image to process (PIL, numpy, or path)

        Returns:
            CognitiveTickResult with all outputs and timing
        """
        self.tick_count += 1
        tick_start = time.time()

        # Phase 1: Perception (with spike detection)
        visual_spike, description, perception_ms = self._run_perception(image)

        # Phase 2: Reasoning (only if we have new visual info or first tick)
        reasoning_output = None
        reasoning_ms = 0.0
        if visual_spike or self.tick_count == 1:
            context = f"Visual observation: {description}\n\nWhat should we do?"
            reasoning_output, reasoning_ms = self._run_reasoning(context)

        # Phase 3: Safety (on demand)
        safety_verdict = None
        safety_ms = 0.0
        if reasoning_output and self.enable_safety:
            safety_verdict, safety_ms = self._run_safety(reasoning_output)

        total_ms = (time.time() - tick_start) * 1000

        result = CognitiveTickResult(
            frame_id=self.tick_count,
            visual_description=description,
            visual_spike=visual_spike,
            reasoning_output=reasoning_output,
            safety_verdict=safety_verdict,
            perception_ms=perception_ms,
            reasoning_ms=reasoning_ms,
            safety_ms=safety_ms,
            total_ms=total_ms,
        )

        self.last_result = result

        logger.info(
            f"Tick {self.tick_count}: spike={visual_spike}, "
            f"perception={perception_ms:.0f}ms, "
            f"reasoning={reasoning_ms:.0f}ms, "
            f"total={total_ms:.0f}ms"
        )

        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        spike_stats = self.spike_detector.get_stats()
        return {
            "ticks": self.tick_count,
            "spike_rate": spike_stats.get("spike_rate", 0.0),
            "reuse_rate": spike_stats.get("reuse_rate", 0.0),
            "threshold": self.spike_threshold,
            "safety_enabled": self.enable_safety,
        }

    def run_reasoning_phase(self, context_text: str, prompt_template: str) -> str:
        """
        Run reasoning phase for RLM document walking.

        Used by recursive_ingestion.py to extract concepts from document chunks.

        Args:
            context_text: The document chunk to analyze
            prompt_template: The prompt with {context} placeholder

        Returns:
            LLM response with extracted concepts as JSON
        """
        # Build the full prompt
        full_prompt = (
            prompt_template.format(context=context_text)
            if "{context}" in prompt_template
            else f"{prompt_template}\n\nContent:\n{context_text}"
        )

        messages = [
            {
                "role": "system",
                "content": "You are a document analyzer. Extract key concepts and return ONLY valid JSON. Do not include thinking process or preamble.",
            },
            {"role": "user", "content": full_prompt},
        ]

        return self._gateway_request(messages, max_tokens=2000, temperature=0.2)

    def _gateway_request(
        self, messages: list, max_tokens: int = 2000, temperature: float = 0.2
    ) -> str:
        """
        Send a request to the LLM Gateway via the Service Mesh.

        Routing Logic:
        - If Local (macOS): Direct HTTP to llm_gateway:8080
        - If Remote (OCI): MCP Tool Call via localhost:8095 (Satellite) -> macOS MCP Server -> Gateway
        """
        NODE_ENV = os.environ.get("ARCA_ENV", "local").lower()

        payload = {
            "model": "deepseek-r1-distill-qwen-1.5b",
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # 1. Local / Brain Node: Direct Access
        if NODE_ENV == "local":
            gateway_url = os.environ.get("LLM_GATEWAY_URL", "http://llm_gateway:8080")
            try:
                resp = requests.post(
                    f"{gateway_url}/v1/chat/completions", json=payload, timeout=600.0
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"Gateway direct call failed: {e}")
                raise

        # 2. OCI Container: Route via MCP Satellite (local bridge network)
        # For OCI containers, use local MCP satellite on bridge network
        elif NODE_ENV == "oci":
            mcp_satellite_url = os.environ.get(
                "MCP_SATELLITE_URL", "http://mcp_satellite:8092/mcp"
            )
            # Use gateway_request tool if available, otherwise generic service_request
            try:
                # payload is a list of messages for /v1/chat/completions compatible gateway
                resp = requests.post(
                    mcp_satellite_url,
                    json={
                        "method": "tools/call",
                        "params": {
                            "name": "gateway_request", 
                            "arguments": {
                                "path": "/v1/chat/completions",
                                "method": "POST",
                                "body": payload
                            }
                        },
                    },
                    timeout=600.0,
                )
                resp.raise_for_status()
                return _parse_satellite_response(resp.json())
            except Exception as e:
                logger.error(f"MCP Satellite (OCI) call failed: {e}")
                raise

        # 3. Remote / Cloud Node: Route via MCP Satellite
        else:
            # We are on a cloud node. Use the local MCP Client Satellite to bridge back to Brain.
            mcp_satellite_url = os.environ.get(
                "MCP_SATELLITE_URL", "http://mcp_satellite:8092/mcp"
            )
            try:
                resp = requests.post(
                    mcp_satellite_url,
                    json={
                        "method": "tools/call",
                        "params": {"name": "gateway_request", "arguments": {
                            "path": "/v1/chat/completions",
                            "method": "POST",
                            "body": payload,
                        }},
                    },
                    timeout=600.0,
                )
                resp.raise_for_status()
                return _parse_satellite_response(resp.json())
            except Exception as e:
                logger.error(f"MCP Satellite call failed: {e}")
                raise


if __name__ == "__main__":
    import sys
    from PIL import Image

    logging.basicConfig(level=logging.INFO)

    scheduler = CognitiveScheduler(
        spike_threshold=0.95,
        enable_safety=False,  # Disable for quick testing
    )

    # Create test images
    img1 = Image.new("RGB", (224, 224), color="red")
    img2 = Image.new("RGB", (224, 224), color="red")  # Same
    img3 = Image.new("RGB", (224, 224), color="blue")  # Different

    print("Testing Cognitive Scheduler...")
    print()

    # Tick 1 - First frame
    result = scheduler.tick(img1)
    print(f"Tick 1: spike={result.visual_spike}, total={result.total_ms:.0f}ms")

    # Tick 2 - Same frame (should reuse)
    result = scheduler.tick(img2)
    print(f"Tick 2: spike={result.visual_spike}, total={result.total_ms:.0f}ms")

    # Tick 3 - Different frame (should spike)
    result = scheduler.tick(img3)
    print(f"Tick 3: spike={result.visual_spike}, total={result.total_ms:.0f}ms")

    print()
    print(f"Stats: {scheduler.get_stats()}")
