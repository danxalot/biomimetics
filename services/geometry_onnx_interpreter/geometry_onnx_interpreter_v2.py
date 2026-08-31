"""
Geometry ONNX Interpreter - Version 2
Implements Full Stage 1 Pipeline + Unified Oracle Prediction

Stage 1 (encoding):
  Produces 2048-dim vectors, stores in Qdrant, truncates to 512-dim, caches in Dragonfly

Oracle layer (prediction / concept memory) — merged from pythia_oracle:
  /predict/state      — HDC 10k → numpy CliffordHDCBridge → CGA [B,1,32] → ONNX → rotors + energy
  /predict/anomaly    — energy divergence anomaly check
  /store/concept      — persist ConceptMonad JSON on disk + in-memory numpy index
  /resonate           — holographic resonance query (numpy cosine similarity, no FAISS)
  /bridge/store_geometric — GATr geometric vector → concept monad mapping

One container, one ORT session — saves ~2.3GB RAM vs running pythia_oracle separately.
"""

import os
import json
import math
import time
import uuid
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging

# Setup logging (must come before optional imports so logger is available in except blocks)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import new pipeline components (optional — service degrades gracefully without qdrant/redis)
try:
    from qdrant_integration import store_vector_2048, retrieve_similar_vectors
    _QDRANT_AVAILABLE = True
except ImportError:
    _QDRANT_AVAILABLE = False
    def store_vector_2048(vector, metadata): return None  # type: ignore
    def retrieve_similar_vectors(vector, limit=5): return []  # type: ignore
    logger.warning("qdrant_integration unavailable — vector storage disabled")

try:
    from dimension_truncation import truncate_vector_2048_to_512
    _TRUNCATION_AVAILABLE = True
except ImportError:
    _TRUNCATION_AVAILABLE = False
    def truncate_vector_2048_to_512(v): return v[:512] if len(v) >= 512 else v + [0.0] * (512 - len(v))  # type: ignore

try:
    from dragonfly_cache import cache_vector_512, retrieve_cached_vector
    _DRAGONFLY_AVAILABLE = True
except ImportError:
    _DRAGONFLY_AVAILABLE = False
    def cache_vector_512(vector, key, metadata=None): return None  # type: ignore
    def retrieve_cached_vector(key): return None  # type: ignore
    logger.warning("dragonfly_cache unavailable — vector caching disabled")

# Configuration
ONNX_MODEL_PATH = os.getenv(
    "ONNX_MODEL_PATH",
    "/Users/danexall/Documents/VS Code Projects/ARCA/models/pythia_c2h_5000_int8.onnx",
)


# Pydantic models
class SolarSystemInput(BaseModel):
    system_id: str
    gravity_well: Dict[str, Any]
    objects: List[Dict[str, Any]]
    trajectory: List[float]


class VectorOutput(BaseModel):
    system_id: str
    vector_2048: List[float]
    vector_512: List[float]
    qdrant_id: Optional[str] = None
    dragonfly_key: Optional[str] = None
    inference_time_ms: float
    storage_time_ms: float


class PipelineResult(BaseModel):
    system_id: str
    vector_2048: List[float]
    vector_512: List[float]
    qdrant_id: Optional[str]
    dragonfly_key: Optional[str]
    similar_vectors: Optional[List[Dict[str, Any]]]
    processing_time_ms: float


# FastAPI app
app = FastAPI(title="Geometry ONNX Interpreter v2", version="2.0.0")


# Global state for ONNX model
class ONNXModelHandler:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.session = None
        self.is_loaded = False

    def load_model(self) -> bool:
        """Load ONNX model"""
        try:
            import onnxruntime as ort

            # Load model
            self.session = ort.InferenceSession(
                self.model_path,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            self.is_loaded = True
            logger.info(f"✅ ONNX model loaded: {self.model_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to load ONNX model: {e}")
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
        """Run ONNX inference"""
        if not self.is_loaded or self.session is None:
            raise ValueError("Model not loaded")

        start_time = time.time()

        # Run inference
        outputs = self.session.run(
            None, {self.session.get_inputs()[0].name: input_array}
        )
        output_array = outputs[0]

        inference_time = (time.time() - start_time) * 1000

        return output_array, inference_time


# Initialize model handler
onnx_handler = ONNXModelHandler(ONNX_MODEL_PATH)


@app.on_event("startup")
async def startup_event():
    """Load ONNX model on startup"""
    logger.info("🚀 Starting Geometry ONNX Interpreter v2...")
    onnx_handler.load_model()


@app.get("/health")
@app.get("/interpret/health")  # alias for built-in image HEALTHCHECK
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "geometry_onnx_interpreter_v2",
        "model_loaded": onnx_handler.is_loaded,
    }


@app.post("/interpret/full_pipeline", response_model=PipelineResult)
async def full_pipeline(solar_system: SolarSystemInput):
    """
    Complete Stage 1 Pipeline:
    1. Run ONNX inference (2048-dim vector)
    2. Store in Qdrant
    3. Truncate to 512-dim
    4. Cache in Dragonfly
    5. Find similar vectors
    """
    start_time = time.time()

    try:
        # Step 1: ONNX inference
        input_array = onnx_handler.preprocess(solar_system.dict())
        output_array, inference_time = onnx_handler.predict(input_array)

        # Step 2: Extract vector from ONNX output
        # ONNX output shape: [batch, sequence, 32] = 1024 dims for 32x32 sequence
        vector = output_array.flatten().tolist()

        # Pad to 2048 dimensions if needed
        if len(vector) < 2048:
            vector.extend([0.0] * (2048 - len(vector)))
        elif len(vector) > 2048:
            vector = vector[:2048]

        vector_2048 = vector

        # Step 3: Store in Qdrant
        qdrant_start = time.time()
        metadata = {
            "system_id": solar_system.system_id,
            "objects_count": len(solar_system.objects),
            "timestamp": time.time(),
        }
        qdrant_id = store_vector_2048(vector_2048, metadata)
        qdrant_time = (time.time() - qdrant_start) * 1000

        # Step 4: Truncate to 512-dim
        vector_512 = truncate_vector_2048_to_512(vector_2048)

        # Step 5: Cache in Dragonfly
        dragonfly_start = time.time()
        dragonfly_key = f"{solar_system.system_id}_512"
        cache_vector_512(vector_512, dragonfly_key, metadata)
        dragonfly_time = (time.time() - dragonfly_start) * 1000

        # Step 6: Find similar vectors
        similar_start = time.time()
        similar_vectors = retrieve_similar_vectors(vector_2048, limit=5)
        similar_time = (time.time() - similar_start) * 1000

        total_time = (time.time() - start_time) * 1000

        logger.info(
            f"Pipeline complete: {total_time:.2f}ms "
            f"(inference: {inference_time:.2f}ms, "
            f"qdrant: {qdrant_time:.2f}ms, "
            f"dragonfly: {dragonfly_time:.2f}ms, "
            f"similar: {similar_time:.2f}ms)"
        )

        return PipelineResult(
            system_id=solar_system.system_id,
            vector_2048=vector_2048,
            vector_512=vector_512,
            qdrant_id=qdrant_id,
            dragonfly_key=dragonfly_key,
            similar_vectors=similar_vectors,
            processing_time_ms=total_time,
        )

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/interpret/onnx_only", response_model=VectorOutput)
async def onnx_only(solar_system: SolarSystemInput):
    """Run ONNX inference only (fastest)"""
    start_time = time.time()

    try:
        input_array = onnx_handler.preprocess(solar_system.dict())
        output_array, inference_time = onnx_handler.predict(input_array)

        vector_2048 = output_array.flatten().tolist()[:2048]

        total_time = (time.time() - start_time) * 1000

        return VectorOutput(
            system_id=solar_system.system_id,
            vector_2048=vector_2048,
            vector_512=[],  # Not computed in onnx_only mode
            inference_time_ms=inference_time,
            storage_time_ms=0,
        )

    except Exception as e:
        logger.error(f"ONNX-only error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vectors/{system_id}")
async def get_vectors(system_id: str):
    """Retrieve stored vectors for a system"""
    # Try Dragonfly first (fastest)
    dragonfly_key = f"{system_id}_512"
    cached = retrieve_cached_vector(dragonfly_key)

    if cached:
        return {
            "source": "dragonfly_cache",
            "system_id": system_id,
            "vector_512": cached["vector"],
            "metadata": cached.get("metadata", {}),
        }

    # Fallback to Qdrant
    # Note: Would need to query Qdrant by metadata
    return {"error": "Vector not found in cache"}


# ═══════════════════════════════════════════════════════════════════════════════
# PYTHIA VECTOR → HUMAN-READABLE RESPONSE
# ═══════════════════════════════════════════════════════════════════════════════
# When a user interacts with Pythia via the LLM, Pythia's response is a
# 2048-dim vector. This endpoint translates that vector into structured
# natural language — the interpreted text IS Pythia's reply to the user.


class PythiaVectorInput(BaseModel):
    vector_2048: List[float]
    context: Optional[str] = None
    system_id: Optional[str] = None


def interpret_vector_to_response(vector: List[float], context: Optional[str] = None) -> str:
    """
    Translate a 2048-dim Pythia output vector into Pythia's natural-language response.

    This IS the response to the user — not a prompt for another LLM.
    The vector encodes Pythia's geometric understanding; this function
    reads that encoding and renders it as human-readable insight.
    """
    arr = np.array(vector, dtype=np.float32)

    # Statistical landscape
    nonzero_mask = arr != 0.0
    active_dims = int(nonzero_mask.sum())
    energy = float(np.linalg.norm(arr))
    top_k = 8
    top_indices = np.argsort(np.abs(arr))[-top_k:][::-1]
    top_values = [(int(i), round(float(arr[i]), 4)) for i in top_indices]

    # Quadrant analysis (4 × 512 blocks matching Matryoshka structure)
    quadrants = [arr[i * 512:(i + 1) * 512] for i in range(4)]
    quadrant_energies = [round(float(np.linalg.norm(q)), 4) for q in quadrants]

    # Dominant quadrant indicates primary semantic axis
    dominant_q = int(np.argmax(quadrant_energies))
    q_labels = ["spatial-geometric", "relational-structural", "temporal-dynamic", "abstract-conceptual"]

    # Sparsity and distribution
    sparsity = 1.0 - (active_dims / 2048.0)
    energy_distribution = [round(e / (energy + 1e-8), 3) for e in quadrant_energies]

    # Build Pythia's response
    parts = [
        f"**Geometric State** (energy: {energy:.3f}, sparsity: {sparsity:.1%})",
        f"Primary axis: **{q_labels[dominant_q]}** ({energy_distribution[dominant_q]:.0%} of total energy)",
        f"Distribution: spatial={energy_distribution[0]:.0%} | relational={energy_distribution[1]:.0%} | temporal={energy_distribution[2]:.0%} | abstract={energy_distribution[3]:.0%}",
        f"Active dimensions: {active_dims}/2048",
        f"Peak activations: {top_values}",
    ]

    if context:
        parts.append(f"Context: {context}")

    return "\n".join(parts)


@app.post("/interpret/pythia_vector")
async def interpret_pythia_vector(input_data: PythiaVectorInput):
    """
    Translate Pythia's 2048-dim response vector into human-readable text.

    This is Pythia's reply to the user — the vector is interpreted and
    returned directly. It is NOT forwarded to another LLM.
    """
    start_time = time.time()

    if len(input_data.vector_2048) != 2048:
        raise HTTPException(
            status_code=400,
            detail=f"Expected 2048-dim vector, got {len(input_data.vector_2048)}"
        )

    system_id = input_data.system_id or f"pythia_{int(time.time())}"
    metadata = {"system_id": system_id, "source": "pythia", "timestamp": time.time()}

    # Store in Qdrant and cache truncated 512 to Dragonfly
    qdrant_id = None
    try:
        qdrant_id = store_vector_2048(input_data.vector_2048, metadata)
        vector_512 = truncate_vector_2048_to_512(input_data.vector_2048)
        cache_vector_512(vector_512, f"{system_id}_512", metadata)
    except Exception as e:
        logger.warning(f"Storage step failed (non-fatal): {e}")
        vector_512 = truncate_vector_2048_to_512(input_data.vector_2048)

    # Find similar past states for richer context
    similar_context = ""
    try:
        similar = retrieve_similar_vectors(input_data.vector_2048, limit=3)
        if similar:
            similar_context = f"Similar past states: {len(similar)} (closest score: {similar[0].get('score', 'N/A')})"
    except Exception:
        pass

    # Interpret the vector — this IS Pythia's response
    full_context = input_data.context or ""
    if similar_context:
        full_context = f"{full_context}\n{similar_context}".strip()

    response_text = interpret_vector_to_response(input_data.vector_2048, context=full_context)

    total_time = (time.time() - start_time) * 1000

    return {
        "system_id": system_id,
        "response": response_text,
        "qdrant_id": qdrant_id,
        "vector_energy": float(np.linalg.norm(np.array(input_data.vector_2048))),
        "processing_time_ms": total_time,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NUMPY CLIFFORD HDC BRIDGE — pythia_oracle ported, no PyTorch required
# ═══════════════════════════════════════════════════════════════════════════════

class NumpyCliffordHDCBridge:
    """
    Pure-numpy equivalent of CliffordHDCBridge from pythia_oracle/lib/noumenal_engine.py.

    Pipeline: HDC [B, 10000] → JL projection [B, 64] → 3D projection [B, 3]
              → conformal_lift → [B, 32] Cl(4,1) multivectors

    Both projection matrices are fixed Johnson-Lindenstrauss matrices:
      - hdc_proj: seed=42,  shape [10000, 64], scale 1/sqrt(64)
      - to_3d:    seed=99,  shape [64, 3],     scale 1/sqrt(3)
      These match the torch buffer initialization in the original class.
    """

    _instance: Optional["NumpyCliffordHDCBridge"] = None

    @classmethod
    def get(cls) -> "NumpyCliffordHDCBridge":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, hdc_dim: int = 10000):
        rng_a = np.random.RandomState(42)
        rng_b = np.random.RandomState(99)
        self.hdc_proj = rng_a.randn(hdc_dim, 64).astype(np.float32) / math.sqrt(64)
        self.proj_3d  = rng_b.randn(64, 3).astype(np.float32) / math.sqrt(3)

    @staticmethod
    def _conformal_lift(points: np.ndarray) -> np.ndarray:
        """Lift R³ → Cl(4,1) null vectors — matches noumenal_engine.conformal_lift()."""
        B = points.shape[0]
        mv = np.zeros((B, 32), dtype=np.float32)
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        x_sq = x**2 + y**2 + z**2
        mv[:, 1] = x
        mv[:, 2] = y
        mv[:, 3] = z
        mv[:, 4] = 0.5 - 0.5 * x_sq
        mv[:, 5] = 0.5 + 0.5 * x_sq
        return mv

    def hdc_to_cga(self, hdc_vector: np.ndarray) -> np.ndarray:
        """HDC [B, 10000] → Cl(4,1) [B, 32]."""
        if hdc_vector.ndim == 1:
            hdc_vector = hdc_vector[np.newaxis, :]
        compressed = hdc_vector @ self.hdc_proj           # [B, 64]
        points_3d  = np.tanh(compressed @ self.proj_3d) * 5.0  # [B, 3], bounded [-5,5]
        return self._conformal_lift(points_3d)            # [B, 32]

    @staticmethod
    def normalize_rotor(r: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(r, axis=-1, keepdims=True).clip(min=1e-8)
        return r / norm


# ═══════════════════════════════════════════════════════════════════════════════
# CONCEPT MEMORY — pythia_oracle/app/memory.py ported, no FAISS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConceptMonad:
    concept_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Unknown"
    lineage: List[str] = field(default_factory=list)
    hv_signature: Optional[List[float]] = None
    hv_velocity: Optional[List[float]] = None
    phase: float = 0.0
    natural_frequency: float = 1.0
    energy_potential: float = 1.0
    uncertainty: float = 0.0
    created_at: float = field(default_factory=time.time)
    source_document: str = ""
    content: str = ""

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items()}

    @staticmethod
    def from_dict(data: Dict) -> "ConceptMonad":
        return ConceptMonad(**{k: v for k, v in data.items()
                                if k in ConceptMonad.__dataclass_fields__})


class ConceptMemory:
    """
    In-memory numpy cosine similarity index for ConceptMonads.
    Replaces faiss.IndexFlatIP — brute-force L2-normalised inner product.
    Fast enough for <10k concepts; no native ARM FAISS required.
    """

    def __init__(self, storage_path: str = "/app/concepts", dimension: int = 10000):
        self.storage_path = storage_path
        self.dimension = dimension
        os.makedirs(storage_path, exist_ok=True)
        self.monads: Dict[str, ConceptMonad] = {}
        self._vectors: Optional[np.ndarray] = None     # [N, D] float32 L2-normalised
        self._concept_ids: List[str] = []
        self._dirty = False

    def _rebuild_index(self):
        if not self._concept_ids:
            self._vectors = None
            return
        rows = []
        valid_ids = []
        for cid in self._concept_ids:
            m = self.monads.get(cid)
            if m and m.hv_signature:
                v = np.array(m.hv_signature, dtype=np.float32)
                norm = np.linalg.norm(v)
                rows.append(v / norm if norm > 0 else v)
                valid_ids.append(cid)
        self._concept_ids = valid_ids
        self._vectors = np.stack(rows) if rows else None
        self._dirty = False

    def initialize(self):
        """Load all persisted JSON concepts from disk and rebuild index."""
        count = 0
        for fname in os.listdir(self.storage_path):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.storage_path, fname)) as f:
                    m = ConceptMonad.from_dict(json.load(f))
                    self.monads[m.concept_id] = m
                    if m.hv_signature:
                        self._concept_ids.append(m.concept_id)
                        count += 1
            except Exception as e:
                logger.warning(f"Skipping {fname}: {e}")
        self._rebuild_index()
        logger.info(f"ConceptMemory: {count} concepts loaded from {self.storage_path}")

    def store_concept(self, monad: ConceptMonad):
        self.monads[monad.concept_id] = monad
        if monad.hv_signature and monad.concept_id not in self._concept_ids:
            self._concept_ids.append(monad.concept_id)
            self._dirty = True
        path = os.path.join(self.storage_path, f"{monad.concept_id}.json")
        with open(path, "w") as f:
            json.dump(monad.to_dict(), f, indent=2)

    def resonate(
        self, context_hv: List[float], threshold: float = 0.5, limit: int = 10
    ) -> List[ConceptMonad]:
        if not self.monads:
            return []
        if self._dirty or self._vectors is None:
            self._rebuild_index()
        if self._vectors is None:
            return []
        query = np.array(context_hv, dtype=np.float32)
        norm = np.linalg.norm(query)
        if norm > 0:
            query /= norm
        scores = self._vectors @ query          # cosine similarity
        order = np.argsort(-scores)
        results = []
        for idx in order[:limit]:
            if float(scores[idx]) >= threshold:
                results.append(self.monads[self._concept_ids[idx]])
        return results


# Singleton concept memory
_concept_memory: Optional[ConceptMemory] = None
CONCEPT_STORAGE_PATH = os.getenv("CONCEPT_STORAGE_PATH", "/app/concepts")


def get_concept_memory() -> ConceptMemory:
    global _concept_memory
    if _concept_memory is None:
        _concept_memory = ConceptMemory(storage_path=CONCEPT_STORAGE_PATH)
    return _concept_memory


# ═══════════════════════════════════════════════════════════════════════════════
# ORACLE ENDPOINTS — /predict/* and /store/* (merged from pythia_oracle)
# ═══════════════════════════════════════════════════════════════════════════════

class StateRequest(BaseModel):
    hdc_vector: List[float]          # 10000-dim HDC input
    context: Optional[str] = None
    entropy_threshold: float = 0.75


class PredictionResponse(BaseModel):
    predicted_rotor: List[float]     # 32-dim Cl(4,1) rotor
    hamiltonian: float               # Energy scalar
    hopfield_energy: Optional[float] = None
    is_anomaly: bool
    inference_time_ms: float


class AnomalyRequest(BaseModel):
    prediction: Dict[str, Any]
    actual: Dict[str, Any]
    threshold: float = 0.75


class ConceptRequest(BaseModel):
    concept_id: str
    name: str
    source_document: str = ""
    content: str = ""
    hv_signature: Optional[List[float]] = None
    hv_velocity: Optional[List[float]] = None
    energy_potential: float = 1.0
    uncertainty: float = 0.0
    phase: float = 0.0


class ResonanceRequest(BaseModel):
    context_hv: List[float]
    threshold: float = 0.5
    limit: int = 10


class GeometricConceptRequest(BaseModel):
    vector: List[float]
    semantic_label: str
    energy_level: float = 0.0


@app.on_event("startup")
async def _load_concept_memory():
    """Load persisted concepts into memory index on startup."""
    mem = get_concept_memory()
    mem.initialize()
    logger.info("Oracle concept memory ready.")


@app.post("/predict/state", response_model=PredictionResponse)
async def predict_state(req: StateRequest):
    """
    Predict next geometric state from an HDC vector.

    Pipeline: HDC [10000] → numpy CliffordHDCBridge → CGA [1,1,32]
              → ONNX session (same as encoding) → predicted_rotor + energy

    This is pythia_oracle's /predict endpoint, ported to ONNX+numpy.
    """
    if not onnx_handler.is_loaded or onnx_handler.session is None:
        raise HTTPException(status_code=503, detail="ONNX model not loaded")

    if len(req.hdc_vector) != 10000:
        raise HTTPException(
            status_code=400,
            detail=f"Expected 10000-dim HDC vector, got {len(req.hdc_vector)}"
        )

    t0 = time.time()

    # 1. HDC → CGA via numpy bridge (no torch required)
    hdc_np = np.array(req.hdc_vector, dtype=np.float32)[np.newaxis, :]  # [1, 10000]
    bridge = NumpyCliffordHDCBridge.get()
    cga_mv = bridge.hdc_to_cga(hdc_np)          # [1, 32]

    # The model was exported with fixed batch*seq=32 (Reshape node constraint).
    # Pad to T=32 with zeros so internal attention works; take last timestep output.
    _SEQ_LEN = 32
    single_step = cga_mv[:, np.newaxis, :]       # [1, 1, 32]
    ort_input = np.zeros((1, _SEQ_LEN, 32), dtype=np.float32)
    ort_input[:, -1:, :] = single_step           # place CGA vector at last position

    # 2. ONNX inference
    input_name = onnx_handler.session.get_inputs()[0].name
    try:
        ort_outputs = onnx_handler.session.run(None, {input_name: ort_input})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ONNX inference failed: {e}")

    # 3. Parse outputs
    # Output 0: predicted_rotors [B, T, 32] — take last timestep
    rotors_raw = ort_outputs[0][0, -1, :]       # [32]
    predicted_rotor = NumpyCliffordHDCBridge.normalize_rotor(rotors_raw).tolist()

    # Output 1 (if present): hamiltonian [B, T] or scalar
    hamiltonian: float = 0.0
    if len(ort_outputs) > 1:
        h = ort_outputs[1]
        hamiltonian = float(h.flat[0]) if hasattr(h, "flat") else float(h[0, -1])

    # Output 2 (if present): hopfield_energy scalar
    hopfield_energy: Optional[float] = None
    if len(ort_outputs) > 2:
        hopfield_energy = float(ort_outputs[2].flat[0])

    is_anomaly = abs(hamiltonian) > req.entropy_threshold
    if is_anomaly:
        logger.warning(f"Pythia anomaly detected — hamiltonian={hamiltonian:.4f}")

    inference_ms = (time.time() - t0) * 1000

    return PredictionResponse(
        predicted_rotor=predicted_rotor,
        hamiltonian=hamiltonian,
        hopfield_energy=hopfield_energy,
        is_anomaly=is_anomaly,
        inference_time_ms=inference_ms,
    )


@app.post("/predict/anomaly")
async def predict_anomaly(req: AnomalyRequest):
    """Energy-based anomaly detection — ported from pythia_oracle /assess_surprise."""
    pred_entropy = req.prediction.get("entropy", req.prediction.get("hamiltonian", 0.0))
    actual_entropy = req.actual.get("entropy", req.actual.get("hamiltonian", 0.0))
    divergence = abs(float(pred_entropy) - float(actual_entropy))
    is_anomaly = divergence > req.threshold
    return {"is_anomaly": is_anomaly, "divergence": divergence, "threshold": req.threshold}


@app.post("/store/concept")
async def store_concept(req: ConceptRequest):
    """Store a ConceptMonad — ported from pythia_oracle /store/concept."""
    monad = ConceptMonad(
        concept_id=req.concept_id,
        name=req.name,
        source_document=req.source_document,
        content=req.content,
        hv_signature=req.hv_signature,
        hv_velocity=req.hv_velocity,
        energy_potential=req.energy_potential,
        uncertainty=req.uncertainty,
        phase=req.phase,
    )
    try:
        get_concept_memory().store_concept(monad)
        return {"status": "stored", "concept_id": monad.concept_id}
    except Exception as e:
        logger.error(f"store_concept error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/resonate")
async def resonate(req: ResonanceRequest):
    """Holographic resonance query — ported from pythia_oracle /resonate."""
    try:
        results = get_concept_memory().resonate(req.context_hv, req.threshold, req.limit)
        return {"results": [m.to_dict() for m in results]}
    except Exception as e:
        logger.error(f"resonate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/bridge/store_geometric")
async def store_geometric_concept(req: GeometricConceptRequest):
    """
    GATr geometric vector → ConceptMonad mapping.
    Ported from pythia_oracle /bridge/store_geometric.
    The geometric vector is projected into 10k HDC space via the numpy bridge (inverse path).
    """
    bridge = NumpyCliffordHDCBridge.get()
    # Treat geometric vector as a truncated CGA multivector; project back to HDC via JL transpose
    geo_np = np.array(req.vector, dtype=np.float32)
    # Pad/truncate to 32-dim (CGA multivector size)
    if len(geo_np) < 32:
        geo_np = np.pad(geo_np, (0, 32 - len(geo_np)))
    else:
        geo_np = geo_np[:32]
    # Approximate inverse: CGA [32] → 3D [3] via pseudo-inverse of conformal_lift
    # Use the known embedding: dimensions 1,2,3 are x,y,z
    points_3d = geo_np[[1, 2, 3]]
    points_3d = np.clip(points_3d, -5.0, 5.0)
    # Expand to 10k HDC via transpose projection: 3→64→10000 (pseudo-inverse)
    v64 = points_3d @ bridge.proj_3d.T                # [64]
    hdc_vec = v64 @ bridge.hdc_proj.T                  # [10000]
    # Binarise to sparse HDC
    hdc_binary = np.sign(hdc_vec).tolist()

    concept_id = str(uuid.uuid4())
    monad = ConceptMonad(
        concept_id=concept_id,
        name=req.semantic_label,
        hv_signature=hdc_binary,
        energy_potential=req.energy_level,
        content=f"geometric_bridge:{req.semantic_label}",
    )
    try:
        get_concept_memory().store_concept(monad)
        return {"status": "stored", "concept_id": concept_id, "mode": "geometric_bridge"}
    except Exception as e:
        logger.error(f"store_geometric error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8096)

