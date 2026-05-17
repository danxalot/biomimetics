"""Kuramoto Oscillator Field — Neural Synchronization Dynamics.

PyTorch port of `services/neural_system/kuramoto_field.py`.
Implements synchronization of phase oscillators on a geometric manifold.

Dynamics:
dθ/dt = ω + K_bg3 * sin(φ_gold - θ_i) + Σ K_ij * sin(θ_j - θ_i)
"""
import math
import torch
import torch.nn as nn
from typing import Optional, Tuple

GOLDEN_RATIO = 1.61803398875

class KuramotoLayer(nn.Module):
    """
    Kuramoto oscillator layer for synchronizing neural states.
    
    Args:
        num_oscillators: Number of oscillators in the field.
        dt: Time step for integration.
        bg3_coupling: Strength of attraction to the Golden Ratio phase.
    """
    
    def __init__(
        self,
        num_oscillators: int = 128,
        dt: float = 0.01,
        bg3_coupling: float = 0.1
    ):
        super().__init__()
        self.num_oscillators = num_oscillators
        self.dt = dt
        self.bg3_coupling = bg3_coupling
        
        # Internal states
        self.register_buffer("phases", torch.rand(num_oscillators) * 2 * math.pi)
        self.register_buffer("natural_frequencies", torch.randn(num_oscillators) * 0.1 + 1.0)
        
        # Coupling matrix K_ij
        self.coupling_matrix = nn.Parameter(torch.ones(num_oscillators, num_oscillators) * 0.01)
        
        # BG3 Target (Golden Ratio phase)
        self.register_buffer("bg3_target", torch.tensor(GOLDEN_RATIO % (2 * math.pi)))

    def step(self, external_forcing: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        Advance one time step using Euler integration.
        
        Args:
            external_forcing: Optional [num_oscillators] tensor of external frequency offsets.
        """
        # Current phases: [N]
        theta = self.phases
        
        # 1. Internal Coupling: Σ K_ij * sin(θ_j - θ_i)
        # Difference matrix: [N, N]
        theta_diff = theta.unsqueeze(0) - theta.unsqueeze(1)
        coupling = torch.sum(self.coupling_matrix * torch.sin(theta_diff), dim=0)
        
        # 2. BG3 Force: K_bg3 * sin(φ_gold - θ_i)
        bg3_force = self.bg3_coupling * torch.sin(self.bg3_target - theta)
        
        # 3. Total dθ/dt
        d_theta = self.natural_frequencies + bg3_force + coupling
        if external_forcing is not None:
            d_theta = d_theta + external_forcing
            
        # Update phases
        self.phases = (theta + self.dt * d_theta) % (2 * math.pi)
        
        return self.phases

    def order_parameter(self) -> torch.Tensor:
        """
        Calculate global coherence r = |(1/N) * Σ e^(i*θ_j)|.
        r=1: perfect sync, r=0: chaos.
        """
        z = torch.exp(1j * self.phases)
        return torch.abs(torch.mean(z))

    def bg3_coherence(self) -> torch.Tensor:
        """Measure resonance with the Golden Ratio center."""
        # Mean exp(-|phase - target|)
        diff = torch.abs(self.phases - self.bg3_target)
        # Circular distance
        diff = torch.min(diff, 2 * math.pi - diff)
        return torch.mean(torch.exp(-diff))

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Integration step for training.
        Input x can be used as frequency modulation.
        Returns (new_phases, coherence).
        """
        new_phases = self.step(external_forcing=x)
        coherence = self.order_parameter()
        return new_phases, coherence
