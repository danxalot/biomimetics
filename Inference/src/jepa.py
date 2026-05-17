"""JEPA (Joint-Embedding Predictive Architecture) — Latent World Modeling.

Implements the JEPA paradigm for learning representations by predicting 
latent outcomes of actions or temporal steps.
"""
import copy
import torch
import torch.nn as nn
import torch.nn.functional as F


class JEPA(nn.Module):
    """
    Joint-Embedding Predictive Architecture.
    
    Predicts the embedding of 'next_state' from the embedding of 'curr_state' 
    given an 'action' or 'delta'.
    """
    
    def __init__(self, state_dim: int = 32, latent_dim: int = 128, action_dim: int = 8):
        super().__init__()
        
        # Context Encoder (Online)
        self.encoder = nn.Sequential(
            nn.Linear(state_dim, latent_dim),
            nn.LayerNorm(latent_dim),
            nn.SiLU(),
            nn.Linear(latent_dim, latent_dim)
        )
        
        # Predictor
        self.predictor = nn.Sequential(
            nn.Linear(latent_dim + action_dim, latent_dim),
            nn.SiLU(),
            nn.Linear(latent_dim, latent_dim)
        )
        
        # Target Encoder (EMA)
        self.target_encoder = copy.deepcopy(self.encoder)
        for param in self.target_encoder.parameters():
            param.requires_grad = False
            
        self.ema_decay = 0.99

    @torch.no_grad()
    def update_target(self):
        """Update the target encoder using Exponential Moving Average."""
        for p, pt in zip(self.encoder.parameters(), self.target_encoder.parameters()):
            pt.data.mul_(self.ema_decay).add_(p.data, alpha=1 - self.ema_decay)

    def forward(self, x_curr: torch.Tensor, x_next: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        """
        Compute JEPA loss.
        L = || Predictor(Encoder(x_curr), action) - TargetEncoder(x_next) ||^2
        """
        # 1. Encode context
        z_curr = self.encoder(x_curr)
        
        # 2. Predict next latent
        z_pred = self.predictor(torch.cat([z_curr, action], dim=-1))
        
        # 3. Get target latent (from EMA encoder)
        with torch.no_grad():
            z_target = self.target_encoder(x_next)
            
        # 4. MSE Loss in latent space
        loss = F.mse_loss(z_pred, z_target)
        
        return loss

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Return the stable target representation."""
        return self.target_encoder(x)
