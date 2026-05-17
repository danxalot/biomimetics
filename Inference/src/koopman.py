"""Koopman Operator — Extended Dynamic Mode Decomposition (EDMD).

PyTorch port of `services/neural_system/koopman_operator.py`.
Maps non-linear dynamics into a higher-dimensional linear observable space.

Key Features:
- Multiple lifting strategies (Polynomial, RBF, Random Fourier Features).
- Least-squares fitting of the linear transition operator K.
- Spectral decomposition (eigenvalues/modes) for stability analysis.
- Differentiable residual energy for use as a curiosity or manifold-loss term.
"""
import math
import torch
import torch.nn as nn
from typing import Optional, Tuple, List, Dict, Any


class KoopmanOperator(nn.Module):
    """
    Koopman Operator for learning and predicting high-dimensional dynamics.
    
    Args:
        state_dim: dimensionality of the raw state space (e.g., multivector dim 32).
        lifted_dim: target dimensionality of the observable space.
        lifting_type: 'polynomial', 'rbf', or 'random_fourier'.
    """

    def __init__(
        self,
        state_dim: int = 32,
        lifted_dim: int = 128,
        lifting_type: str = "polynomial",
        seed: int = 42,
    ):
        super().__init__()
        self.state_dim = state_dim
        self.lifted_dim = lifted_dim
        self.lifting_type = lifting_type
        self.seed = seed

        # Operator K: [lifted_dim, lifted_dim]
        self.register_buffer("K", torch.eye(lifted_dim))
        
        # State tracking
        self.register_buffer("fitted", torch.tensor(False))
        self.register_buffer("reconstruction_error", torch.tensor(1.0))

        # Initialization of lifting parameters
        torch.manual_seed(seed)
        if lifting_type == "rbf":
            self.register_buffer("rbf_centers", torch.randn(lifted_dim, state_dim))
            self.register_buffer("rbf_widths", torch.full((lifted_dim,), 0.5))
        elif lifting_type == "random_fourier":
            half_dim = max(1, (lifted_dim + 1) // 2)
            self.register_buffer("rff_weights", torch.randn(half_dim, state_dim))
            self.register_buffer("rff_bias", torch.rand(half_dim) * 2 * math.pi)
        elif lifting_type == "polynomial":
            # Polynomial schema is handled in the lift() method via fixed logic
            pass

    def lift(self, x: torch.Tensor) -> torch.Tensor:
        """Lift raw states into Koopman observable space."""
        # x: [..., state_dim]
        B = x.shape[:-1]
        x_flat = x.view(-1, self.state_dim)
        n_samples = x_flat.shape[0]

        if self.lifting_type == "rbf":
            # exp(-||x-c||² / (2σ²))
            dist_sq = torch.cdist(x_flat, self.rbf_centers).pow(2)
            denom = 2.0 * self.rbf_widths.pow(2)
            lifted = torch.exp(-dist_sq / denom)
        elif self.lifting_type == "random_fourier":
            # [cos(Wx+b), sin(Wx+b)]
            proj = torch.matmul(x_flat, self.rff_weights.t()) + self.rff_bias
            lifted = torch.cat([torch.cos(proj), torch.sin(proj)], dim=-1)
            lifted = lifted[..., :self.lifted_dim]
        else: # polynomial
            # [1, x, x^2, sin(x), cos(x)]
            features = [torch.ones(n_samples, 1, device=x.device)]
            features.append(x_flat)
            # Quadratic (limited to cross-terms if dim is high)
            if self.state_dim <= 16:
                for i in range(self.state_dim):
                    features.append(x_flat[:, i:i+1] * x_flat[:, i:])
            # Trig
            features.append(torch.sin(x_flat[:, :8]))
            features.append(torch.cos(x_flat[:, :8]))
            
            lifted = torch.cat(features, dim=-1)
            if lifted.shape[-1] > self.lifted_dim:
                lifted = lifted[:, :self.lifted_dim]
            elif lifted.shape[-1] < self.lifted_dim:
                padding = torch.zeros(n_samples, self.lifted_dim - lifted.shape[-1], device=x.device)
                lifted = torch.cat([lifted, padding], dim=-1)

        return lifted.view(*B, self.lifted_dim)

    def fit(self, trajectory: torch.Tensor, regularization: float = 1e-4):
        """Fit the Koopman operator K using least squares (EDMD)."""
        # trajectory: [Time, Dim]
        G = self.lift(trajectory)
        G_x = G[:-1]
        G_y = G[1:]

        # Solve G_x @ K.T = G_y  => K.T = (G_x.T @ G_x + reg*I)^-1 @ G_x.T @ G_y
        eye = torch.eye(self.lifted_dim, device=trajectory.device)
        A = torch.matmul(G_x.t(), G_x) + regularization * eye
        B = torch.matmul(G_x.t(), G_y)
        
        try:
            K_t = torch.linalg.solve(A, B)
            self.K = K_t.t()
            self.fitted = torch.tensor(True)
            
            # Compute reconstruction error
            G_y_pred = torch.matmul(G_x, self.K.t())
            self.reconstruction_error = F.mse_loss(G_y, G_y_pred)
        except RuntimeError:
            # Fallback to pseudo-inverse if singular
            K_t = torch.matmul(torch.linalg.pinv(A), B)
            self.K = K_t.t()
            self.fitted = torch.tensor(True)
            
        return self.reconstruction_error.item()

    def predict(self, x: torch.Tensor, steps: int = 1) -> torch.Tensor:
        """Predict future states by repeatedly applying K."""
        g = self.lift(x)
        preds = []
        for _ in range(steps):
            g = torch.matmul(g, self.K.t())
            # Reconstruct is hard for non-linear lifts, 
            # we typically just return the first state_dim slots as a linear approximation
            preds.append(g[..., :self.state_dim])
        return torch.stack(preds, dim=-2)

    def residual_energy(self, x_curr: torch.Tensor, x_next: torch.Tensor) -> torch.Tensor:
        """Differentiable residual energy for manifold regularisation."""
        g_curr = self.lift(x_curr)
        g_next = self.lift(x_next)
        g_pred = torch.matmul(g_curr, self.K.t())
        return F.mse_loss(g_pred, g_next)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Standard forward pass: lift and apply one step of K."""
        g = self.lift(x)
        g_next = torch.matmul(g, self.K.t())
        return g_next[..., :self.state_dim]
