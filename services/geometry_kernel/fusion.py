
"""
Fusion Layer for Geometry Kernel.

Combines multimodal embeddings into a unified 1024-dim latent state vector.
STANDARDIZED for JEPA compatibility.

Inputs:
- Vision: SigLIP (1152 dim) → 341 projected
- Language: Qwen3 (1024 dim) → 342 projected  
- Proprioception: HSE (10000 dim binary) → 341 projected

Output:
- Fused Latent Vector (dim=1024, JEPA-ready)
"""


import numpy as np
from typing import Optional, List, Dict, Union
from dataclasses import dataclass

@dataclass
class FusionConfig:
    # STANDARDIZED: All projections target 1024-dim for JEPA compatibility
    output_dim: int = 1024      # Universal latent dimension (JEPA ready)
    vision_dim: int = 1152      # SigLIP Large input
    text_dim: int = 1024        # Qwen3 Embedding (native 1024)
    hse_dim: int = 10000        # HSE binary hypervector input
    use_projection: bool = True
    # Projection targets (all standardized to sum to output_dim)
    vision_proj_dim: int = 341  # ~1/3
    text_proj_dim: int = 342    # ~1/3  
    hse_proj_dim: int = 341     # ~1/3 (341 + 342 + 341 = 1024)


class FusionLayer:
    """
    Multimodal Fusion Layer.
    Uses concatenation + linear projection (simulated via random matrix if no weights)
    to fuse inputs into STANDARDIZED 1024-dim output for JEPA compatibility.
    """
    def __init__(self, config: FusionConfig = FusionConfig()):
        self.config = config
        self.weights = {}
        
        # Initialize random projection matrices (fixed seed for deterministic behavior)
        # In a trained system, these would be loaded from a checkpoint.
        rng = np.random.default_rng(42)
        
        if self.config.use_projection:
            # STANDARDIZED 1024-dim output: Each modality projects to ~1/3
            # vision: 1152 → 341
            # text:   1024 → 342
            # hse:    10000 → 341
            # Total: 341 + 342 + 341 = 1024
            
            self.hse_proj = rng.standard_normal((self.config.hse_dim, self.config.hse_proj_dim)) / np.sqrt(self.config.hse_dim)
            self.vision_proj = rng.standard_normal((self.config.vision_dim, self.config.vision_proj_dim)) / np.sqrt(self.config.vision_dim)
            self.text_proj = rng.standard_normal((self.config.text_dim, self.config.text_proj_dim)) / np.sqrt(self.config.text_dim)
            
            # Final fusion dimension
            self.final_dim = self.config.vision_proj_dim + self.config.text_proj_dim + self.config.hse_proj_dim
            assert self.final_dim == self.config.output_dim, f"Projection dims must sum to output_dim: {self.final_dim} != {self.config.output_dim}"

    
    def fuse(self, 
             vision_emb: Optional[np.ndarray] = None, 
             text_emb: Optional[np.ndarray] = None, 
             hse_emb: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Fuse available embeddings into a single vector.
        """
        # Handle missing inputs with zero vectors
        v_vec = vision_emb if vision_emb is not None else np.zeros(self.config.vision_dim)
        t_vec = text_emb if text_emb is not None else np.zeros(self.config.text_dim)
        h_vec = hse_emb if hse_emb is not None else np.zeros(self.config.hse_dim)
        
        # Normalize inputs
        v_vec = self._normalize(v_vec)
        t_vec = self._normalize(t_vec)
        # HSE is binary/sparse, maybe don't normalize or just scale?
        # If it's from HSE service, it might be 0/1. 
        # Converting to float for projection.
        h_vec = h_vec.astype(np.float32)
        
        # Project
        if self.config.use_projection:
            v_proj = v_vec @ self.vision_proj
            t_proj = t_vec @ self.text_proj
            h_proj = h_vec @ self.hse_proj
        else:
            v_proj, t_proj, h_proj = v_vec, t_vec, h_vec
            
        # Concatenate
        fused = np.concatenate([v_proj, t_proj, h_proj])
        
        # Final Norm
        return self._normalize(fused)

    def _normalize(self, v: np.ndarray) -> np.ndarray:
        """L2 Normalization."""
        norm = np.linalg.norm(v)
        if norm == 0:
            return v
        return v / norm
