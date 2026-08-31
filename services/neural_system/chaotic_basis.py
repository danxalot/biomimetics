import numpy as np

class ChaoticBasis:
    """
    Deterministic Chaotic Map Generator for HDC Basis Vectors.
    Generates infinite, consistent basis vectors on-the-fly without memory storage.
    """
    
    def __init__(self, seed_map: str = "logistic"):
        self.map_type = seed_map

    def logistic_map(self, x: float, r: float = 3.99) -> float:
        """x_{n+1} = r * x_n * (1 - x_n)"""
        return r * x * (1 - x)

    def generate_basis(self, seed_key: str, dim: int = 10000) -> np.ndarray:
        """
        Generates a deterministic Hypervector from a string key using chaotic iteration.
        1. Hash key to get initial x0.
        2. Iterate map 'dim' times to trace trajectory.
        3. Quantize trajectory to {-1, 1}.
        """
        # Simple string hash to float [0, 1]
        seed_hash = int(input_str_hash(seed_key), 16) if isinstance(seed_key, str) else hash(seed_key)
        # Normalize to (0, 1) safely
        x = (seed_hash % 1000000) / 1000000.0 + 1e-6
        
        trajectory = np.zeros(dim, dtype=np.float32)
        
        # Warmup to forget seed structure
        for _ in range(50):
            x = self.logistic_map(x)
            
        # Generate
        for i in range(dim):
            x = self.logistic_map(x)
            trajectory[i] = x
            
        # Quantize: Logistic map mean is 0.5 for r=4
        # values > 0.5 -> 1, < 0.5 -> -1
        return np.where(trajectory > 0.5, 1.0, -1.0).astype(np.float32)

def input_str_hash(s):
    import hashlib
    return hashlib.md5(s.encode()).hexdigest()
