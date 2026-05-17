"""Hamiltonian phase-space evolution — Akasha 2.

- HamiltonianExpert            : single expert parameterising a local potential
                                  manifold; symplectic-Euler integration step.
- SparseMixtureHamiltonianExperts : top-2 expert routing via gating network;
                                  conserves H = T + V across rollouts.

Originally from `train_script.py:453-540`. The QAT (`fake_quant_int8`) integration
is wired here — the integrator goes through the int8 saturation pipe during
training so that on-device runtime (which is FP32) sees a quantization-robust
manifold.
"""
from typing import Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import CONFIG
from .quant import fake_quant_int8


class HamiltonianExpert(nn.Module):
    """Single Hamiltonian expert — symplectic Euler with QAT clamping."""

    def __init__(self, dim: int):
        super().__init__()
        self.potential = nn.Sequential(
            nn.Linear(dim, dim * 2),
            nn.SiLU(),
            nn.Linear(dim * 2, dim),
        )

    def forward(self, q: torch.Tensor, p: torch.Tensor, step: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """Symplectic Euler.
            dq/dt = ∂H/∂p,   dp/dt = -∂H/∂q
        QAT applied to all intermediates so the int8-rounded manifold is what trains.
        """
        dt = CONFIG["symplectic_dt"]
        q_q = fake_quant_int8(q, step)
        p_q = fake_quant_int8(p, step)
        dq = fake_quant_int8(self.potential(p_q), step)
        new_q = q + dt * dq
        dp = fake_quant_int8(self.potential(new_q), step)
        new_p = p - dt * dp
        return new_q, new_p


class SparseMixtureHamiltonianExperts(nn.Module):
    """SMoE-HE: top-2 routing of (q, p) phase-space to local potential experts."""

    def __init__(self, dim: int, n_experts: int):
        super().__init__()
        self.experts = nn.ModuleList([HamiltonianExpert(dim) for _ in range(n_experts)])
        self.gate = nn.Linear(dim, n_experts)
        self.n_experts = n_experts

    def forward(self, q: torch.Tensor, p: torch.Tensor, step: int) -> Tuple[torch.Tensor, torch.Tensor]:
        # FP32 gate to prevent softmax underflow under AMP.
        gate_logits = self.gate(q).float()
        gate_weights = F.softmax(gate_logits, dim=-1)

        topk_weights, topk_indices = gate_weights.topk(2, dim=-1)
        denominator = topk_weights.sum(dim=-1, keepdim=True).clamp(min=1e-6)
        topk_weights = (topk_weights / denominator).to(q.dtype)

        new_q = torch.zeros_like(q)
        new_p = torch.zeros_like(p)

        for k in range(2):
            for e_idx in range(self.n_experts):
                mask = topk_indices[..., k] == e_idx
                if mask.any():
                    weight = topk_weights[..., k:k + 1]
                    eq, ep = self.experts[e_idx](q, p, step)
                    new_q += weight * eq * mask.unsqueeze(-1).float()
                    new_p += weight * ep * mask.unsqueeze(-1).float()
        return new_q, new_p

    def compute_hamiltonian(self, q: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
        """H(q, p) = T(p) + V_avg(q) — for conservation monitoring across rollouts."""
        p_f32 = p.float()
        kinetic = 0.5 * (p_f32 ** 2).sum(dim=-1)
        potential = torch.zeros_like(kinetic)
        for expert in self.experts:
            v = expert.potential(q).float()
            potential += 0.5 * (v ** 2).sum(dim=-1)
        potential /= self.n_experts
        return (kinetic + potential).to(q.dtype)
