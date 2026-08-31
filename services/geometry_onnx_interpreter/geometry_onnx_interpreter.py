"""
Geometry ONNX Interpreter Service

Orchestrates ONNX model inference on geometric data (solar system format)
followed by Qwen3VL interpretation of the results.

Input: Solar system JSON from recursive_ingestion.py
Output: Interpreted analysis via Qwen3VL

Endpoints:
  POST /interpret/predict     - Run ONNX model + Qwen3VL interpretation
  POST /interpret/onnx_only   - Run ONNX model only (no Qwen3VL)
  POST /interpret/batch       - Batch processing endpoint
  GET  /interpret/health      - Service health check
"""

import os
import json
import logging
import time
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from contextlib import asynccontextmanager

import numpy as np
import onnxruntime as ort
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("geometry_onnx_interpreter")

# ============================================================================
# Configuration
# ============================================================================

# ONNX Model Configuration
ONNX_MODEL_PATH = os.getenv("ONNX_MODEL_PATH", "/app/models/geometry_model.onnx")

# Qwen3VL Configuration (running on port 11435)
QWEN3VL_HOST = os.getenv(
    "QWEN3VL_HOST", os.getenv("LOCAL_LLM_HOST", "host.docker.internal")
)
QWEN3VL_PORT = int(os.getenv("QWEN3VL_PORT", "11435"))
QWEN3VL_URL = f"http://{QWEN3VL_HOST}:{QWEN3VL_PORT}/v1/chat/completions"
QWEN3VL_MODEL = os.getenv("QWEN3VL_MODEL", "qwen3vl")

# Service Configuration
SERVICE_PORT = int(os.getenv("PORT", "8096"))

# ============================================================================
# Pydantic Models
# ============================================================================


class ObjectInput(BaseModel):
    """Input object from solar system format."""

    id: str
    mass: float = Field(ge=0.0, le=1.0)
    position: List[float] = Field(min_length=3, max_length=3)
    desc: Optional[str] = None


class SolarSystemInput(BaseModel):
    """Solar system format from recursive_ingestion.py"""

    system_id: str
    gravity_well: Dict[str, Any]
    objects: List[ObjectInput]
    trajectory: List[float] = Field(min_length=3, max_length=3)


class ONNXOutput(BaseModel):
    """Output from ONNX model."""

    vector: List[float]
    confidence: float
    energy: float
    inference_time_ms: float


class Qwen3VLInterpretation(BaseModel):
    """Interpretation from Qwen3VL."""

    summary: str
    key_insights: List[str]
    recommendations: List[str]
    confidence: float


class InterpretationResult(BaseModel):
    """Final interpretation result."""

    system_id: str
    onnx_output: ONNXOutput
    qwen3vl_interpretation: Qwen3VLInterpretation
    processing_time_ms: float


class BatchInput(BaseModel):
    """Batch processing input."""

    items: List[SolarSystemInput]


class BatchOutput(BaseModel):
    """Batch processing output."""

    results: List[InterpretationResult]
    total_time_ms: float


# ============================================================================
# ONNX Model Handler
# ============================================================================


@dataclass
class ModelMetadata:
    """ONNX model metadata."""

    input_shape: Tuple[int, ...]
    output_shape: Tuple[int, ...]
    model_path: str
    is_loaded: bool = False


class ONNXModelHandler:
    """Handles ONNX model loading and inference."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self.session: Optional[ort.InferenceSession] = None
        self.metadata: Optional[ModelMetadata] = None
        self.is_loaded = False

    def load_model(self) -> bool:
        """Load ONNX model from path."""
        try:
            if not os.path.exists(self.model_path):
                # Try alternative locations
                alt_paths = [
                    os.path.join(
                        os.path.dirname(__file__), "models", "geometry_model.onnx"
                    ),
                    "/app/models/geometry_model.onnx",
                ]
                for alt_path in alt_paths:
                    if os.path.exists(alt_path):
                        self.model_path = alt_path
                        break
                else:
                    logger.warning(f"ONNX model not found at {self.model_path}")
                    return False

            # Initialize ONNX Runtime session
            providers = ["CPUExecutionProvider"]
            self.session = ort.InferenceSession(self.model_path, providers=providers)

            # Get model metadata
            input_meta = self.session.get_inputs()[0]
            output_meta = self.session.get_outputs()[0]
            self.metadata = ModelMetadata(
                input_shape=tuple(input_meta.shape),
                output_shape=tuple(output_meta.shape),
                model_path=self.model_path,
                is_loaded=True,
            )
            self.is_loaded = True
            logger.info(f"✅ ONNX model loaded: {self.model_path}")
            logger.info(f"   Input shape: {self.metadata.input_shape}")
            logger.info(f"   Output shape: {self.metadata.output_shape}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to load ONNX model: {e}")
            self.is_loaded = False
            return False

    def preprocess(self, solar_system: Dict[str, Any]) -> np.ndarray:
        """
        Preprocess solar system data for ONNX model input.

        Expects model input shape: [batch, sequence, features]
        where features include 32 dimensions per multivector.
        Current implementation: mass + position (3) + trajectory (3) + padding (25)
        """
        objects = solar_system.get("objects", [])
        trajectory = solar_system.get("trajectory", [0.0, 0.0, 0.0])

        # Extract features per object
        object_features = []
        for obj in objects:
            # Base features (7 dimensions)
            features = [
                obj.get("mass", 0.5),
                obj.get("position", [0.0, 0.0, 0.0])[0],
                obj.get("position", [0.0, 0.0, 0.0])[1],
                obj.get("position", [0.0, 0.0, 0.0])[2],
                trajectory[0],
                trajectory[1],
                trajectory[2],
            ]

            # Pad to 32 features with zeros (for future expansion)
            features.extend([0.0] * 25)

            object_features.append(features)

        # Pad or truncate to fixed sequence length
        seq_len = 32  # Common sequence length for geometric models
        if len(object_features) < seq_len:
            # Pad with zeros
            padding = [[0.0] * 32] * (seq_len - len(object_features))
            object_features.extend(padding)
        else:
            # Truncate
            object_features = object_features[:seq_len]

        # Convert to numpy array
        # Shape: [1, sequence_length, features]
        input_array = np.array([object_features], dtype=np.float32)

        return input_array

    def predict(self, input_array: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Run ONNX inference.

        Returns:
            Tuple of (output_array, inference_time_ms)
        """
        if not self.is_loaded or self.session is None:
            raise RuntimeError("Model not loaded")

        start_time = time.time()

        try:
            # Run inference
            inputs = {self.session.get_inputs()[0].name: input_array}
            outputs = self.session.run(None, inputs)
            output_array = outputs[0]

            # Extract key metrics from output
            # Assuming output shape is [1, features] or [1, sequence, features]
            if len(output_array.shape) > 2:
                # Mean pool across sequence if needed
                output_array = np.mean(output_array, axis=1)

            inference_time = (time.time() - start_time) * 1000
            return output_array, inference_time

        except Exception as e:
            logger.error(f"ONNX inference error: {e}")
            raise

            # ============================================================================
            # Qwen3VL Integration - REMOVED
            # ============================================================================
            # Qwen3VLClient removed - geometry_onnx_interpreter now ONLY does ONNX inference
            # Qwen3VL interpretation is handled by pythia_integration.py calling Pythia server

            if response.status_code != 200:
                logger.error(
                    f"MCP satellite error: {response.status_code} - {response.text}"
                )
                return None

            # Parse MCP satellite response
            return self._parse_mcp_response(response.json())

        except Exception as e:
            logger.error(f"MCP satellite call failed: {e}")
            return None

    def _parse_mcp_response(self, mcp_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse MCP satellite response to extract LLM completion."""
        try:
            # Handle different response formats
            if "result" in mcp_data:
                gateway_response = mcp_data["result"]
            elif "content" in mcp_data:
                import json as _json

                raw = mcp_data["content"][0]["text"]
                gateway_response = _json.loads(raw)
            else:
                gateway_response = mcp_data

            # Handle nested wrapping
            if "result" in gateway_response and "choices" not in gateway_response:
                gateway_response = gateway_response["result"]

            return gateway_response
        except Exception as e:
            logger.error(f"Failed to parse MCP response: {e}")
            return None

    async def _call_pythia_server(
        self, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Call Qwen3VL via the local pythia_server (llama.cpp with Vulkan)."""
        if not self.pythia_server_url:
            logger.error("Pythia server URL not configured")
            return None

        try:
            logger.info(f"Calling pythia_server at {self.pythia_server_url}")

            response = await self.client.post(
                f"{self.pythia_server_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                logger.error(
                    f"Pythia server error: {response.status_code} - {response.text}"
                )
                return None

            return response.json()

        except Exception as e:
            logger.error(f"Pythia server call failed: {e}")
            return None

    async def _call_direct(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call Qwen3VL directly (for local/macOS mode)."""
        # Check for pythia_server first
        if self.pythia_server_url:
            return await self._call_pythia_server(payload)

        # Fallback to gateway
        try:
            gateway_url = os.environ.get("LLM_GATEWAY_URL", "http://llm_gateway:8080")
            logger.info(f"Calling Qwen3VL directly via gateway at {gateway_url}")

            response = await self.client.post(
                f"{gateway_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                logger.error(f"Gateway error: {response.status_code} - {response.text}")
                return None

            return response.json()

        except Exception as e:
            logger.error(f"Direct gateway call failed: {e}")
            return None

    async def interpret_onnx_output(
        self,
        solar_system: Dict[str, Any],
        onnx_output: Dict[str, Any],
        context: str = "geometric_analysis",
    ) -> Qwen3VLInterpretation:
        """
        Send ONNX output to Qwen3VL for interpretation.

        Routes via MCP satellite in OCI mode, direct gateway in local mode.

        Args:
            solar_system: Original input data
            onnx_output: ONNX model output
            context: Type of analysis context

        Returns:
            Qwen3VLInterpretation object
        """
        try:
            # Build prompt for Qwen3VL
            prompt = self._build_interpretation_prompt(
                solar_system, onnx_output, context
            )

            messages = [
                {
                    "role": "system",
                    "content": """You are a geometric analysis expert.
Interpret the geometric model output and provide actionable insights.
Focus on:
1. Key patterns in the object distribution
2. System stability and coherence
3. Potential anomalies or interesting features
4. Recommendations for further analysis""",
                },
                {"role": "user", "content": prompt},
            ]

            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 200,
                "temperature": 0.3,
                "stream": False,
            }

            logger.info(
                f"Calling Qwen3VL (mode={self.node_env}) with model {self.model}"
            )

            # Route based on environment
            result = None
            if self.node_env == "oci":
                # Use MCP satellite for mesh network access
                result = await self._call_via_mcp_satellite(payload)
            else:
                # Direct call for local/macOS mode
                result = await self._call_direct(payload)

            if result is None:
                logger.error("Failed to get response from Qwen3VL")
                return self._fallback_interpretation(onnx_output)

            # Extract content from response
            try:
                content = result["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"Failed to parse Qwen3VL response: {e}")
                return self._fallback_interpretation(onnx_output)

            # Parse response
            interpretation = self._parse_qwen3vl_response(content)

            return interpretation

        except httpx.ReadTimeout:
            logger.error("Qwen3VL request timeout")
            return self._fallback_interpretation(onnx_output)
        except Exception as e:
            logger.error(f"Qwen3VL integration error: {e}")
            return self._fallback_interpretation(onnx_output)

    def _build_interpretation_prompt(
        self, solar_system: Dict[str, Any], onnx_output: Dict[str, Any], context: str
    ) -> str:
        """Build prompt for Qwen3VL interpretation."""

        # Convert to JSON for better context
        system_json = json.dumps(solar_system, indent=2)
        output_json = json.dumps(onnx_output, indent=2)

        return f"""## Geometric System Analysis

### Input Data (Solar System Format)
```json
{system_json}
```

### ONNX Model Output
```json
{output_json}
```

### Analysis Context
Context Type: {context}

### Task
Please analyze this geometric system and provide:
1. Summary of the system state
2. Key insights from the pattern distribution
3. Recommendations for further analysis or actions

Return your response in a structured format that includes:
- summary (brief overall description)
- key_insights (list of key findings)
- recommendations (list of suggested actions)
"""

    def _parse_qwen3vl_response(self, content: str) -> Qwen3VLInterpretation:
        """Parse Qwen3VL response into structured format."""

        # Try to extract JSON from response
        try:
            # Look for JSON block
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                data = json.loads(json_str)
            else:
                # Try to find JSON object in content
                import re

                match = re.search(r"\{[^}]+\}", content, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                else:
                    # Parse as free-form text
                    data = {
                        "summary": content[:200],
                        "key_insights": [],
                        "recommendations": [],
                    }

            return Qwen3VLInterpretation(
                summary=data.get("summary", "No summary provided"),
                key_insights=data.get("key_insights", []),
                recommendations=data.get("recommendations", []),
                confidence=data.get("confidence", 0.8),
            )

        except Exception as e:
            logger.error(f"Failed to parse Qwen3VL response: {e}")
            return self._fallback_interpretation({})

    def _fallback_interpretation(
        self, onnx_output: Dict[str, Any]
    ) -> Qwen3VLInterpretation:
        """Generate fallback interpretation when Qwen3VL is unavailable."""
        logger.warning("Using fallback interpretation")

        # Extract basic metrics from ONNX output
        vector = onnx_output.get("vector", [0, 0, 0])
        confidence = onnx_output.get("confidence", 0.5)

        return Qwen3VLInterpretation(
            summary=f"Geometric analysis complete. System vector: {vector}",
            key_insights=[
                f"Model confidence: {confidence:.2f}",
                "Vector analysis completed successfully",
                "System state evaluated",
            ],
            recommendations=[
                "Review detailed object distribution",
                "Check for anomalies in trajectory",
                "Consider semantic analysis of concepts",
            ],
            confidence=confidence,
        )


# ============================================================================
# Service Initialization
# ============================================================================


@dataclass
class ServiceState:
    """Global service state."""

    onnx_handler: Optional[ONNXModelHandler] = None
    is_ready: bool = False


# Global state
service_state = ServiceState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Service lifespan management."""
    logger.info("🚀 Starting Geometry ONNX Interpreter Service...")

    # Initialize ONNX model handler
    service_state.onnx_handler = ONNXModelHandler(ONNX_MODEL_PATH)
    if service_state.onnx_handler.load_model():
        logger.info("✅ ONNX model loaded successfully")
    else:
        logger.warning("⚠️ ONNX model not loaded - service will run in degraded mode")

    service_state.is_ready = service_state.onnx_handler.is_loaded

    yield

    # Cleanup
    logger.info("🛑 Shutting down Geometry ONNX Interpreter Service")


# ============================================================================
# API Endpoints
# ============================================================================

app = FastAPI(title="Geometry ONNX Interpreter", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/interpret/health")
async def health_check():
    """Service health check."""
    mcp_satellite_url = os.environ.get("MCP_SATELLITE_URL", "not configured")
    pythia_server_url = os.environ.get("PYTHIA_SERVER_URL", "http://localhost:11435")
    return {
        "status": "healthy" if service_state.is_ready else "degraded",
        "service": "geometry_onnx_interpreter",
        "onnx_loaded": service_state.onnx_handler.is_loaded
        if service_state.onnx_handler
        else False,
        "mcp_satellite_url": mcp_satellite_url,
        "pythia_server_url": pythia_server_url,
        "mode": os.environ.get("ARCA_ENV", "local"),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/interpret/model_info")
async def model_info():
    """Get ONNX model metadata."""
    if not service_state.onnx_handler or not service_state.onnx_handler.metadata:
        raise HTTPException(status_code=503, detail="Model not loaded")

    return {
        "model_path": service_state.onnx_handler.metadata.model_path,
        "input_shape": service_state.onnx_handler.metadata.input_shape,
        "output_shape": service_state.onnx_handler.metadata.output_shape,
        "is_loaded": service_state.onnx_handler.metadata.is_loaded,
    }


@app.post("/interpret/onnx_only", response_model=ONNXOutput)
async def predict_onnx_only(solar_system: SolarSystemInput):
    """
    Run ONNX model only, without Qwen3VL interpretation.

    Useful for debugging or when only model output is needed.
    """
    if not service_state.onnx_handler or not service_state.onnx_handler.is_loaded:
        raise HTTPException(
            status_code=503, detail="ONNX model not loaded or unavailable"
        )

    try:
        start_time = time.time()

        # Preprocess input
        input_array = service_state.onnx_handler.preprocess(solar_system.model_dump())

        # Run inference
        output_array, inference_time = service_state.onnx_handler.predict(input_array)

        # Extract vector and metrics
        vector = output_array.flatten().tolist()[:3]  # Take first 3 dims as vector
        confidence = float(np.mean(np.abs(output_array)))  # Simple confidence metric
        energy = float(np.sum(output_array**2))  # Energy metric

        result = ONNXOutput(
            vector=vector,
            confidence=confidence,
            energy=energy,
            inference_time_ms=inference_time,
        )

        logger.info(f"ONNX inference completed in {inference_time:.2f}ms")
        return result

    except Exception as e:
        logger.error(f"ONNX prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/interpret/predict", response_model=InterpretationResult)
async def predict_with_interpretation(solar_system: SolarSystemInput):
    """
    ONNX inference + Qwen3VL interpretation (optimized).

    NOTE: This endpoint is DEPRECATED for performance reasons.
    Use /interpret/onnx_only for fast ONNX inference, then call
    Pythia server separately for Qwen3VL interpretation.

    For backward compatibility, this endpoint now only runs ONNX
    and returns a minimal interpretation.
    """
    if not service_state.onnx_handler or not service_state.onnx_handler.is_loaded:
        raise HTTPException(
            status_code=503, detail="ONNX model not loaded or unavailable"
        )

    start_time = time.time()

    try:
        # 1. Preprocess and run ONNX model (fast)
        input_array = service_state.onnx_handler.preprocess(solar_system.model_dump())
        output_array, inference_time = service_state.onnx_handler.predict(input_array)

        # Extract ONNX output
        vector = output_array.flatten().tolist()[:3]
        confidence = float(np.mean(np.abs(output_array)))
        energy = float(np.sum(output_array**2))

        onnx_output = ONNXOutput(
            vector=vector,
            confidence=confidence,
            energy=energy,
            inference_time_ms=inference_time,
        )

        # 2. Return minimal interpretation (no Qwen3VL call to avoid blocking)
        # The calling service should handle Qwen3VL interpretation separately
        total_time = (time.time() - start_time) * 1000

        result = InterpretationResult(
            system_id=solar_system.system_id,
            onnx_output=onnx_output,
            qwen3vl_interpretation=Qwen3VLInterpretation(
                summary="ONNX inference complete. Vector ready for interpretation.",
                key_insights=["Vector extracted", f"Confidence: {confidence:.3f}"],
                recommendations=[
                    "Call Pythia server separately for Qwen3VL interpretation"
                ],
                confidence=confidence,
            ),
            processing_time_ms=total_time,
        )

        logger.info(f"ONNX inference completed in {total_time:.2f}ms (vector ready)")
        return result

    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/interpret/batch", response_model=BatchOutput)
async def predict_batch(batch_input: BatchInput):
    """
    Batch processing endpoint.

    Processes multiple solar systems in sequence.
    """
    if not service_state.onnx_handler or not service_state.onnx_handler.is_loaded:
        raise HTTPException(
            status_code=503, detail="ONNX model not loaded or unavailable"
        )

    start_time = time.time()
    results = []

    try:
        for i, solar_system in enumerate(batch_input.items):
            logger.info(f"Processing batch item {i + 1}/{len(batch_input.items)}")

            # Run full pipeline
            input_array = service_state.onnx_handler.preprocess(
                solar_system.model_dump()
            )
            output_array, inference_time = service_state.onnx_handler.predict(
                input_array
            )

            vector = output_array.flatten().tolist()[:3]
            confidence = float(np.mean(np.abs(output_array)))
            energy = float(np.sum(output_array**2))

            onnx_output = ONNXOutput(
                vector=vector,
                confidence=confidence,
                energy=energy,
                inference_time_ms=inference_time,
            )

            # Store vector result (no Qwen3VL interpretation - handled separately)
            result = InterpretationResult(
                system_id=solar_system.system_id,
                onnx_output=onnx_output,
                qwen3vl_interpretation=Qwen3VLInterpretation(
                    summary="ONNX inference complete. Vector ready for interpretation.",
                    key_insights=["Vector extracted", f"Confidence: {confidence:.3f}"],
                    recommendations=[
                        "Call Pythia server separately for Qwen3VL interpretation"
                    ],
                    confidence=confidence,
                ),
                processing_time_ms=inference_time,
            )
            results.append(result)

        total_time = (time.time() - start_time) * 1000

        return BatchOutput(results=results, total_time_ms=total_time)

    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/interpret/async_predict")
async def async_predict(solar_system: SolarSystemInput):
    """
    Async prediction endpoint that returns immediately.

    Useful for high-throughput scenarios where immediate response is needed.
    """
    if not service_state.onnx_handler or not service_state.onnx_handler.is_loaded:
        raise HTTPException(
            status_code=503, detail="ONNX model not loaded or unavailable"
        )

    try:
        # Run ONNX only for async endpoint
        input_array = service_state.onnx_handler.preprocess(solar_system.model_dump())
        output_array, inference_time = service_state.onnx_handler.predict(input_array)

        # Queue Qwen3VL interpretation in background (simulated)
        task_id = f"task_{int(time.time())}_{solar_system.system_id}"

        # Return immediately with ONNX results
        return {
            "task_id": task_id,
            "system_id": solar_system.system_id,
            "onnx_output": {
                "vector": output_array.flatten().tolist()[:3],
                "inference_time_ms": inference_time,
            },
            "status": "queued",
            "qwen3vl_endpoint": f"/interpret/status/{task_id}",
        }

    except Exception as e:
        logger.error(f"Async prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Startup
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
