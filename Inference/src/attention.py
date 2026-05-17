"""Geometric Product Attention (GPA).

Replaces standard dot-product attention with a geometric-product decomposition:
    Q·K = ⟨Q,K⟩ (scalar / proximity) + Q∧K (bivector / orientational coupling)

The dual decomposition is interpretable: the system reveals whether attention
is driven by distance (scalar) or alignment (bivector).

Originally from `train_script.py:286-343`.
"""
import math
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


class GeometricProductAttention(nn.Module):
    def __init__(self, d_model: int, n_heads: int, mv_dim: int):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.mv_dim = mv_dim

        self.W_q = nn.Linear(d_model, d_model)
        self.W_k = nn.Linear(d_model, d_model)
        self.W_v = nn.Linear(d_model, d_model)
        self.W_out = nn.Linear(d_model, d_model)

        # Geometric product mixing: scalar + bivector weighting.
        self.scalar_weight = nn.Parameter(torch.tensor(0.6))
        self.bivector_weight = nn.Parameter(torch.tensor(0.4))

        self.scale = math.sqrt(self.head_dim)

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        B, T, D = x.shape

        Q = self.W_q(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        K = self.W_k(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        V = self.W_v(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)

        # Scalar attention (inner product / proximity). FP32 to avoid overflow under AMP.
        scalar_attn = torch.matmul(Q.float(), K.transpose(-2, -1).float()) / self.scale

        # Bivector attention: antisymmetric component captures orientational coupling.
        # Q∧K ≈ Q·Kᵀ - K·Qᵀ — magnitudes summed over keys give a per-row alignment score.
        bivector_attn = (scalar_attn - scalar_attn.transpose(-2, -1)) * 0.5
        bivector_magnitude = bivector_attn.abs().sum(dim=-1, keepdim=True)
        bivector_magnitude = bivector_magnitude.expand_as(scalar_attn)

        attn = self.scalar_weight * scalar_attn + self.bivector_weight * bivector_magnitude

        if mask is not None:
            attn = attn.masked_fill(mask == 0, float("-inf"))

        attn = F.softmax(attn, dim=-1).to(V.dtype)

        out = torch.matmul(attn, V)
        out = out.transpose(1, 2).contiguous().view(B, T, D)
        return self.W_out(out)
