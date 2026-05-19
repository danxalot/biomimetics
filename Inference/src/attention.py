"""Geometric Product Attention (GPA) — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/attention.py.
No autograd. FP32 strict. All nn.Linear replaced with np.dot + bias arrays.

Weight contract (loaded from checkpoint via weight_store):
  W_q:           [d_model, d_model] float32
  W_q_bias:      [d_model]          float32
  W_k:           [d_model, d_model] float32
  W_k_bias:      [d_model]          float32
  W_v:           [d_model, d_model] float32
  W_v_bias:      [d_model]          float32
  W_out:         [d_model, d_model] float32
  W_out_bias:    [d_model]          float32
  scalar_weight: scalar float32
  bivector_weight: scalar float32
"""
import math
import numpy as np
from .config import CONFIG


class GeometricProductAttention:
    """GPA: scalar proximity + bivector orientational coupling.

    Q·K  =  ⟨Q,K⟩  (scalar / proximity)
           + Q∧K    (bivector / orientational coupling)

    Mirrors pytorch GeometricProductAttention(nn.Module).
    Call as gpa(x) to match forward() signature.

    Args:
        weights: dict with keys as documented in module docstring.
                 If None, random-init weights are used (for testing).
    """

    def __init__(self, d_model: int, n_heads: int, mv_dim: int, weights: dict = None):
        self.d_model   = d_model
        self.n_heads   = n_heads
        self.head_dim  = d_model // n_heads
        self.mv_dim    = mv_dim
        self.scale     = math.sqrt(self.head_dim)

        if weights is not None:
            self.W_q   = np.asarray(weights["W_q"],   dtype=np.float32)
            self.b_q   = np.asarray(weights["W_q_bias"], dtype=np.float32)
            self.W_k   = np.asarray(weights["W_k"],   dtype=np.float32)
            self.b_k   = np.asarray(weights["W_k_bias"], dtype=np.float32)
            self.W_v   = np.asarray(weights["W_v"],   dtype=np.float32)
            self.b_v   = np.asarray(weights["W_v_bias"], dtype=np.float32)
            self.W_out = np.asarray(weights["W_out"],  dtype=np.float32)
            self.b_out = np.asarray(weights["W_out_bias"], dtype=np.float32)
            self.scalar_weight  = float(weights["scalar_weight"])
            self.bivector_weight = float(weights["bivector_weight"])
        else:
            # Random init — for unit tests only
            rng = np.random.default_rng(0)
            def _rand(shape): return rng.standard_normal(shape).astype(np.float32) * 0.02
            self.W_q   = _rand((d_model, d_model))
            self.b_q   = np.zeros(d_model, dtype=np.float32)
            self.W_k   = _rand((d_model, d_model))
            self.b_k   = np.zeros(d_model, dtype=np.float32)
            self.W_v   = _rand((d_model, d_model))
            self.b_v   = np.zeros(d_model, dtype=np.float32)
            self.W_out = _rand((d_model, d_model))
            self.b_out = np.zeros(d_model, dtype=np.float32)
            self.scalar_weight   = 0.6
            self.bivector_weight = 0.4

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Numerically stable softmax along last axis."""
        e = np.exp(x - x.max(axis=-1, keepdims=True))
        return e / e.sum(axis=-1, keepdims=True)

    def __call__(self, x: np.ndarray, mask: np.ndarray = None) -> np.ndarray:
        """Forward pass.

        Args:
            x:    np.ndarray [B, T, d_model] float32
            mask: np.ndarray [B, n_heads, T, T] float32 or None
                  (0 = masked, 1 = unmasked — matches pytorch convention)

        Returns:
            np.ndarray [B, T, d_model] float32
        """
        x = np.asarray(x, dtype=np.float32)
        B, T, D = x.shape

        # Linear projections: [B, T, d_model]
        Q = x @ self.W_q.T + self.b_q
        K = x @ self.W_k.T + self.b_k
        V = x @ self.W_v.T + self.b_v

        # Reshape to [B, n_heads, T, head_dim]
        Q = Q.reshape(B, T, self.n_heads, self.head_dim).transpose(0, 2, 1, 3)
        K = K.reshape(B, T, self.n_heads, self.head_dim).transpose(0, 2, 1, 3)
        V = V.reshape(B, T, self.n_heads, self.head_dim).transpose(0, 2, 1, 3)

        # Scalar attention [B, n_heads, T, T]
        scalar_attn = np.matmul(Q, K.transpose(0, 1, 3, 2)) / self.scale

        # Bivector attention: antisymmetric component — captures orientational coupling
        bivector_attn      = (scalar_attn - scalar_attn.transpose(0, 1, 3, 2)) * 0.5
        bivector_magnitude = np.abs(bivector_attn).sum(axis=-1, keepdims=True)
        bivector_magnitude = np.broadcast_to(bivector_magnitude, scalar_attn.shape).copy()

        attn = self.scalar_weight * scalar_attn + self.bivector_weight * bivector_magnitude

        if mask is not None:
            attn = np.where(mask == 0, -1e9, attn)

        attn = self._softmax(attn)

        # Context vectors [B, n_heads, T, head_dim]
        out = np.matmul(attn, V)
        # Merge heads: [B, T, d_model]
        out = out.transpose(0, 2, 1, 3).reshape(B, T, D)
        return out @ self.W_out.T + self.b_out
