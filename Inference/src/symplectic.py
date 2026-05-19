"""Symplectic Topology — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/symplectic.py.
Autograd (torch.enable_grad, torch.autograd.grad) replaced with finite-difference
gradient estimation — exact enough for inference-time Hamiltonian monitoring.
QAT: stripped. FP32 strict.
"""
import numpy as np
from typing import Callable, Tuple


class HamiltonianDynamics:
    """Manages Hamiltonian dynamics on a phase space (q, p).

    q: positions/states, p: momenta.
    Mirrors pytorch HamiltonianDynamics(nn.Module).

    Note on leapfrog_step:
        The pytorch implementation uses torch.autograd.grad to obtain ∇V(q).
        For inference-only NumPy we use a central finite-difference approximation:
            ∂V/∂q_i ≈ [V(q + ε·e_i) - V(q - ε·e_i)] / (2ε)
        This is exact for quadratic potentials and sufficiently accurate for
        inference-time trajectory monitoring. ε = 1e-4.
    """

    def __init__(self, dim: int = 16):
        self.dim = dim   # half of total phase-space dim

    def split_state(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Split a state vector into position q and momentum p."""
        return x[..., :self.dim], x[..., self.dim:]

    def merge_state(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """Merge q and p into a single state vector."""
        return np.concatenate([q, p], axis=-1)

    def compute_hamiltonian(
        self,
        q: np.ndarray,
        p: np.ndarray,
        potential_fn: Callable,
    ) -> np.ndarray:
        """H(q, p) = T(p) + V(q).

        Args:
            q:            [..., dim]
            p:            [..., dim]
            potential_fn: callable(q) → [...] scalar potential energy
        Returns:
            [...] Hamiltonian
        """
        kinetic   = 0.5 * np.sum(p ** 2, axis=-1)
        potential = potential_fn(q)
        return kinetic + potential

    def _grad_v_fd(self, q: np.ndarray, potential_fn: Callable, eps: float = 1e-4) -> np.ndarray:
        """Finite-difference gradient of potential_fn w.r.t. q.

        Args:
            q:            [..., dim] float32
            potential_fn: callable(q[..., dim]) → [...] scalar
        Returns:
            grad_v: [..., dim] float32
        """
        grad = np.zeros_like(q)
        for i in range(q.shape[-1]):
            q_plus  = q.copy(); q_plus[..., i]  += eps
            q_minus = q.copy(); q_minus[..., i] -= eps
            grad[..., i] = (potential_fn(q_plus) - potential_fn(q_minus)) / (2.0 * eps)
        return grad

    def leapfrog_step(
        self,
        q: np.ndarray,
        p: np.ndarray,
        potential_fn: Callable,
        dt: float = 0.01,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Symplectic Leapfrog (Störmer-Verlet) integration step.

        1. p(t + dt/2) = p(t) − (dt/2) · ∇V(q(t))
        2. q(t + dt)   = q(t) + dt · p(t + dt/2)
        3. p(t + dt)   = p(t + dt/2) − (dt/2) · ∇V(q(t + dt))
        """
        q = np.asarray(q, dtype=np.float32)
        p = np.asarray(p, dtype=np.float32)

        grad_v   = self._grad_v_fd(q, potential_fn)
        p_half   = p - (dt / 2.0) * grad_v
        q_next   = q + dt * p_half
        grad_v2  = self._grad_v_fd(q_next, potential_fn)
        p_next   = p_half - (dt / 2.0) * grad_v2
        return q_next, p_next

    def hamiltonian_conservation_loss(
        self,
        q1: np.ndarray,
        p1: np.ndarray,
        q2: np.ndarray,
        p2: np.ndarray,
        potential_fn: Callable,
    ) -> float:
        """Loss = mean |H(q1, p1) − H(q2, p2)|².

        Used for offline conservation diagnostics — not backpropagated.
        """
        h1 = self.compute_hamiltonian(q1, p1, potential_fn)
        h2 = self.compute_hamiltonian(q2, p2, potential_fn)
        return float(np.mean((h1 - h2) ** 2))

    def __call__(
        self,
        x: np.ndarray,
        potential_fn: Callable,
        dt: float = 0.01,
    ) -> np.ndarray:
        """Step the phase space forward using leapfrog integration."""
        q, p     = self.split_state(x)
        q_n, p_n = self.leapfrog_step(q, p, potential_fn, dt)
        return self.merge_state(q_n, p_n)
