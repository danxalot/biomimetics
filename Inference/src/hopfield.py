import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Union, Tuple

class ModernHopfield(nn.Module):
    """
    Modern Hopfield Network (Dense Associative Memory).
    
    Implements:
    - Energy-based retrieval (Lagrangian formulation)
    - Pattern storage as attractors
    - Attention-based update rule (softmax)
    - Projections for high-dimensional state mapping
    
    Based on: "Hopfield Networks is All You Need" (Ramsauer et al., 2020)
    """
    
    def __init__(
        self,
        hv_dim: int = 32,
        internal_dim: int = 128,
        beta: float = 4.0,
        normalize_patterns: bool = True
    ):
        super().__init__()
        self.hv_dim = hv_dim
        self.internal_dim = internal_dim
        self.beta = beta
        self.normalize_patterns = normalize_patterns
        
        # Projections to internal Hopfield space
        if hv_dim != internal_dim:
            self.q_proj = nn.Linear(hv_dim, internal_dim, bias=False)
            self.k_proj = nn.Linear(hv_dim, internal_dim, bias=False)
            self.v_proj = nn.Linear(hv_dim, internal_dim, bias=False)
            self.out_proj = nn.Linear(internal_dim, hv_dim, bias=False)
        else:
            self.q_proj = nn.Identity()
            self.k_proj = nn.Identity()
            self.v_proj = nn.Identity()
            self.out_proj = nn.Identity()

        # Persistent storage for patterns (keys/values in attention terms)
        self.register_buffer("stored_patterns", torch.zeros(0, internal_dim))

    def store(self, patterns: torch.Tensor):
        """Store patterns as attractors."""
        # patterns: [N, hv_dim]
        projected = self.k_proj(patterns)
        if self.normalize_patterns:
            projected = F.normalize(projected, p=2, dim=-1)
        self.stored_patterns = projected

    def energy(self, query: torch.Tensor) -> torch.Tensor:
        """
        Compute energy of a query state.
        Low energy indicates proximity to a stored attractor.
        """
        # query: [..., hv_dim]
        q = self.q_proj(query)
        if self.normalize_patterns:
            q = F.normalize(q, p=2, dim=-1)
            
        if self.stored_patterns.shape[0] == 0:
            return torch.zeros(q.shape[:-1], device=q.device)

        # similarities: [..., N]
        sim = torch.matmul(q, self.stored_patterns.t())
        
        # Energy = -lse(beta, sim) + 0.5 * ||q||^2
        lse = (1.0 / self.beta) * torch.logsumexp(self.beta * sim, dim=-1)
        norm_term = 0.5 * torch.sum(q**2, dim=-1)
        
        return -lse + norm_term

    def retrieve(self, query: torch.Tensor, iterations: int = 1) -> torch.Tensor:
        """Retrieve stored patterns via the modern Hopfield update rule."""
        # query: [..., hv_dim]
        q = self.q_proj(query)
        
        if self.stored_patterns.shape[0] == 0:
            return query

        for _ in range(iterations):
            # softmax(beta * Q * K^T) * V
            sim = torch.matmul(q, self.stored_patterns.t())
            attn = torch.softmax(self.beta * sim, dim=-1)
            q = torch.matmul(attn, self.stored_patterns)
            
        return self.out_proj(q)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass for training: return retrieval result."""
        return self.retrieve(x)


class SandboxHopfieldMemory(nn.Module):
    """C1-compatible Modern Hopfield memory.

    Mirrors the format used in C1's `phase_c1_ued_active_inference.py` and
    `launch_c2_unified.py` so the 1868 attractor patterns produced over 500K
    steps of C1 training can be loaded directly via `seed_from_redis()`.

    Dimension flow:
        query  [B, T, query_dim=128]   ← outputs["q"] from NoumenalEngine
            ↓ query_lift (Linear 128→256)
        q256   [B, T, attractor_dim=256]
            ↓ input_projection (Linear 256→512)
        q512   [B, T, pattern_projection_dim=512]
            ↓ similarity vs stored_patterns [N, 512]
        energy [B, T]

    The 1868 C1 attractors live in the user's Redis at 256 dim (raw attractor
    space). `seed_from_redis()` takes the raw 256-dim tensors, projects them
    to 512 dim via `input_projection`, and stores normalised. Patterns are
    NOT gradient-trained — only the projection layers are.
    """

    def __init__(
        self,
        attractor_dim: int = 256,
        query_dim: int = 128,
        pattern_projection_dim: int = 512,
        beta: float = 4.0,
    ):
        super().__init__()
        self.attractor_dim = attractor_dim
        self.query_dim = query_dim
        self.beta = beta
        self.pattern_projection_dim = pattern_projection_dim

        # Lift incoming q (128-dim phase-space coord) to attractor space (256-dim)
        self.query_lift = nn.Linear(query_dim, attractor_dim)
        # Project into Hopfield-internal storage space (512-dim)
        self.input_projection = nn.Linear(attractor_dim, pattern_projection_dim)

        # Stored attractor patterns — populated by seed_from_redis or
        # bootstrap. Persistent buffer so it round-trips through state_dict.
        self.register_buffer(
            "stored_patterns", torch.zeros(0, pattern_projection_dim)
        )

    def _load_from_state_dict(
        self, state_dict, prefix, local_metadata, strict,
        missing_keys, unexpected_keys, error_msgs,
    ):
        """Allow dynamic resizing of stored_patterns when loading checkpoints
        with a different attractor count than the freshly-built buffer.
        """
        key = prefix + "stored_patterns"
        if key in state_dict:
            src = state_dict[key]
            if self.stored_patterns.shape != src.shape:
                with torch.no_grad():
                    self.stored_patterns = torch.empty_like(src)
        super()._load_from_state_dict(
            state_dict, prefix, local_metadata, strict,
            missing_keys, unexpected_keys, error_msgs,
        )

    def seed_from_redis(self, attractor_tensors: torch.Tensor):
        """Inject raw 256-dim attractor patterns from Redis (or a saved tensor).

        Args:
            attractor_tensors: [N, 256] — raw attractor vectors. Will be
                projected to 512-dim internal storage via `input_projection`
                and then L2-normalised.

        Use this when you have raw Redis exports (pre-projection format).
        For already-projected [N, 512] L2-normalized tensors saved from a
        prior C2 run, use `seed_from_pretrained_projected` instead — it
        skips `input_projection` to preserve the original geometry.
        """
        if attractor_tensors.shape[-1] != self.attractor_dim:
            raise ValueError(
                f"Expected attractor dim {self.attractor_dim}, got "
                f"{attractor_tensors.shape[-1]}. Are these raw 256-dim Redis "
                f"vectors? For 512-dim post-projection tensors use "
                f"seed_from_pretrained_projected()."
            )
        with torch.no_grad():
            attractor_tensors = attractor_tensors.to(
                self.input_projection.weight.device,
                dtype=self.input_projection.weight.dtype,
            )
            projected = self.input_projection(attractor_tensors)
            projected = F.normalize(projected, p=2, dim=-1)
        # Replace the stored buffer outright — same device & dtype as projection.
        self.stored_patterns = projected

    def seed_from_pretrained_projected(self, patterns: torch.Tensor):
        """Load already-projected, already-L2-normalized 512-dim patterns.

        Args:
            patterns: [N, 512] — patterns from a prior trained checkpoint
                (e.g. `hopfield_patterns_c2_50k_standalone.pt`). Will be
                re-normalized defensively in case storage / dtype shift
                introduced any numerical drift.

        Use this when you have a tensor already in `stored_patterns` format.
        Skips `input_projection` to preserve the original geometry — the
        patterns occupy the SAME absolute positions in 512-dim space they
        had in the source run. Note: the query path still goes through this
        engine's (potentially differently-trained) `input_projection`, so
        initial query→pattern alignment depends on whether the projection
        layer's weights are themselves loaded from the source run.
        """
        if patterns.shape[-1] != self.pattern_projection_dim:
            raise ValueError(
                f"Expected pattern_projection_dim {self.pattern_projection_dim}, "
                f"got {patterns.shape[-1]}. For raw 256-dim Redis vectors use "
                f"seed_from_redis()."
            )
        with torch.no_grad():
            patterns = patterns.to(
                self.input_projection.weight.device,
                dtype=self.input_projection.weight.dtype,
            )
            patterns = F.normalize(patterns, p=2, dim=-1)
        self.stored_patterns = patterns

    def compute_energy(self, query: torch.Tensor) -> torch.Tensor:
        """Compute attractor-proximity energy for the query stream.

        Args:
            query: [B, T, 128] — outputs["q"] from NoumenalEngine
        Returns:
            [B, T] energy (1 - mean cosine similarity to stored patterns).
            Bounded in [0, 2] — 0 = perfect alignment with attractors, 2 = anti-aligned.
        """
        if self.stored_patterns.size(0) == 0:
            return torch.zeros(query.shape[:-1], device=query.device, dtype=query.dtype)

        # Lift 128 → 256 → 512
        q_lifted = self.query_lift(query)
        q = self.input_projection(q_lifted)
        q = F.normalize(q, p=2, dim=-1)

        # Similarity vs stored patterns — fully FP32 to avoid logsumexp NaN under AMP
        q_f32 = q.float()
        patterns_f32 = self.stored_patterns.float()
        sim = torch.matmul(q_f32, patterns_f32.t())          # [B, T, N]
        mean_sim = sim.mean(dim=-1)                           # [B, T] in [-1, 1]
        return (1.0 - mean_sim).to(query.dtype)               # [B, T] in [0, 2]

    def forward(self, query: torch.Tensor) -> torch.Tensor:
        return self.compute_energy(query)
