import math
import numpy as np

def _gelu(x: np.ndarray) -> np.ndarray:
    """Gaussian Error Linear Unit - tanh approximation."""
    return 0.5 * x * (1.0 + np.tanh(math.sqrt(2.0 / math.pi) * (x + 0.044715 * x**3)))

def _layer_norm(x: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    """Layer Normalization along the last dimension."""
    mean = np.mean(x, axis=-1, keepdims=True)
    var  = np.var(x,  axis=-1, keepdims=True)
    return (x - mean) / np.sqrt(var + eps)

class GradePreservingProjection:
    """
    Translates CGA multivectors (rotors) into dense 2048D language model embeddings.
    
    Architecture (Phase C2):
        Scalar (1)    -> Linear(1, 256)   -> GELU
        Vectors (5)   -> Linear(5, 768)   -> GELU
        Bivectors (10) -> Linear(10, 1024) -> GELU
        Concatenate   -> [B, 2048] -> LayerNorm
    """
    def __init__(self, seed: int = 42):
        rng = np.random.RandomState(seed)
        # Grade 0: Scalar (e0)
        self.w_scalar   = rng.randn(1,  256).astype(np.float32) * 0.1
        self.b_scalar   = np.zeros(256, dtype=np.float32)
        
        # Grade 1: Vectors (e1, e2, e3, e+, e-)
        self.w_vector   = rng.randn(5,  768).astype(np.float32) * 0.1
        self.b_vector   = np.zeros(768, dtype=np.float32)
        
        # Grade 2: Bivectors (e12, e13, e14, e15, e23, e24, e25, e34, e35, e45)
        self.w_bivector = rng.randn(10, 1024).astype(np.float32) * 0.1
        self.b_bivector = np.zeros(1024, dtype=np.float32)

    def forward(self, rotor_32d: np.ndarray) -> np.ndarray:
        """
        Projects a 32D CGA multivector into a 2048D dense embedding.
        
        Args:
            rotor_32d: shape (32,) or (B, 32)
        Returns:
            shape (B, 2048)
        """
        if rotor_32d.ndim == 1:
            rotor_32d = rotor_32d[np.newaxis, :]
            
        # Extraction (Matches Cl(4,1) null cone indexing)
        scalar    = rotor_32d[:, 0:1]    # e0
        vectors   = rotor_32d[:, 1:6]    # e1-e5
        bivectors = rotor_32d[:, 6:16]   # e12-e45 (approximate indices for bivector block)
        
        # Grade-wise projections
        e_s  = _gelu(scalar    @ self.w_scalar   + self.b_scalar)
        e_v  = _gelu(vectors   @ self.w_vector   + self.b_vector)
        e_bv = _gelu(bivectors @ self.w_bivector + self.b_bivector)
        
        # Integration
        combined = np.concatenate([e_s, e_v, e_bv], axis=1)
        return _layer_norm(combined)
