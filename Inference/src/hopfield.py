"""Hopfield Associative Memory — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/hopfield.py.
No autograd. FP32 strict.

Two classes are ported:
  ModernHopfield         — standard dense associative memory (energy-based retrieval).
  SandboxHopfieldMemory  — C1-compatible memory with 256→512 projection pipeline
                           and cosine-similarity energy (used as default by engine.py).

Weight contract — ModernHopfield (when hv_dim != internal_dim):
  q_proj_weight: [internal_dim, hv_dim]  float32
  k_proj_weight: [internal_dim, hv_dim]  float32
  v_proj_weight: [internal_dim, hv_dim]  float32
  out_proj_weight: [hv_dim, internal_dim] float32

Weight contract — SandboxHopfieldMemory:
  query_lift_weight: [attractor_dim, query_dim]       float32
  query_lift_bias:   [attractor_dim]                  float32
  input_projection_weight: [pattern_projection_dim, attractor_dim]  float32
  input_projection_bias:   [pattern_projection_dim]   float32
  stored_patterns: [N, pattern_projection_dim]        float32  (optional — seeded separately)
"""
import numpy as np


class ModernHopfield:
    """Modern Hopfield Network (Dense Associative Memory).

    Energy-based retrieval:
        energy = −lse(β, sim) + ½‖q‖²
    Update rule (softmax attention):
        q ← softmax(β · q · Kᵀ) · V

    Args:
        hv_dim:             input state dimension.
        internal_dim:       Hopfield internal (hidden) dimension.
        beta:               inverse temperature.
        normalize_patterns: L2-normalize stored patterns.
        weights:            optional dict with projection weights.
    """

    def __init__(
        self,
        hv_dim: int = 32,
        internal_dim: int = 128,
        beta: float = 4.0,
        normalize_patterns: bool = True,
        weights: dict = None,
    ):
        self.hv_dim             = hv_dim
        self.internal_dim       = internal_dim
        self.beta               = beta
        self.normalize_patterns = normalize_patterns

        # Persistent pattern store — populated via store()
        self.stored_patterns = np.zeros((0, internal_dim), dtype=np.float32)

        if hv_dim != internal_dim:
            if weights is not None:
                def _w(k): return np.asarray(weights[k], dtype=np.float32)
                self.W_q   = _w("q_proj_weight")
                self.W_k   = _w("k_proj_weight")
                self.W_v   = _w("v_proj_weight")
                self.W_out = _w("out_proj_weight")
            else:
                rng = np.random.default_rng(6)
                scale = 1.0 / np.sqrt(hv_dim)
                self.W_q   = rng.standard_normal((internal_dim, hv_dim)).astype(np.float32) * scale
                self.W_k   = rng.standard_normal((internal_dim, hv_dim)).astype(np.float32) * scale
                self.W_v   = rng.standard_normal((internal_dim, hv_dim)).astype(np.float32) * scale
                self.W_out = rng.standard_normal((hv_dim, internal_dim)).astype(np.float32) * scale
            self._project_q   = lambda x: x @ self.W_q.T
            self._project_k   = lambda x: x @ self.W_k.T
            self._project_v   = lambda x: x @ self.W_v.T
            self._project_out = lambda x: x @ self.W_out.T
        else:
            # Identity projections
            self._project_q   = lambda x: x
            self._project_k   = lambda x: x
            self._project_v   = lambda x: x
            self._project_out = lambda x: x

    @staticmethod
    def _l2_normalize(x: np.ndarray, eps: float = 1e-8) -> np.ndarray:
        norm = np.linalg.norm(x, axis=-1, keepdims=True)
        return x / np.maximum(norm, eps)

    def store(self, patterns: np.ndarray) -> None:
        """Store patterns as attractors.

        Args:
            patterns: [N, hv_dim] float32
        """
        projected = self._project_k(np.asarray(patterns, dtype=np.float32))
        if self.normalize_patterns:
            projected = self._l2_normalize(projected)
        self.stored_patterns = projected

    def energy(self, query: np.ndarray) -> np.ndarray:
        """Compute energy of a query state — low = near an attractor.

        Args:
            query: [..., hv_dim]
        Returns:
            [...] scalar energy
        """
        query = np.asarray(query, dtype=np.float32)
        q = self._project_q(query)
        if self.normalize_patterns:
            q = self._l2_normalize(q)

        if self.stored_patterns.shape[0] == 0:
            return np.zeros(q.shape[:-1], dtype=np.float32)

        sim  = q @ self.stored_patterns.T       # [..., N]
        # Numerically stable log-sum-exp: lse = max + log(sum(exp(x - max)))
        sim_max = sim.max(axis=-1, keepdims=True)          # [..., 1]
        lse = sim_max.squeeze(-1) + np.log(
            np.sum(np.exp(np.clip(self.beta * (sim - sim_max), -80, 0)), axis=-1)
        ) / self.beta
        norm_term = 0.5 * np.sum(q ** 2, axis=-1)
        return -lse + norm_term

    def retrieve(self, query: np.ndarray, iterations: int = 1) -> np.ndarray:
        """Retrieve stored patterns via the modern Hopfield update rule.

        Args:
            query:      [..., hv_dim]
            iterations: number of update steps
        Returns:
            [..., hv_dim] retrieved state
        """
        query = np.asarray(query, dtype=np.float32)
        q = self._project_q(query)

        if self.stored_patterns.shape[0] == 0:
            return query

        for _ in range(iterations):
            sim  = q @ self.stored_patterns.T         # [..., N]
            sim_shifted = sim - sim.max(axis=-1, keepdims=True)
            attn = np.exp(self.beta * sim_shifted)
            attn /= attn.sum(axis=-1, keepdims=True)
            q    = attn @ self.stored_patterns        # [..., internal_dim]

        return self._project_out(q)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return self.retrieve(x)


class SandboxHopfieldMemory:
    """C1-compatible Modern Hopfield memory.

    Dimension flow:
        query [B, T, query_dim=128]
            ↓ query_lift   (Linear 128→256)
        q256  [B, T, 256]
            ↓ input_projection (Linear 256→512)
        q512  [B, T, 512]
            ↓ cosine similarity vs stored_patterns [N, 512]
        energy [B, T] in [0, 2]

    Stored patterns are L2-normalized 512-dim vectors.
    Energy = 1 − mean_cosine_sim → bounded in [0, 2].
    """

    def __init__(
        self,
        attractor_dim: int = 256,
        query_dim: int = 128,
        pattern_projection_dim: int = 512,
        beta: float = 4.0,
        weights: dict = None,
    ):
        self.attractor_dim          = attractor_dim
        self.query_dim              = query_dim
        self.pattern_projection_dim = pattern_projection_dim
        self.beta                   = beta

        # Persistent pattern store
        self.stored_patterns = np.zeros((0, pattern_projection_dim), dtype=np.float32)

        if weights is not None:
            def _w(k): return np.asarray(weights[k], dtype=np.float32)
            self.W_lift   = _w("query_lift_weight")
            self.b_lift   = _w("query_lift_bias")
            self.W_proj   = _w("input_projection_weight")
            self.b_proj   = _w("input_projection_bias")
        else:
            rng = np.random.default_rng(7)
            self.W_lift = rng.standard_normal((attractor_dim, query_dim)).astype(np.float32) * 0.02
            self.b_lift = np.zeros(attractor_dim, dtype=np.float32)
            self.W_proj = rng.standard_normal((pattern_projection_dim, attractor_dim)).astype(np.float32) * 0.02
            self.b_proj = np.zeros(pattern_projection_dim, dtype=np.float32)

        # Load stored patterns if provided
        if weights is not None and "stored_patterns" in weights:
            self.stored_patterns = np.asarray(weights["stored_patterns"], dtype=np.float32)

    @staticmethod
    def _l2_normalize(x: np.ndarray, eps: float = 1e-8) -> np.ndarray:
        norm = np.linalg.norm(x, axis=-1, keepdims=True)
        return x / np.maximum(norm, eps)

    def seed_from_redis(self, attractor_tensors: np.ndarray) -> None:
        """Inject raw 256-dim attractor patterns (pre-projection format).

        Args:
            attractor_tensors: [N, attractor_dim] — raw attractor vectors.
        """
        at = np.asarray(attractor_tensors, dtype=np.float32)
        if at.shape[-1] != self.attractor_dim:
            raise ValueError(
                f"Expected attractor dim {self.attractor_dim}, got {at.shape[-1]}. "
                f"For 512-dim post-projection tensors use seed_from_pretrained_projected()."
            )
        projected = at @ self.W_proj.T + self.b_proj   # [N, 512] — note: skip query_lift
        self.stored_patterns = self._l2_normalize(projected)

    def seed_from_pretrained_projected(self, patterns: np.ndarray) -> None:
        """Load already-projected, already-L2-normalized 512-dim patterns.

        Args:
            patterns: [N, pattern_projection_dim]
        """
        p = np.asarray(patterns, dtype=np.float32)
        if p.shape[-1] != self.pattern_projection_dim:
            raise ValueError(
                f"Expected pattern_projection_dim {self.pattern_projection_dim}, got {p.shape[-1]}."
            )
        self.stored_patterns = self._l2_normalize(p)

    def compute_energy(self, query: np.ndarray) -> np.ndarray:
        """Compute attractor-proximity energy.

        Args:
            query: [B, T, query_dim=128]
        Returns:
            [B, T] energy in [0, 2]. 0 = aligned, 2 = anti-aligned.
        """
        query = np.asarray(query, dtype=np.float32)

        if self.stored_patterns.shape[0] == 0:
            return np.zeros(query.shape[:-1], dtype=np.float32)

        # Lift 128 → 256 → 512
        q_lifted = query @ self.W_lift.T + self.b_lift    # [B, T, 256]
        q        = q_lifted @ self.W_proj.T + self.b_proj  # [B, T, 512]
        q        = self._l2_normalize(q)

        # Cosine similarity vs stored patterns
        sim      = q @ self.stored_patterns.T              # [B, T, N]
        mean_sim = sim.mean(axis=-1)                       # [B, T]
        return (1.0 - mean_sim).astype(np.float32)        # [B, T] in [0, 2]

    def __call__(self, query: np.ndarray) -> np.ndarray:
        return self.compute_energy(query)
