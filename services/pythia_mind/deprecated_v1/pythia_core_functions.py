"""
Pythia Core Functions: Conformal Lift, Bridge, and Hopfield

These functions are loaded into Pythia's isolated databases and used for inference
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import logging
import pickle

logger = logging.getLogger(__name__)

# ============================================================================
# CONFORMAL LIFT FUNCTION (512-dim → 32-dim Cl(4,1))
# ============================================================================


def conformal_lift(
    vector_512: List[float], params: Optional[Dict] = None
) -> List[float]:
    """
    Project 512-dim semantic vector into 32-dim Cl(4,1) conformal geometric algebra space

    Args:
        vector_512: 512-dim semantic embedding
        params: Conformal lift parameters (projection matrix, basis vectors)

    Returns:
        32-dim multivector in Cl(4,1) space
    """
    if params is None:
        raise ValueError("Conformal lift parameters must be provided. Missing B1 artifacts.")

    # Convert to array
    vector_array = np.array(vector_512, dtype=np.float32)

    # Validate dimension
    if len(vector_array) != 512:
        raise ValueError(f"Expected 512-dim vector, got {len(vector_array)}")

    # Normalize input
    mean = params["normalization"]["mean"]
    std = params["normalization"]["std"]
    vector_array = (vector_array - mean) / (std + 1e-8)

    # Project to 32-dim
    projection = params["projection_matrix"]
    multivector_32 = vector_array @ projection

    # Apply CGA structure (reshape to interpret as geometric components)
    # 32-dim: scalar (1) + vector (5) + bivector (10) + ... + pseudoscalar (1)
    # Simplified: just ensure geometric consistency
    multivector_32 = multivector_32 / np.linalg.norm(multivector_32)

    return multivector_32.tolist()


def inverse_conformal_lift(
    multivector_32: List[float], params: Optional[Dict] = None
) -> List[float]:
    """
    Inverse conformal lift: 32-dim multivector → 512-dim semantic vector

    Args:
        multivector_32: 32-dim multivector in Cl(4,1)
        params: Conformal lift parameters

    Returns:
        512-dim semantic embedding (approximate)
    """
    if params is None:
        raise ValueError("Conformal lift parameters must be provided for inverse lift.")

    multivector_array = np.array(multivector_32, dtype=np.float32)

    # Use pseudo-inverse for inverse projection
    if "inverse_matrix" in params:
        vector_512 = multivector_array @ params["inverse_matrix"]
    else:
        # Compute pseudo-inverse
        proj = params["projection_matrix"]
        proj_pinv = np.linalg.pinv(proj)
        vector_512 = multivector_array @ proj_pinv

    return vector_512.tolist()


# ============================================================================
# CYCLE-CONSISTENT BRIDGE FUNCTION (10,000-dim HDC ↔ 2048-dim Dense)
# ============================================================================


class CycleConsistentBridge:
    """
    Bridge between 10,000-dim sparse HDC and 2048-dim dense language space
    """

    def __init__(self, hdc_dim: int = 10000, dense_dim: int = 2048):
        self.dense_dim = dense_dim

        # Weights must be loaded via load_weights() or initialize_pythia_functions()
        self.encoder_weights = None
        self.decoder_weights = None

        logger.info(f"CycleConsistentBridge initialized: {hdc_dim} ↔ {dense_dim}")

    def hdc_to_dense(self, hdc_vector: List[float]) -> List[float]:
        """Project 10,000-dim HDC to 2048-dim dense"""
        if len(hdc_vector) != 10000:
            raise ValueError(f"Expected 10000-dim HDC vector, got {len(hdc_vector)}")

        if self.encoder_weights is None:
            raise RuntimeError("Bridge weights not loaded. System is in uninitialized state.")

        hdc_array = np.array(hdc_vector, dtype=np.float32)
        dense_array = hdc_array @ self.encoder_weights

        return dense_array.tolist()

    def dense_to_hdc(self, dense_vector: List[float]) -> List[float]:
        """Project 2048-dim dense to 10,000-dim HDC"""
        if len(dense_vector) != 2048:
            raise ValueError(f"Expected 2048-dim dense vector, got {len(dense_vector)}")

        dense_array = np.array(dense_vector, dtype=np.float32)

        # Dense to sparse projection
        hdc_array = dense_array @ self.decoder_weights

        # Sparsify (keep top-k active dimensions)
        k = 100  # 1% sparsity
        top_k_indices = np.argsort(np.abs(hdc_array))[-k:]
        sparse_result = np.zeros_like(hdc_array)
        sparse_result[top_k_indices] = hdc_array[top_k_indices]

        return sparse_result.tolist()

    def load_weights(self, weights: Dict[str, np.ndarray]):
        """Load pre-trained weights from B1 data"""
        if "encoder_weights" in weights:
            self.encoder_weights = weights["encoder_weights"]
        if "decoder_weights" in weights:
            self.decoder_weights = weights["decoder_weights"]
        logger.info("Loaded pre-trained bridge weights")


# Global bridge instance
_bridge: Optional[CycleConsistentBridge] = None


def get_bridge() -> CycleConsistentBridge:
    """Get or create bridge singleton"""
    global _bridge
    if _bridge is None:
        _bridge = CycleConsistentBridge()
    return _bridge


def bridge_hdc_to_dense(hdc_vector: List[float]) -> List[float]:
    """Convenience function for HDC → Dense"""
    bridge = get_bridge()
    return bridge.hdc_to_dense(hdc_vector)


def bridge_dense_to_hdc(dense_vector: List[float]) -> List[float]:
    """Convenience function for Dense → HDC"""
    bridge = get_bridge()
    return bridge.dense_to_hdc(dense_vector)


# ============================================================================
# HOPFIELD FUNCTION (Pattern Storage and Retrieval)
# ============================================================================


class ContinuousHopfieldNetwork:
    """Modern Continuous Hopfield Network (Dense Associative Memory)"""

    def __init__(self, beta: float = 1.0):
        self.patterns = []
        self.beta = beta
        logger.info("Continuous Hopfield Network initialized (float32, softmax attention)")

    def store_pattern(self, pattern: np.ndarray):
        """Store continuous float32 pattern and sync to Redis for the Pulse."""
        import os
        import time

        pattern = np.array(pattern, dtype=np.float32).flatten()
        norm = np.linalg.norm(pattern) + 1e-12
        normalized_pattern = pattern / norm

        # 1. Store in active neural memory
        self.patterns.append(normalized_pattern)

        # 2. Sync to Redis for the Default Mode Network (Pulse)
        try:
            import redis
            r = redis.Redis(
                host=os.environ.get("PYTHIA_REDIS_HOST", "localhost"),
                port=int(os.environ.get("PYTHIA_REDIS_PORT", "6380")),
                socket_timeout=1.0
            )
            step_id = int(time.time() * 1000)
            key = f"attractor:step:{step_id}"
            r.set(key, normalized_pattern.tobytes())
        except Exception:
            pass  # Fail silently

    def retrieve_pattern(self, probe: np.ndarray) -> np.ndarray:
        """Retrieve using continuous softmax attention (Modern Hopfield update)"""
        if not self.patterns:
            return probe

        probe = np.array(probe, dtype=np.float32).flatten()
        probe = probe / (np.linalg.norm(probe) + 1e-12)

        M = np.vstack(self.patterns)
        similarities = np.dot(M, probe) * self.beta
        exp_sim = np.exp(similarities - np.max(similarities))
        attention = exp_sim / np.sum(exp_sim)
        retrieved = np.dot(attention, M)
        return retrieved / (np.linalg.norm(retrieved) + 1e-12)

    def compute_energy(self, pattern: np.ndarray) -> float:
        """Compute Hopfield energy (negative similarity to stored patterns)"""
        if not self.patterns:
            return 0.0
        probe = np.array(pattern, dtype=np.float32).flatten()
        probe = probe / (np.linalg.norm(probe) + 1e-12)
        similarities = np.dot(np.vstack(self.patterns), probe)
        return float(-np.max(similarities))

    def similarity(self, pattern1: np.ndarray, pattern2: np.ndarray) -> float:
        """Compute cosine similarity"""
        p1 = np.array(pattern1, dtype=np.float32).flatten()
        p2 = np.array(pattern2, dtype=np.float32).flatten()
        return float(np.dot(p1, p2) / (np.linalg.norm(p1) * np.linalg.norm(p2) + 1e-12))


# Global Hopfield instance
_hopfield: Optional[ContinuousHopfieldNetwork] = None


def get_hopfield() -> ContinuousHopfieldNetwork:
    """Get or create Hopfield network singleton"""
    global _hopfield
    if _hopfield is None:
        _hopfield = ContinuousHopfieldNetwork(beta=1.0)
    return _hopfield


def store_hopfield_pattern(pattern: List[float]):
    """Convenience function to store a pattern"""
    hopfield = get_hopfield()
    hopfield.store_pattern(np.array(pattern))


def retrieve_hopfield_pattern(probe: List[float]) -> List[float]:
    """Convenience function to retrieve a pattern"""
    hopfield = get_hopfield()
    result = hopfield.retrieve_pattern(np.array(probe))
    return result.tolist()


def compute_hopfield_energy(pattern: List[float]) -> float:
    """Convenience function to compute energy"""
    hopfield = get_hopfield()
    return hopfield.compute_energy(np.array(pattern))


# ============================================================================
# LOADING FUNCTIONS FROM B1 DATA
# ============================================================================


def load_conformal_lift_params(b1_data: Dict[str, Any]) -> Dict[str, np.ndarray]:
    """Load conformal lift parameters from B1 data"""
    if "conformal_data" in b1_data:
        data = b1_data["conformal_data"]
        return {
            "projection_matrix": np.array(data["projection_matrix"]),
            "basis_vectors": np.array(data.get("basis_vectors", np.eye(5))),
            "normalization": data.get("normalization", {"mean": 0.0, "std": 1.0}),
        }
    return {}


def load_bridge_weights(b1_data: Dict[str, Any]) -> Dict[str, np.ndarray]:
    """Load bridge weights from B1 data"""
    if "bridge_mappings" in b1_data:
        data = b1_data["bridge_mappings"]
        return {
            "encoder_weights": np.array(data["hdc_to_dense_weights"]),
            "decoder_weights": np.array(data["dense_to_hdc_weights"]),
        }
    return {}


def load_hopfield_patterns(b1_data: Dict[str, Any]) -> List[np.ndarray]:
    """Load Hopfield patterns from B1 data"""
    if "hopfield_patterns" in b1_data:
        return [np.array(p) for p in b1_data["hopfield_patterns"]]
    return []


def initialize_pythia_functions(b1_data: Dict[str, Any]):
    """Initialize all Pythia functions with B1 data"""
    logger.info("Initializing Pythia core functions from B1 data...")

    # Load conformal lift parameters
    conformal_params = load_conformal_lift_params(b1_data)
    if conformal_params:
        logger.info("✓ Loaded conformal lift parameters")

    # Load bridge weights
    bridge_weights = load_bridge_weights(b1_data)
    if bridge_weights:
        bridge = get_bridge()
        bridge.load_weights(bridge_weights)
        logger.info("✓ Loaded bridge weights")

    # Load Hopfield patterns
    hopfield_patterns = load_hopfield_patterns(b1_data)
    hopfield = get_hopfield()
    for pattern in hopfield_patterns:
        hopfield.store_pattern(pattern)
    if hopfield_patterns:
        logger.info(f"✓ Loaded {len(hopfield_patterns)} Hopfield patterns")

    logger.info("✅ Pythia core functions initialized!")

    return {
        "conformal_params": conformal_params,
        "bridge": get_bridge(),
        "hopfield": get_hopfield(),
    }
