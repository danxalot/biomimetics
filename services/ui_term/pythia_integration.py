"""
Pythia Server Integration for LangGraph Agent

Provides functions to call the Pythia server (llama.cpp with Qwen3VL)
and the geometry_onnx_interpreter for geometric analysis.
"""

import os
import json
import asyncio
import httpx
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging
import uuid
import tempfile

logger = logging.getLogger(__name__)

# Directory for storing ONNX vector outputs
VECTOR_CACHE_DIR = os.path.join(tempfile.gettempdir(), "arca_vector_cache")


def get_vector_cache_path(system_id: str) -> str:
    """Get the file path for storing a vector by system_id."""
    os.makedirs(VECTOR_CACHE_DIR, exist_ok=True)
    return os.path.join(VECTOR_CACHE_DIR, f"vector_{system_id}.json")


def store_vector(system_id: str, vector_data: Dict[str, Any]) -> str:
    """Store vector data to cache file."""
    cache_path = get_vector_cache_path(system_id)
    with open(cache_path, "w") as f:
        json.dump(vector_data, f)
    return cache_path


def load_vector(system_id: str) -> Optional[Dict[str, Any]]:
    """Load vector data from cache file."""
    cache_path = get_vector_cache_path(system_id)
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)
    return None


@dataclass
class PythiaConfig:
    """Configuration for Pythia server"""

    server_url: str = "http://localhost:11435"
    model_name: str = "Qwen3VL-2B-Instruct-Q8_0.gguf"
    onnx_interpreter_url: str = "http://localhost:8096"
    timeout: float = 120.0
    agent_name: str = "pythia"  # Agent identifier for LangGraph


class PythiaClient:
    """Client for Pythia server and ONNX interpreter"""

    def __init__(self, config: Optional[PythiaConfig] = None):
        self.config = config or PythiaConfig()
        self.client = httpx.AsyncClient(timeout=self.config.timeout)
        logger.info(f"PythiaClient initialized: {self.config.server_url}")

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> Optional[Dict[str, Any]]:
        """Call Pythia server for chat completion"""
        model = model or self.config.model_name

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        try:
            url = f"{self.config.server_url}/v1/chat/completions"
            logger.info(f"Calling Pythia server: {url}")

            response = await self.client.post(url, json=payload)

            if response.status_code != 200:
                logger.error(
                    f"Pythia server error: {response.status_code} - {response.text}"
                )
                return None

            return response.json()

        except Exception as e:
            logger.error(f"Pythia server call failed: {e}")
            return None

    async def run_onnx_inference(
        self, solar_system_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Run ONNX inference and get full Pythia interpretation.

        Uses the /interpret/pythia_vector endpoint on geometry_onnx_interpreter
        which handles the full pipeline: ONNX → 2048-dim → interpret → llama.cpp:11435.
        No separate port/instance needed — the vector is translated to an instruct
        prompt and forwarded to the same LLM server.
        """
        try:
            # First get the raw vector via ONNX
            url = f"{self.config.onnx_interpreter_url}/interpret/onnx_only"
            logger.info(f"Running ONNX inference: {url}")

            response = await self.client.post(
                url,
                json=solar_system_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                logger.error(
                    f"ONNX inference error: {response.status_code} - {response.text}"
                )
                return None

            result = response.json()
            system_id = solar_system_data.get("system_id", str(uuid.uuid4()))
            vector_2048 = result.get("vector_2048", [])

            # If we got a 2048-dim vector, use the interpreter to get Pythia's response
            if len(vector_2048) == 2048:
                bridge_url = f"{self.config.onnx_interpreter_url}/interpret/pythia_vector"
                bridge_resp = await self.client.post(
                    bridge_url,
                    json={
                        "vector_2048": vector_2048,
                        "system_id": system_id,
                        "context": solar_system_data.get("context", ""),
                    },
                )
                if bridge_resp.status_code == 200:
                    bridge_result = bridge_resp.json()
                    vector_data = {
                        "system_id": system_id,
                        "vector": vector_2048,
                        "pythia_response": bridge_result.get("response"),
                        "energy": bridge_result.get("vector_energy", 0),
                        "inference_time_ms": result.get("inference_time_ms", 0),
                        "total_time_ms": bridge_result.get("processing_time_ms", 0),
                    }
                    store_vector(system_id, vector_data)
                    logger.info(f"Pythia response received for {system_id}")
                    return vector_data

            # Fallback: store raw vector without interpretation
            vector_data = {
                "system_id": system_id,
                "vector": vector_2048,
                "confidence": result.get("confidence", 0),
                "energy": result.get("energy", 0),
                "inference_time_ms": result.get("inference_time_ms", 0),
            }
            store_vector(system_id, vector_data)

            logger.info(
                f"Stored vector for system {system_id} (inference time: {vector_data['inference_time_ms']:.2f}ms)"
            )
            return vector_data

        except Exception as e:
            logger.error(f"ONNX inference call failed: {e}")
            return None

    async def interpret_with_prompt(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 500,
    ) -> Optional[str]:
        """Interpret text using Pythia server"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        result = await self.chat_completion(messages, max_tokens=max_tokens)

        if result and "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]

        return None


# Singleton instance
_pythia_client: Optional[PythiaClient] = None


def get_pythia_client() -> PythiaClient:
    """Get or create Pythia client singleton"""
    global _pythia_client
    if _pythia_client is None:
        config = PythiaConfig(
            server_url=os.getenv("PYTHIA_SERVER_URL", "http://localhost:11435"),
            onnx_interpreter_url=os.getenv(
                "ONNX_INTERPRETER_URL", "http://localhost:8096"
            ),
        )
        _pythia_client = PythiaClient(config)
    return _pythia_client


# Example usage in LangGraph agent
async def pythia_geometric_analysis(
    session_id: str,
    user_input: str,
    geometric_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Main integration function for LangGraph agent
    Performs geometric analysis using Pythia server + ONNX interpreter

    Optimized: Separates ONNX inference from Qwen3VL interpretation
    to avoid blocking the pipeline.
    """
    client = get_pythia_client()

    # Step 1: Run ONNX inference (fast, ~8ms) and store vector
    # This is now a separate, fast call that doesn't block on Qwen3VL
    vector_data = None
    if geometric_data:
        vector_data = await client.run_onnx_inference(geometric_data)
        if not vector_data:
            logger.warning("ONNX inference failed, continuing without vector")

    # Step 2: Interpret user input with Pythia (Qwen3VL)
    # Include vector data in the prompt for context
    system_prompt = """You are a geometric analysis assistant.
Analyze the user's input and extract key geometric concepts.
Focus on: spatial relationships, patterns, structures, and anomalies."""

    # Build comprehensive prompt with vector if available
    if vector_data:
        prompt_content = f"""User Input: {user_input}

Geometric Vector Analysis:
- Vector: {vector_data.get("vector", [])}
- Confidence: {vector_data.get("confidence", 0):.3f}
- Energy: {vector_data.get("energy", 0):.3f}
- Inference Time: {vector_data.get("inference_time_ms", 0):.2f}ms

Please analyze this geometric system based on the vector data."""
    else:
        prompt_content = user_input

    interpretation = await client.interpret_with_prompt(
        prompt=prompt_content,
        system_prompt=system_prompt,
        max_tokens=300,
    )

    if not interpretation:
        logger.error("Failed to interpret user input")
        return {"error": "Interpretation failed"}

    # Step 3: Generate final response
    # The vector is already included in the context from Step 2
    final_prompt = f"""Previous Analysis: {interpretation}

Based on the geometric vector data provided, 
give a comprehensive technical analysis with recommendations."""

    final_response = await client.interpret_with_prompt(
        prompt=final_prompt,
        system_prompt="You are a geometric analysis expert. Provide clear, actionable insights with specific recommendations.",
        max_tokens=500,
    )

    return {
        "session_id": session_id,
        "interpretation": interpretation,
        "vector_data": vector_data,
        "final_response": final_response,
        "status": "success" if final_response else "partial",
    }
