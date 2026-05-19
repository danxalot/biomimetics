"""Hamiltonian phase-space evolution — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/hamiltonian.py.

QAT / fake_quant_int8: STRIPPED — inference runtime is FP32 strict.
The symplectic Euler integrator uses clean FP32 arithmetic throughout.

Weight contract — per expert, indexed 0..n_experts-1:
  expert_{i}_potential_0_weight: [dim*2, dim]  float32
  expert_{i}_potential_0_bias:   [dim*2]       float32
  expert_{i}_potential_2_weight: [dim, dim*2]  float32
  expert_{i}_potential_2_bias:   [dim]         float32

Weight contract — SparseMixtureHamiltonianExperts (additional):
  gate_weight: [n_experts, dim]  float32
  gate_bias:   [n_experts]       float32
"""
import numpy as np
from .config import CONFIG


class HamiltonianExpert:
    """Single Hamiltonian expert — symplectic Euler (FP32 strict).

    dq/dt = ∂H/∂p   (approximated as potential(p))
    dp/dt = -∂H/∂q  (approximated as potential(new_q))

    QAT removed: the trained manifold is loaded as-is. FP32 inference
    is the specification.
    """

    def __init__(self, dim: int, weights: dict = None):
        self.dim = dim

        if weights is not None:
            def _w(k): return np.asarray(weights[k], dtype=np.float32)
            self.W0 = _w("potential_0_weight")   # [dim*2, dim]
            self.b0 = _w("potential_0_bias")
            self.W2 = _w("potential_2_weight")   # [dim, dim*2]
            self.b2 = _w("potential_2_bias")
        else:
            rng = np.random.default_rng(4)
            self.W0 = rng.standard_normal((dim * 2, dim)).astype(np.float32) * 0.02
            self.b0 = np.zeros(dim * 2, dtype=np.float32)
            self.W2 = rng.standard_normal((dim, dim * 2)).astype(np.float32) * 0.02
            self.b2 = np.zeros(dim, dtype=np.float32)

    @staticmethod
    def _silu(x: np.ndarray) -> np.ndarray:
        return x / (1.0 + np.exp(-x))

    def _potential(self, x: np.ndarray) -> np.ndarray:
        """V(x) — two-layer MLP with SiLU activation."""
        h = self._silu(x @ self.W0.T + self.b0)   # [..., dim*2]
        return h @ self.W2.T + self.b2              # [..., dim]

    def forward(self, q: np.ndarray, p: np.ndarray) -> tuple:
        """Symplectic Euler step.

        Args:
            q: [..., dim] position
            p: [..., dim] momentum
        Returns:
            (new_q, new_p) each [..., dim]
        """
        q = np.asarray(q, dtype=np.float32)
        p = np.asarray(p, dtype=np.float32)
        dt = CONFIG["symplectic_dt"]

        dq    = self._potential(p)
        new_q = q + dt * dq
        dp    = self._potential(new_q)
        new_p = p - dt * dp
        return new_q, new_p

    def potential(self, x: np.ndarray) -> np.ndarray:
        """Public accessor for potential evaluation (used by compute_hamiltonian)."""
        return self._potential(np.asarray(x, dtype=np.float32))

    def __call__(self, q: np.ndarray, p: np.ndarray) -> tuple:
        return self.forward(q, p)


class SparseMixtureHamiltonianExperts:
    """SMoE-HE: top-2 routing of (q, p) phase-space to local potential experts.

    Mirrors pytorch SparseMixtureHamiltonianExperts(nn.Module).
    Gate uses FP32 softmax to prevent underflow (matching AMP guard in pytorch).

    Args:
        dim:       half the phase-space dimension (q and p are each [dim]).
        n_experts: number of Hamiltonian experts.
        weights:   dict with gate + per-expert weights (see module docstring).
    """

    def __init__(self, dim: int, n_experts: int, weights: dict = None):
        self.dim       = dim
        self.n_experts = n_experts

        if weights is not None:
            self.experts = [
                HamiltonianExpert(
                    dim,
                    weights={
                        "potential_0_weight": weights[f"expert_{i}_potential_0_weight"],
                        "potential_0_bias":   weights[f"expert_{i}_potential_0_bias"],
                        "potential_2_weight": weights[f"expert_{i}_potential_2_weight"],
                        "potential_2_bias":   weights[f"expert_{i}_potential_2_bias"],
                    }
                )
                for i in range(n_experts)
            ]
            self.W_gate = np.asarray(weights["gate_weight"], dtype=np.float32)
            self.b_gate = np.asarray(weights["gate_bias"],   dtype=np.float32)
        else:
            self.experts = [HamiltonianExpert(dim) for _ in range(n_experts)]
            rng = np.random.default_rng(5)
            self.W_gate = rng.standard_normal((n_experts, dim)).astype(np.float32) * 0.02
            self.b_gate = np.zeros(n_experts, dtype=np.float32)

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        e = np.exp(x - x.max(axis=-1, keepdims=True))
        return e / e.sum(axis=-1, keepdims=True)

    def forward(self, q: np.ndarray, p: np.ndarray) -> tuple:
        """Top-2 routed symplectic Euler step.

        Args:
            q: [..., dim] float32
            p: [..., dim] float32
        Returns:
            (new_q, new_p) each [..., dim]
        """
        q = np.asarray(q, dtype=np.float32)
        p = np.asarray(p, dtype=np.float32)

        # Gate — FP32 softmax
        gate_logits  = q @ self.W_gate.T + self.b_gate   # [..., n_experts]
        gate_weights = self._softmax(gate_logits)          # [..., n_experts]

        # Top-2
        top2_idx = np.argsort(gate_weights, axis=-1)[..., -2:]   # [..., 2]
        top2_w   = np.take_along_axis(gate_weights, top2_idx, axis=-1)  # [..., 2]
        denom    = top2_w.sum(axis=-1, keepdims=True).clip(min=1e-6)
        top2_w   = top2_w / denom                                        # [..., 2] normalised

        new_q = np.zeros_like(q)
        new_p = np.zeros_like(p)

        for k in range(2):
            for e_idx, expert in enumerate(self.experts):
                mask = top2_idx[..., k] == e_idx        # [...] bool
                if mask.any():
                    weight = top2_w[..., k:k + 1]       # [..., 1]
                    eq, ep = expert(q, p)
                    new_q += weight * eq * mask[..., np.newaxis]
                    new_p += weight * ep * mask[..., np.newaxis]

        return new_q, new_p

    def compute_hamiltonian(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """H(q, p) = T(p) + V_avg(q) — for conservation monitoring.

        Returns [...] scalar Hamiltonian value.
        """
        q = np.asarray(q, dtype=np.float32)
        p = np.asarray(p, dtype=np.float32)

        kinetic   = 0.5 * (p ** 2).sum(axis=-1)          # [...]
        potential = np.zeros(q.shape[:-1], dtype=np.float32)
        for expert in self.experts:
            v = expert.potential(q)
            potential += 0.5 * (v ** 2).sum(axis=-1)
        potential /= self.n_experts
        return kinetic + potential

    def __call__(self, q: np.ndarray, p: np.ndarray) -> tuple:
        return self.forward(q, p)
