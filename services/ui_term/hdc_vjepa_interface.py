"""
HDC-VJEPA Interface - NumPy Version
=================================

Bridge between HDC vectors and V-JEPA's latent space.
Treats a sequence of HDC ticks as a 'video' stream.
"""

import numpy as np
from typing import List
from .aflash_encoder import AFlashEncoder


class HDC_VJEPA_Interface:
    """
    Bridge between HDC vectors and V-JEPA's latent space.
    Treats a sequence of HDC ticks as a 'video' stream.
    """
    
    def __init__(self, hdc_dim=10000, jepa_dim=768, seq_len=16):
        self.hdc_dim = hdc_dim
        self.jepa_dim = jepa_dim
        self.seq_len = seq_len
        
        # HDC encoder
        self.hdc_encoder = AFlashEncoder(input_dim=1024, hdc_dim=hdc_dim)
        
        # Project 10k-bit HDC -> 768-dim
        # Xavier/Glorot initialization
        limit = np.sqrt(6 / (hdc_dim + jepa_dim))
        self.projector_weight = np.random.uniform(
            -limit, limit, (jepa_dim, hdc_dim)
        ).astype(np.float32)
        self.projector_bias = np.zeros(jepa_dim, dtype=np.float32)
        
        # Layer norm parameters (learned scale and shift, but we'll use fixed for simplicity)
        self.ln_scale = np.ones(jepa_dim, dtype=np.float32)
        self.ln_eps = 1e-5
        
        # Positional embedding
        self.pos_embed = np.zeros((1, seq_len, jepa_dim), dtype=np.float32)
        
    def _gelu(self, x: np.ndarray) -> np.ndarray:
        """GELU activation function."""
        return 0.5 * x * (1 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * x**3)))
    
    def _layer_norm(self, x: np.ndarray) -> np.ndarray:
        """Layer normalization."""
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        return self.ln_scale * (x - mean) / np.sqrt(var + self.ln_eps) + self.ln_bias
    
    def forward(self, telemetry_stream: List[np.ndarray]) -> np.ndarray:
        """
        HDC encode each state -> project to JEPA space.
        
        Args:
            telemetry_stream: List of state vectors or inputs
            
        Returns:
            Array of shape (batch, seq, jepa_dim)
        """
        # HDC encode each state
        raw_hdc = []
        for s in telemetry_stream:
            # Assuming s is suitable for AFlashEncoder
            encoded = self.hdc_encoder.forward(s)
            raw_hdc.append(encoded)
        
        # Stack: (Seq, HDC_Dim) -> (Batch, Seq, HDC_Dim)
        # Assuming batch dimension of 1
        x = np.stack(raw_hdc)  # (Seq, HDC_Dim)
        x = x[np.newaxis, :, :]  # (1, Seq, HDC_Dim)
        
        # Project to JEPA dim: (1, Seq, HDC_Dim) -> (1, Seq, JEPA_Dim)
        # Reshape for matrix multiplication
        batch, seq, hdc_d = x.shape
        x_reshaped = x.reshape(-1, hdc_d)  # (batch*seq, hdc_dim)
        projected = x_reshaped @ self.projector_weight.T + self.projector_bias  # (batch*seq, jepa_dim)
        x = projected.reshape(batch, seq, -1)  # (1, seq, jepa_dim)
        
        # Layer norm
        x = self._layer_norm(x)
        
        # GELU activation
        x = self._gelu(x)
        
        # Add positional embeddings
        seq_len_actual = min(x.shape[1], self.seq_len)
        x[:, :seq_len_actual, :] += self.pos_embed[:, :seq_len_actual, :]
        
        return x
