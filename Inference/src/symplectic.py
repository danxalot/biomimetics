"""Symplectic Topology — Hamiltonian Neural Dynamics.

Implements phase-space preserving integrators and Hamiltonian losses 
to ensure conservation of energy/momentum in neural state transitions.
"""
import torch
import torch.nn as nn
from typing import Tuple, Callable


class HamiltonianDynamics(nn.Module):
    """
    Manages Hamiltonian dynamics on a phase space (q, p).
    q: positions/states, p: momenta.
    """
    
    def __init__(self, dim: int = 16):
        super().__init__()
        self.dim = dim # Half of total phase space dim

    def split_state(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Split a state vector into position q and momentum p."""
        return x[..., :self.dim], x[..., self.dim:]

    def merge_state(self, q: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
        """Merge q and p into a single state vector."""
        return torch.cat([q, p], dim=-1)

    def compute_hamiltonian(self, q: torch.Tensor, p: torch.Tensor, potential_fn: Callable) -> torch.Tensor:
        """H(q, p) = T(p) + V(q)."""
        kinetic = 0.5 * torch.sum(p**2, dim=-1) # T = p^2/2m
        potential = potential_fn(q) # V(q)
        return kinetic + potential

    def leapfrog_step(self, q: torch.Tensor, p: torch.Tensor, potential_fn: Callable, dt: float = 0.01) -> Tuple[torch.Tensor, torch.Tensor]:
        """Symplectic Leapfrog (Verlet) integration step."""
        # 1. p(t + dt/2) = p(t) - (dt/2) * ∇V(q(t))
        with torch.enable_grad():
            q_in = q.detach().requires_grad_(True)
            v = potential_fn(q_in)
            grad_v = torch.autograd.grad(v.sum(), q_in)[0]
            
        p_half = p - (dt / 2.0) * grad_v
        
        # 2. q(t + dt) = q(t) + dt * p(t + dt/2)
        q_next = q + dt * p_half
        
        # 3. p(t + dt) = p(t + dt/2) - (dt/2) * ∇V(q(t + dt))
        with torch.enable_grad():
            q_next_in = q_next.detach().requires_grad_(True)
            v_next = potential_fn(q_next_in)
            grad_v_next = torch.autograd.grad(v_next.sum(), q_next_in)[0]
            
        p_next = p_half - (dt / 2.0) * grad_v_next
        
        return q_next, p_next

    def hamiltonian_conservation_loss(self, q1: torch.Tensor, p1: torch.Tensor, 
                                    q2: torch.Tensor, p2: torch.Tensor, 
                                    potential_fn: Callable) -> torch.Tensor:
        """Loss = |H(q1, p1) - H(q2, p2)|^2."""
        h1 = self.compute_hamiltonian(q1, p1, potential_fn)
        h2 = self.compute_hamiltonian(q2, p2, potential_fn)
        return torch.mean((h1 - h2)**2)

    def forward(self, x: torch.Tensor, potential_fn: Callable, dt: float = 0.01) -> torch.Tensor:
        """Step the phase space forward using leapfrog integration."""
        q, p = self.split_state(x)
        q_n, p_n = self.leapfrog_step(q, p, potential_fn, dt)
        return self.merge_state(q_n, p_n)
