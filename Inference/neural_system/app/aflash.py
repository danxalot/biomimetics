# services/neural_system/app/aflash.py
import numpy as np
from typing import Optional, List

class AFLASHEncoder:
    """
    A-FLASH (Associative-Feature Hashing for Large-scale Associative Memory).
    
    Implements the "Analogue" hashing principles defined in the ARCA Design Spec (Sec 4.1).
    Uses a Winner-Take-All (WTA) or SimHash projection to create sparse, associative codes.
    """
    
    def __init__(self, input_dim: int, hv_dim: int = 10000, density: float = 0.05):
        self.input_dim = input_dim
        self.hv_dim = hv_dim
        self.density = density
        
        # Random projection matrix (fixed)
        # We use a Seeded generator for determinism
        self.generator = np.random.RandomState(42)
        
        # W: [In, Out] projection matrix
        self.projection_matrix = self.generator.randn(input_dim, hv_dim).astype(np.float32)

    def encode(self, x: np.ndarray) -> np.ndarray:
        """
        Encode input 'x' (dense vector) into an HDC hypervector using A-FLASH.
        """
        # Ensure 2D for batch processing
        if x.ndim == 1:
            x = x.reshape(1, -1)
        
        # 1. Linear Projection
        # h = x @ W
        # If x is [B, In], W is [In, Out] -> [B, Out]
        h = np.dot(x, self.projection_matrix)
        
        # 2. Winner-Take-All (WTA) / Sparse Activation
        # For true A-FLASH, we want k-active neurons
        k = int(self.hv_dim * self.density)
        
        # Top-k values -> 1, others -> 0
        # Get indices of top k values for each row
        # Using argpartition for efficiency (O(n) vs O(n log n) for full sort)
        top_k_indices = np.argpartition(h, -k, axis=1)[:, -k:]
        
        # Create binary mask
        encoded = np.zeros_like(h)
        # Use advanced indexing to set top-k positions to 1
        batch_indices = np.arange(h.shape[0])[:, None]
        encoded[batch_indices, top_k_indices] = 1.0
        
        # For bipolar systems, we might map 0 -> -1, but A-FLASH often uses sparse binary
        # Let's stick to Sparse Binary {0, 1} for Associative Memory use-cases
        return encoded

    def batch_encode(self, inputs: List[List[float]]) -> np.ndarray:
        t_in = np.array(inputs, dtype=np.float32)
        return self.encode(t_in)