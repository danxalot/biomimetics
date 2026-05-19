"""NoteBlock — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/note_block.py.
Kanerva-style HDC memory pool: score → compress → pool → inject.
No autograd. FP32 strict.

Weight contract:
  importance_scorer_weight: [1, d_model] float32
  importance_scorer_bias:   [1]          float32
  compressor_weight:        [d_model, d_model] float32
  compressor_bias:          [d_model]    float32
"""
import math
import numpy as np
from .config import CONFIG


class NoteBlock:
    """Persistent memory pool with importance-based compression and injection.

    Mirrors pytorch NoteBlock(nn.Module). Intentionally gradient-free —
    the pool operates as a detached reservoir exactly as in the original.

    Args:
        d_model:   embedding dimension (must match backbone d_model).
        pool_size: maximum number of compressed states to retain (default 64).
        weights:   dict with keys documented in module docstring.
                   If None, random-init weights are used (for testing).
    """

    def __init__(self, d_model: int, pool_size: int = 64, weights: dict = None):
        self.d_model   = d_model
        self.pool_size = pool_size

        # Persistent state pool — circular buffer, zero-initialized
        self.state_pool = np.zeros((pool_size, d_model), dtype=np.float32)
        self.pool_ptr   = 0

        if weights is not None:
            self.W_scorer = np.asarray(weights["importance_scorer_weight"], dtype=np.float32)
            self.b_scorer = np.asarray(weights["importance_scorer_bias"],   dtype=np.float32)
            self.W_comp   = np.asarray(weights["compressor_weight"],        dtype=np.float32)
            self.b_comp   = np.asarray(weights["compressor_bias"],          dtype=np.float32)
        else:
            rng = np.random.default_rng(1)
            self.W_scorer = rng.standard_normal((1, d_model)).astype(np.float32) * 0.02
            self.b_scorer = np.zeros(1, dtype=np.float32)
            self.W_comp   = np.eye(d_model, dtype=np.float32)
            self.b_comp   = np.zeros(d_model, dtype=np.float32)

    @staticmethod
    def _sigmoid(x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-x))

    def score_importance(self, x: np.ndarray) -> np.ndarray:
        """Score each token's importance for memory persistence.

        Args:
            x: [B, T, d_model]
        Returns:
            [B, T] importance scores in (0, 1)
        """
        x = np.asarray(x, dtype=np.float32)
        # Linear: [B, T, 1]  →  sigmoid  →  squeeze
        logits = x @ self.W_scorer.T + self.b_scorer   # [B, T, 1]
        return self._sigmoid(logits).squeeze(-1)        # [B, T]

    def update_pool(self, x: np.ndarray, scores: np.ndarray) -> None:
        """Store high-importance tokens in the persistent state pool (detached).

        Args:
            x:      [B, T, d_model]
            scores: [B, T]  — from score_importance()
        """
        x      = np.asarray(x,      dtype=np.float32)
        scores = np.asarray(scores, dtype=np.float32)
        threshold = CONFIG["note_block_threshold"]

        for b in range(x.shape[0]):
            mask      = scores[b] > threshold          # [T] bool
            important = x[b][mask]                     # [K, d_model]
            if important.shape[0] > 0:
                compressed = important @ self.W_comp.T + self.b_comp   # [K, d_model]
                if compressed.shape[0] > 1:
                    compressed = compressed.max(axis=0, keepdims=True)  # [1, d_model]
                ptr = self.pool_ptr % self.pool_size
                self.state_pool[ptr] = compressed[0]  # detached — no gradient
                self.pool_ptr += 1

    def inject_memory(self, x: np.ndarray) -> np.ndarray:
        """Inject persistent memory via sparse cross-token attention.

        Args:
            x: [B, T, d_model]
        Returns:
            [B, T, d_model] — x + 0.1 * memory_injection
        """
        x = np.asarray(x, dtype=np.float32)
        active = min(self.pool_ptr, self.pool_size)
        if active == 0:
            return x

        # pool: [active, d_model]  →  [1, active, d_model] → [B, active, d_model]
        pool = self.state_pool[:active][np.newaxis, :, :]     # [1, active, d_model]
        pool = np.broadcast_to(pool, (x.shape[0], active, self.d_model))

        # Attention: [B, T, active]
        attn = np.matmul(x, pool.transpose(0, 2, 1)) / math.sqrt(self.d_model)
        attn = attn - attn.max(axis=-1, keepdims=True)
        attn = np.exp(attn)
        attn /= attn.sum(axis=-1, keepdims=True)

        memory_injection = np.matmul(attn, pool)   # [B, T, d_model]
        return x + 0.1 * memory_injection

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """For use as a drop-in: score → update_pool → return x unchanged."""
        scores = self.score_importance(x)
        self.update_pool(x, scores)
        return x
