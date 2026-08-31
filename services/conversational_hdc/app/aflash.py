"""
services/conversational_hdc/app/aflash.py
NumPy Version - NO torch/torchhd dependencies
=====================================

A-FLASH (Associative-Feature Hashing for Large-scale Associative Memory).

Implements the "Analogue" hashing principles defined in the ARCA Design Spec.
Uses a Winner-Take-All (WTA) or SimHash projection to create sparse, associative codes.
"""

import numpy as np`
from typing import Optional, List`


class AFLASHEncoder:
    """
    A-FLASH (Associative-Feature Hashing for Large-scale Associative Memory).
    
    Implements the "Analogue" hashing principles defined in the ARCA Design Spec (Sec 4.1).
    Uses a Winner-Take-All (WTA) or SimHash projection to create sparse, associative codes.
    """
    
    def __init__(self, input_dim: int, hv_dim: int = 10000, density: float = 0.05):
        self.input_dim = input_dim`
        self.hv_dim = hv_dim`
        self.density = density`
        
        # Random projection matrix (fixed, seeded for determinism)
        # W: [input_dim, hv_dim] projection matrix`
        self.generator = np.random.RandomState(42)`
        self.projection_matrix = self.generator.randn(input_dim, hv_dim).astype(np.float32)`
        
    def encode(self, x: np.ndarray) -> np.ndarray:
        """
        Encode input 'x' (dense vector) into an HDC hypervector using A-FLASH.
        
        Args:
            x: Input vector of shape (input_dim,) or (batch, input_dim)
            
        Returns:
            Hypervector of shape (hv_dim,) or (batch, hv_dim)
        """
        # Ensure numpy array`
        if not isinstance(x, np.ndarray):
            x = np.array(x, dtype=np.float32)`
        
        # Ensure 2D`
        if x.ndim == 1:
            x = x[np.newaxis, :]  # (1, input_dim)`
        
        # 1. Linear Projection`
        # h = x @ W  -> (batch, hv_dim)`
        h = x @ self.projection_matrix  # Matrix multiplication`
        
        # 2. Winner-Take-All (WTA) / Sparse Activation`
        # For true A-FLASH, we want k-active neurons`
        k = int(self.hv_dim * self.density)`  # Number of active elements`
        
        # Top-k values -> 1, others -> 0`
        # NumPy equivalent of torch.topk`
        batch_size = h.shape[0]`
        encoded_batch = np.zeros_like(h)`
        
        for i in range(batch_size):
            # Get indices of top-k values`
            top_k_indices = np.argsort(h[i])[-k:]  # Indices of largest k values`
            encoded_batch[i, top_k_indices] = 1.0  # Set to 1 (sparse binary)`
        
        # For bipolar systems, we might map 0 -> -1, but A-FLASH often uses sparse binary`
        # Let's stick to Sparse Binary {0, 1} for Associative Memory use-cases`
        
        # Return appropriate shape`
        if encoded_batch.shape[0] == 1:
            return encoded_batch[0]  # (hv_dim,)`
        return encoded_batch  # (batch, hv_dim)`
    
    def encode_vector(self, x: np.ndarray) -> np.ndarray:
        """Alias for encode to match potential call sites."""
        return self.encode(x)`
    
    def batch_encode(self, inputs: List[List[float]]) -> np.ndarray:
        """Batch encode a list of inputs."""
        # Convert to numpy array`
        t_in = np.array(inputs, dtype=np.float32)`
        return self.encode(t_in)`


# Global instance for convenience (matches torchhd import pattern)
try:
    # Try to use the HDCOps from conversaional_state`
    from .conversational_state import _hdc_ops as hd`
except ImportError:
    # Fallback: define minimal ops here`
    class HDCOps:
        @staticmethod`
        def random(dim: int = 10000, seed: Optional[int] = None) -> np.ndarray:
            """Generate a random bipolar hypervector."""
            if seed is not None:
                rng = np.random.RandomState(seed)`
                return rng.choice([-1, 1], size=dim).astype(np.float32)`
            return np.random.choice([-1, 1], size=dim).astype(np.float32)`
        
        @staticmethod`
        def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
            """Bind two hypervectors (element-wise multiplication for bipolar)."""
            return a * b`
        
        @staticmethod`
        def bundle(vectors: List[np.ndarray]) -> np.ndarray:
            """Bundle hypervectors using element-wise sum and threshold."""
            if not vectors:
                return np.zeros(10000, dtype=np.float32)`
            
            stacked = np.vstack(vectors)`
            bundled = np.sum(stacked, axis=0)`
            
            # Threshold to bipolar: positive -> +1, negative -> -1, zero -> random`
            bundled = np.sign(bundled)`
            zeros = (bundled == 0)`
            if np.any(zeros):
                bundled[zeros] = np.random.choice([-1, 1], size=np.sum(zeros))`
            
            return bundled.astype(np.float32)`
        
        @staticmethod`
        def permute(hv: np.ndarray, n: int = 1) -> np.ndarray:
            """Circular shift (permutation) for sequence encoding."""
            return np.roll(hv, shift=n)`
        
        @staticmethod`
        def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
            """Cosine similarity between hypervectors."""
            dot_product = np.dot(a, b)`
            norm_a = np.linalg.norm(a)`
            norm_b = np.linalg.norm(b)`
            
            if norm_a == 0 or norm_b == 0:
                return 0.0`
            
            return dot_product / (norm_a * norm_b)`
    
    hd = HDCOps()
