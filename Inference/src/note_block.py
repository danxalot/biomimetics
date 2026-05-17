"""MemMamba-3 NoteBlock — horizontal memory fidelity preservation.

When ETMF (effective token-importance) drops below threshold τ, salient
geometric laws are compressed and stored in a persistent state pool, then
re-injected via sparse cross-token attention every `cross_layer_interval`
layers.

The compressor/scorer use intentionally-detached gradients — NoteBlock
operates as a Kanerva-style HDC random projection reservoir. Removing the
detach would require TBPTT across batches which is impractical for long
training runs.

Originally from `train_script.py:350-407`.
"""
import math

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import CONFIG


class NoteBlock(nn.Module):
    def __init__(self, d_model: int, pool_size: int = 64):
        super().__init__()
        self.d_model = d_model
        self.pool_size = pool_size
        self.importance_scorer = nn.Linear(d_model, 1)
        self.compressor = nn.Linear(d_model, d_model)
        self.register_buffer("state_pool", torch.zeros(pool_size, d_model))
        self.register_buffer("pool_ptr", torch.tensor(0, dtype=torch.long))

    def score_importance(self, x: torch.Tensor) -> torch.Tensor:
        """Score each token's importance for memory persistence ([B, T])."""
        return torch.sigmoid(self.importance_scorer(x)).squeeze(-1)

    def update_pool(self, x: torch.Tensor, scores: torch.Tensor) -> None:
        """Store high-importance tokens in the persistent state pool."""
        threshold = CONFIG["note_block_threshold"]
        mask = scores > threshold

        for b in range(x.shape[0]):
            important = x[b][mask[b]]
            if important.shape[0] > 0:
                compressed = self.compressor(important)
                if compressed.shape[0] > 1:
                    compressed = compressed.max(dim=0, keepdim=True)[0]
                ptr = self.pool_ptr.item() % self.pool_size
                # INTENTIONAL .detach() — see module docstring.
                self.state_pool[ptr] = compressed.squeeze(0).detach()
                self.pool_ptr += 1

    def inject_memory(self, x: torch.Tensor) -> torch.Tensor:
        """Inject persistent memory via sparse cross-token attention."""
        active = min(self.pool_ptr.item(), self.pool_size)
        if active == 0:
            return x

        pool = self.state_pool[:active].unsqueeze(0).expand(x.shape[0], -1, -1)
        attn = torch.matmul(x, pool.transpose(-2, -1))
        attn = F.softmax(attn / math.sqrt(self.d_model), dim=-1)
        memory_injection = torch.matmul(attn, pool)
        return x + 0.1 * memory_injection
