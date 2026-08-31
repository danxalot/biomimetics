import logging
import numpy as np
from typing import List, Dict, Any, Optional
import asyncio
import httpx
from datetime import datetime

# Configure Logging
logger = logging.getLogger("HDCGenesisChain")

# NumPy-based Hyperdimensional Computing Operations (replacing torchhd)
class HDCOps:
    """NumPy-based HDC operations for bipolar {-1, +1} vectors."""
    
    @staticmethod
    def random(dim: int = 10000, seed: Optional[int] = None) -> np.ndarray:
        """Generate a random bipolar hypervector."""
        if seed is not None:
            rng = np.random.RandomState(seed)
            return rng.choice([-1, 1], size=dim)
        return np.random.choice([-1, 1], size=dim)
    
    @staticmethod
    def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Bind two hypervectors (element-wise multiplication for bipolar)."""
        return a * b
    
    @staticmethod
    def bundle(vectors: List[np.ndarray]) -> np.ndarray:
        """Bundle hypervectors using element-wise sum and threshold."""
        if not vectors:
            return np.zeros(10000, dtype=np.float32)
        
        stacked = np.vstack(vectors)
        bundled = np.sum(stacked, axis=0)
        
        # Threshold to bipolar: positive -> +1, negative -> -1, zero -> random
        bundled = np.sign(bundled)
        zeros = (bundled == 0)
        if np.any(zeros):
            bundled[zeros] = np.random.choice([-1, 1], size=np.sum(zeros))
        
        return bundled.astype(np.float32)
    
    @staticmethod
    def permute(hv: np.ndarray, n: int = 1) -> np.ndarray:
        """Circular shift (permutation) for sequence encoding."""
        return np.roll(hv, shift=n)
    
    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between hypervectors."""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        # Avoid division by zero
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return dot_product / (norm_a * norm_b)

# Global HDC operations instance
_hdc_ops = HDCOps()

class AFLASHEncoder:
    """
    Wrapper for HDC Encoding (SentenceTransformer -> Projection).
    For now, uses Random Projection or TorchHD directly.
    """
    def __init__(self, hv_dim: int = 10000):
        self.hv_dim = hv_dim
        
    def encode_text(self, text: str) -> np.ndarray:
        # Placeholder: Semantic Hash / Token-based encoding
        # In real system: Embed -> Project
        # Here: Random deterministic hash for demo/parsing
        seed = hash(text) % (2**32)
        return _hdc_ops.random(1, self.hv_dim, generator=np.random.RandomState(seed))[0]

    def encode_vector(self, vector: np.ndarray) -> np.ndarray:
        # Project dense vector to HDC
        # Simple projection: take first hv_dim elements or repeat/pad
        if len(vector) >= self.hv_dim:
            return vector[:self.hv_dim]
        else:
            # Repeat vector to fill dimensions
            repeats = self.hv_dim // len(vector) + 1
            repeated = np.tile(vector, repeats)
            return repeated[:self.hv_dim]

    def bind(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Bind two hypervectors (element-wise multiplication for bipolar)."""
        return _hdc_ops.bind(a, b)
    
    def bundle(self, vectors: List[np.ndarray]) -> np.ndarray:
        """Bundle hypervectors."""
        return _hdc_ops.bundle(vectors)
    
    def permute(self, hv: np.ndarray, n: int = 1) -> np.ndarray:
        """Circular shift (permutation) for sequence encoding."""
        return _hdc_ops.permute(hv, n)

class HDCGenesisChain:
    def __init__(self, encoder=None, hv_dim: int = 10000):
        self.hv_dim = hv_dim
        self.encoder = encoder or AFLASHEncoder(hv_dim)
        
        # Replace torchhd functions with numpy equivalents
        self.bind = _hdc_ops.bind
        self.bundle = _hdc_ops.bundle
        self.permute = _hdc_ops.permute
        self.role_objectives = _hdc_ops.random(1, hv_dim)[0]
        self.role_prerequisites = _hdc_ops.random(1, hv_dim)[0]
        self.role_steps = _hdc_ops.random(1, hv_dim)[0]
        self.role_criteria = _hdc_ops.random(1, hv_dim)[0]
        self.plan_archetypes = {"standard": _hdc_ops.random(1, hv_dim)[0]}
        
        # Initialize state
        self.current_state = np.zeros(hv_dim, dtype=np.float32)
        
    def encode_state(self, state_dict: Dict[str, Any]) -> np.ndarray:
        """Encode a state dictionary into an HDC vector."""
        # Simple encoding: hash keys and values to basis vectors
        state_hv = np.zeros(self.hv_dim, dtype=np.float32)
        
        for key, value in state_dict.items():
            # Create basis vector for key
            key_seed = hash(f"key_{key}") % (2**32)
            key_hv = _hdc_ops.random(1, self.hv_dim, generator=np.random.RandomState(key_seed))[0]
            
            # Create basis vector for value (handle different types)
            if isinstance(value, str):
                value_seed = hash(f"val_{value}") % (2**32)
                value_hv = _hdc_ops.random(1, self.hv_dim, generator=np.random.RandomState(value_seed))[0]
            elif isinstance(value, (int, float)):
                # Thermometer encoding for numeric values
                normalized = max(0.0, min(1.0, float(value)))  # Assume 0-1 range for now
                levels = 100
                active_levels = int(normalized * levels)
                level_vectors = [_hdc_ops.get_basis(f"level_{i}") for i in range(active_levels)]
                value_hv = _hdc_ops.bundle(level_vectors) if level_vectors else np.zeros(self.hv_dim, dtype=np.float32)
            else:
                # Default to random for complex types
                value_seed = hash(f"val_{str(value)}") % (2**32)
                value_hv = _hdc_ops.random(1, self.hv_dim, generator=np.random.RandomState(value_seed))[0]
            
            # Bind key and value, then bundle into state
            kv_hv = _hdc_ops.bind(key_hv, value_hv)
            state_hv = _hdc_ops.bundle([state_hv, kv_hv])
        
        return state_hv
    
    def process_transition(self, state_hv: np.ndarray, action_hv: np.ndarray) -> np.ndarray:
        """Process a state-action transition."""
        # Bind state and action
        sa_hv = _hdc_ops.bind(state_hv, action_hv)
        # Bundle with current state
        self.current_state = _hdc_ops.bundle([self.current_state, sa_hv])
        return self.current_state.copy()
    
    def get_state_vector(self) -> np.ndarray:
        """Get current state vector."""
        return self.current_state.copy()
    
    def reset(self):
        """Reset the genesis chain state."""
        self.current_state = np.zeros(self.hv_dim, dtype=np.float32)

