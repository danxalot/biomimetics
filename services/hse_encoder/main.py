"""
Hyper-Spatial Embedding (HSE) Encoder Service

Converts raw telemetry, events, and semantic data into 10000-dimensional
binary hypervectors using NumPy-based hyperdimensional computing. This enables:

1. Thermometer encoding for continuous metrics (CPU, RAM, latency)
2. Basis vectors for categorical data (service names, event types)
3. Semantic folding for log text
4. Bundling for global state vectors

The global state vector V_State is published to Redis for:
- Velocity detection: Δ = V_t ⊕ V_{t-1}
- Anomaly detection via similarity to failure mode vectors
- Geometry Kernel integration for proprioceptive state

Architecture inspired by:
- Kanerva's sparse distributed memory
- Hyperdimensional computing (Pentti Kanerva)
- Holographic reduced representations (Plate)
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

import numpy as np
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

HSE_DIMENSIONS = int(os.environ.get("HSE_DIMENSIONS", "10000"))
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
STATE_VECTOR_KEY = "arca:hse:state_vector"
STATE_HISTORY_KEY = "arca:hse:state_history"
FAILURE_MODES_KEY = "arca:hse:failure_modes"

# =============================================================================
# Hypervector Operations (NumPy-based HDC)
# =============================================================================

class HypervectorOps:
    """
    Hyperdimensional computing operations using NumPy.
    Optimized for consistent behavior across platforms.
    Uses bipolar {-1, +1} representation for HDC operations.
    """
    
    def __init__(self, dimensions: int = 10000):
        self.d = dimensions
        self._basis_cache: Dict[str, np.ndarray] = {}
    
    def random_hv(self) -> np.ndarray:
        """Generate a random bipolar hypervector."""
        return np.random.choice([-1, 1], size=self.d)
    
    def get_basis(self, name: str) -> np.ndarray:
        """Get or create a deterministic basis vector for a named concept."""
        if name not in self._basis_cache:
            seed = hash(name) % (2**32)
            rng = np.random.RandomState(seed)
            self._basis_cache[name] = rng.choice([-1, 1], size=self.d)
        return self._basis_cache[name]
    
    def bind(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Bind two hypervectors (element-wise multiplication for bipolar)."""
        return a * b
    
    def bundle(self, vectors: List[np.ndarray]) -> np.ndarray:
        """Bundle hypervectors using element-wise sum and threshold."""
        if not vectors:
            return np.zeros(self.d, dtype=np.float32)
        
        stacked = np.vstack(vectors)
        bundled = np.sum(stacked, axis=0)
        
        # Threshold to bipolar: positive -> +1, negative -> -1, zero -> random
        bundled = np.sign(bundled)
        zeros = (bundled == 0)
        if np.any(zeros):
            bundled[zeros] = np.random.choice([-1, 1], size=np.sum(zeros))
        
        return bundled.astype(np.float32)
    
    def permute(self, hv: np.ndarray, n: int = 1) -> np.ndarray:
        """Circular shift (permutation) for sequence encoding."""
        return np.roll(hv, shift=n)
    
    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between hypervectors."""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        # Avoid division by zero
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return dot_product / (norm_a * norm_b)
    
    def thermometer_encode(self, value: float, min_val: float = 0.0, 
                           max_val: float = 100.0, levels: int = 100) -> np.ndarray:
        """
        Thermometer encoding for continuous values.
        Returns a bundled vector representing the value level.
        """
        normalized = max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))
        active_levels = int(normalized * levels)
        
        level_vectors = [self.get_basis(f"level_{i}") for i in range(active_levels)]
        
        if level_vectors:
            return self.bundle(level_vectors)
        else:
            return np.zeros(self.d, dtype=np.float32)
    
    def to_numpy(self, hv: np.ndarray) -> np.ndarray:
        """Convert hypervector to numpy for Redis storage.
        
        Convert bipolar {-1, +1} to binary {0, 1} for compact storage.
        """
        return ((hv > 0).astype(np.int8))
    
    def from_numpy(self, arr: np.ndarray) -> np.ndarray:
        """Convert numpy array back to bipolar hypervector.
        
        Convert binary {0, 1} to bipolar {-1, +1}
        """
        return (arr.astype(np.float32) * 2) - 1


# =============================================================================
# Data Models
# =============================================================================

class MetricEvent(BaseModel):
    """Telemetry metric event."""
    type: str = Field(default="metric", description="Event type: metric, log, span")
    service: str = Field(..., description="Service name (redis, postgres, agent, etc.)")
    metric_name: Optional[str] = Field(None, description="Metric name (cpu, memory, latency)")
    value: Optional[float] = Field(None, description="Metric value")
    text: Optional[str] = Field(None, description="Log text for semantic encoding")
    labels: Dict[str, str] = Field(default_factory=dict, description="Additional labels")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")


class EncodeRequest(BaseModel):
    """Request to encode a single event."""
    type: str = "metric"
    service: str
    metric_name: Optional[str] = None
    value: Optional[float] = None
    text: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)


class EncodeBatchRequest(BaseModel):
    """Request to encode multiple events."""
    events: List[EncodeRequest]


class EncodeResponse(BaseModel):
    """Response containing encoded hypervector."""
    state_vector: List[int]  # Binary {0, 1} representation for JSON serialization
    dimensions: int
    encoding_method: str = "numpy_hdc"


# =============================================================================
# HSE Encoder Service
# =============================================================================

app = FastAPI(title="ARCA HSE Encoder (NumPy-based Hyperdimensional Computing)")

# Global HDC operations instance
hdc_ops = HypervectorOps(dimensions=HSE_DIMENSIONS)


@app.on_event("startup")
async def startup_event():
    logger.info(f"🧠 HSE Encoder Starting | Dimensions: {HSE_DIMENSIONS}")
    logger.info("🔢 Using NumPy-based Hyperdimensional Computing")


@app.get("/health")
async def health():
    return {
        "status": "active", 
        "role": "hse_encoder",
        "dimensions": HSE_DIMENSIONS,
        "hdc_implementation": "numpy"
    }


@app.post("/encode", response_model=EncodeResponse)
async def encode_event(request: EncodeRequest):
    """Encode a single metric event into a hypervector."""
    try:
        # Initialize zero vector
        hv = np.zeros(HSE_DIMENSIONS, dtype=np.float32)
        
        # Encode service as basis vector
        service_hv = hdc_ops.get_basis(request.service)
        hv = hdc_ops.bundle([hv, service_hv])
        
        # Encode metric name if provided
        if request.metric_name:
            metric_hv = hdc_ops.get_basis(f"metric_{request.metric_name}")
            hv = hdc_ops.bundle([hv, metric_hv])
        
        # Encode value using thermometer encoding if provided
        if request.value is not None:
            # Normalize value ranges based on metric type
            if request.metric_name in ["cpu", "memory"]:
                value_hv = hdc_ops.thermometer_encode(
                    request.value, min_val=0.0, max_val=100.0, levels=50
                )
            elif request.metric_name == "latency":
                value_hv = hdc_ops.thermometer_encode(
                    request.value, min_val=0.0, max_val=1000.0, levels=50
                )
            else:
                # Generic scaling
                value_hv = hdc_ops.thermometer_encode(
                    request.value, min_val=0.0, max_val=10.0, levels=50
                )
            hv = hdc_ops.bundle([hv, value_hv])
        
        # Encode text if provided (simple approach: hash to basis)
        if request.text:
            text_seed = hash(request.text) % (2**32)
            text_hv = hdc_ops.get_basis(f"text_{text_seed}")
            hv = hdc_ops.bundle([hv, text_hv])
        
        # Encode labels
        for label_key, label_value in request.labels.items():
            label_hv = hdc_ops.get_basis(f"label_{label_key}_{label_value}")
            hv = hdc_ops.bundle([hv, label_hv])
        
        # Convert to binary storage format
        binary_vector = hdc_ops.to_numpy(hv)
        
        return EncodeResponse(
            state_vector=binary_vector.tolist(),
            dimensions=len(binary_vector),
            encoding_method="numpy_hdc"
        )
        
    except Exception as e:
        logger.error(f"Encoding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/encode_batch", response_model=List[EncodeResponse])
async def encode_batch(request: EncodeBatchRequest):
    """Encode multiple events."""
    responses = []
    for event in request.events:
        response = await encode_event(event)
        responses.append(response)
    return responses


@app.post("/similarity")
async def compute_similarity(vector1: List[int], vector2: List[int]):
    """Compute similarity between two binary vectors."""
    try:
        # Convert binary to bipolar
        hv1 = np.array(vector1, dtype=np.float32) * 2 - 1
        hv2 = np.array(vector2, dtype=np.float32) * 2 - 1
        
        similarity = hdc_ops.similarity(hv1, hv2)
        return {"similarity": similarity}
    except Exception as e:
        logger.error(f"Similarity computation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8095)
