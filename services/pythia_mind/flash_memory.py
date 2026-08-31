"""
A-FLASH Sparse HDC Memory

Part of Stage 3: Phenomenological Mind
Sparse Hyperdimensional Computing memory for orthogonal superposition of concepts

Optimization layer (Phase 4 — OCI ARM):
  - Packed binary encoding: 10,000 bits → 1,250 uint8 bytes (64× memory reduction)
  - NEON-accelerated similarity via hdc_ops native (.so) when available on ARM
  - Pure-numpy fallback for all platforms
"""

import ctypes
import ctypes.util
import os
import sys
import numpy as np
from typing import List, Dict, Any, Optional, Set
import logging
import hashlib

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# NEON native optional load — hdc_ops compiled .so
# ---------------------------------------------------------------------------

_hdc_ops = None  # C extension module, None if unavailable

def _try_load_hdc_ops() -> None:
    """Attempt to import the compiled hdc_ops NEON extension."""
    global _hdc_ops
    if _hdc_ops is not None:
        return

    # Search paths: ARCA lib dir on OCI, then sys.path
    candidates = [
        os.environ.get("HDC_OPS_PATH", ""),
        "/home/ubuntu/ARCA/lib",
        "/app/lib",
        os.path.join(os.path.dirname(__file__), "..", "mcp_server", "tools", "hdc_native"),
    ]
    for path in candidates:
        if not path:
            continue
        if path not in sys.path:
            sys.path.insert(0, path)
        try:
            import importlib
            mod = importlib.import_module("hdc_ops_native")
            _hdc_ops = mod
            logger.info(f"A-FLASH: NEON hdc_ops loaded from {path}")
            return
        except ImportError:
            pass

    logger.info("A-FLASH: hdc_ops NEON not available — using numpy fallback")


_try_load_hdc_ops()


# ---------------------------------------------------------------------------
# Packed binary helpers (platform-independent numpy fallback)
# ---------------------------------------------------------------------------

def _pack_binary(float_vec: np.ndarray) -> np.ndarray:
    """Pack 10,000-dim float32 sparse binary → 1,250 uint8 (10,000 bits)."""
    bits = (float_vec > 0).astype(np.uint8)
    # Pad to multiple of 8
    pad = (8 - len(bits) % 8) % 8
    if pad:
        bits = np.pad(bits, (0, pad))
    return np.packbits(bits)


def _hamming_np(a: np.ndarray, b: np.ndarray) -> int:
    """Hamming distance between two packed uint8 arrays (numpy fallback)."""
    return int(np.unpackbits(np.bitwise_xor(a, b)).sum())


def _hamming_similarity(a: np.ndarray, b: np.ndarray, n_bits: int) -> float:
    """Hamming similarity ∈ [0,1] from packed uint8 vectors."""
    if _hdc_ops is not None:
        try:
            dist = _hdc_ops.hamming_distance(a, b)
            return 1.0 - dist / n_bits
        except Exception:
            pass
    dist = _hamming_np(a, b)
    return 1.0 - dist / n_bits





class AFLASHMemory:
    """
    A-FLASH (Adaptive-Fast-Associated-Logical-HDC) Sparse Memory

    Stores 10,000-dim sparse binary arrays representing concepts.
    Allows thousands of concepts to coexist in orthogonal superposition.

    Storage strategy:
      Float32 vectors (concept_vectors):  used for basis projection / superposition
      Packed uint8 vectors (packed_vectors): used for fast Hamming similarity
        — 1,250 bytes per concept vs 80,000 bytes float32 = 64× reduction
    When hdc_ops NEON is available, similarity uses hardware-accelerated popcount.
    """

    def __init__(self, dimension: int = 10000, sparsity: float = 0.01):
        self.dimension = dimension
        self.sparsity = sparsity  # 1% of dimensions are active
        self.active_dims = int(dimension * sparsity)
        self._packed_bytes = (dimension + 7) // 8  # bytes per packed vector

        # Storage for concept vectors
        self.concept_vectors: Dict[str, np.ndarray] = {}

        # Packed binary storage for fast similarity (64× memory reduction)
        self.packed_vectors: Dict[str, np.ndarray] = {}  # concept → uint8[1250]

        # Inverted index for fast lookup
        self.inverted_index: Dict[int, Set[str]] = {}

        # Initialize random basis vectors
        self.basis_vectors = np.random.randn(dimension, 128)  # 128 basis concepts

        logger.info(
            f"A-FLASH Memory initialized: {dimension}-dim sparse arrays "
            f"({'NEON' if _hdc_ops else 'numpy'} similarity)"
        )

    def encode_concept(
        self, concept: str, state_vector: Optional[List[float]] = None
    ) -> np.ndarray:
        """
        Encode a concept into a sparse binary vector

        Args:
            concept: Concept name/identifier
            state_vector: Optional continuous state to encode

        Returns:
            10,000-dim sparse binary vector
        """
        # Create deterministic sparse vector from concept name
        hash_obj = hashlib.md5(concept.encode())
        hash_int = int(hash_obj.hexdigest(), 16)

        # Generate sparse binary vector
        vector = np.zeros(self.dimension, dtype=np.float32)

        # Set active dimensions based on hash
        rng = np.random.RandomState(hash_int % (2**32))
        active_indices = rng.choice(
            self.dimension, size=self.active_dims, replace=False
        )
        vector[active_indices] = 1.0

        # If state vector provided, modulate the encoding
        if state_vector is not None:
            state_array = np.array(state_vector, dtype=np.float32)
            # Project state onto sparse vector
            modulation = np.dot(self.basis_vectors.T, state_array)
            # Apply modulation to active dimensions
            vector[active_indices] *= 1.0 + 0.1 * modulation[: self.active_dims]

        # Normalize to maintain sparsity
        vector = (vector > 0).astype(np.float32)

        # Store concept (float32 for superposition) + packed uint8 (for fast similarity)
        self.concept_vectors[concept] = vector
        self.packed_vectors[concept] = _pack_binary(vector)

        # Update inverted index
        for idx in active_indices:
            if idx not in self.inverted_index:
                self.inverted_index[idx] = set()
            self.inverted_index[idx].add(concept)

        return vector

    def retrieve_concepts(self, query_vector: np.ndarray, top_k: int = 10) -> List[str]:
        """
        Retrieve concepts similar to query vector.

        Uses packed uint8 Hamming similarity when available (NEON or numpy popcount).
        Falls back to sparse cosine similarity if packed vectors unavailable.
        """
        if not self.concept_vectors:
            return []

        # --- Fast path: packed binary Hamming similarity ---
        if self.packed_vectors:
            query_packed = _pack_binary((query_vector > 0).astype(np.float32))
            similarities = [
                (concept, _hamming_similarity(query_packed, pv, self.dimension))
                for concept, pv in self.packed_vectors.items()
            ]
        else:
            # Slow fallback: sparse float cosine
            similarities = [
                (concept, self._sparse_cosine_similarity(query_vector, vector))
                for concept, vector in self.concept_vectors.items()
            ]

        similarities.sort(key=lambda x: x[1], reverse=True)
        return [concept for concept, _ in similarities[:top_k]]

    def _sparse_cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """Compute sparse cosine similarity"""
        intersection = np.sum((v1 > 0) & (v2 > 0))
        norm1 = np.sum(v1 > 0)
        norm2 = np.sum(v2 > 0)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return intersection / np.sqrt(norm1 * norm2)

    def associative_recall(self, concept: str) -> List[str]:
        """
        Retrieve concepts associated with a given concept

        Uses inverted index for fast associative recall
        """
        if concept not in self.concept_vectors:
            return []

        vector = self.concept_vectors[concept]
        active_indices = np.where(vector > 0)[0]

        associated_concepts = set()
        for idx in active_indices:
            if idx in self.inverted_index:
                associated_concepts.update(self.inverted_index[idx])

        # Remove the query concept itself
        associated_concepts.discard(concept)

        return list(associated_concepts)

    def combine_concepts(self, concepts: List[str]) -> np.ndarray:
        """
        Combine multiple concepts via orthogonal superposition

        Args:
            concepts: List of concept names

        Returns:
            Combined sparse vector (logical OR of concepts)
        """
        if not concepts:
            return np.zeros(self.dimension, dtype=np.float32)

        combined = np.zeros(self.dimension, dtype=np.float32)

        for concept in concepts:
            if concept in self.concept_vectors:
                combined = np.maximum(combined, self.concept_vectors[concept])

        return combined

    def concept_state(self, concept: str) -> Optional[Dict[str, Any]]:
        """Get state information for a concept"""
        if concept not in self.concept_vectors:
            return None

        vector = self.concept_vectors[concept]
        active_count = np.sum(vector > 0)

        return {
            "concept": concept,
            "active_dims": int(active_count),
            "sparsity": active_count / self.dimension,
            "associations": self.associative_recall(concept),
        }


# Singleton instance
_flash_memory: Optional[AFLASHMemory] = None


def get_flash_memory() -> AFLASHMemory:
    """Get or create A-FLASH memory singleton"""
    global _flash_memory
    if _flash_memory is None:
        _flash_memory = AFLASHMemory(dimension=10000, sparsity=0.01)
    return _flash_memory


def encode_concept(
    concept: str, state_vector: Optional[List[float]] = None
) -> List[float]:
    """Convenience function to encode a concept"""
    memory = get_flash_memory()
    result = memory.encode_concept(concept, state_vector)
    return result.tolist()


def retrieve_similar_concepts(query_vector: List[float], top_k: int = 10) -> List[str]:
    """Convenience function to retrieve similar concepts"""
    memory = get_flash_memory()
    return memory.retrieve_concepts(np.array(query_vector), top_k)


def associative_recall(concept: str) -> List[str]:
    """Convenience function for associative recall"""
    memory = get_flash_memory()
    return memory.associative_recall(concept)


def combine_concepts(concepts: List[str]) -> List[float]:
    """Convenience function to combine concepts"""
    memory = get_flash_memory()
    result = memory.combine_concepts(concepts)
    return result.tolist()
