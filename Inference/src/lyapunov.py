"""Lyapunov Stability Analysis — Dynamic Convergence Control.

Implements stability loss functions for ensuring neural dynamics converge to 
target attractors and remain within stable regions of the manifold.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Callable


class LyapunovStability(nn.Module):
    """
    Evaluates and enforces Lyapunov stability: V(x) > 0 and V_dot(x) < 0.
    """
    
    def __init__(self, dim: int = 32, center: Optional[torch.Tensor] = None):
        super().__init__()
        self.dim = dim
        if center is not None:
            self.register_buffer("center", center)
        else:
            self.register_buffer("center", torch.zeros(dim))

    def candidate_v(self, x: torch.Tensor) -> torch.Tensor:
        """Quadratic Lyapunov candidate: V(x) = (x-c)^T P (x-c)."""
        diff = x - self.center
        return 0.5 * torch.sum(diff**2, dim=-1)

    def stability_loss(self, x_curr: torch.Tensor, x_next: torch.Tensor, alpha: float = 0.1) -> torch.Tensor:
        """
        Enforce V_dot < -alpha * V.
        This ensures exponential stability toward the center.
        """
        v_curr = self.candidate_v(x_curr)
        v_next = self.candidate_v(x_next)
        
        # V_dot = (V_next - V_curr) / dt (assuming dt=1)
        v_dot = v_next - v_curr
        
        # We want v_dot <= -alpha * v_curr
        # Loss is the violation of this condition
        violation = F.relu(v_dot + alpha * v_curr)
        return torch.mean(violation)

    def find_attractor(self, x: torch.Tensor, f: Callable, steps: int = 100) -> torch.Tensor:
        """Trace the trajectory under dynamics f to find the local attractor."""
        curr = x
        for _ in range(steps):
            curr = f(curr)
        return curr

    def forward(self, x_curr: torch.Tensor, x_next: torch.Tensor) -> torch.Tensor:
        """Return the stability violation loss."""
        return self.stability_loss(x_curr, x_next)
