"""
numpy_stack.py — VersorMemMambaStackNP: 32-layer NumPy V3 student stack.

Loads pythia_c3_v3_65k.npz and runs the full stack forward.

Per-layer forward (from PORT_SPEC.md §8):
    residual = x                                    # (B, T, 768)
    h = layer_norm(x, norm.weight, norm.bias)       # standard LayerNorm
    h = mamba3_forward(h)                           # (B, T, 768)
    x = residual + 0.125 * h                        # residual_scale = 1/sqrt(2*32)

Vestigial keys `layers.N.A_log` (12,) and `layers.N.dt_bias` (12,) are loaded
and silently ignored — they are entropy-probe params from the PyTorch block
wrapper, not part of the Mamba-3 kernel forward.

Key completeness: the loader asserts ALL 384 keys are consumed, zero missing,
zero leftover.  Any deviation raises immediately.
"""

from __future__ import annotations

import math
import numpy as np
from typing import Dict, Optional, Tuple

from .numpy_mamba3 import Mamba3Params, mamba3_forward, scan_recurrent, _preprocess

# ---------------------------------------------------------------------------
# Architecture constants
# ---------------------------------------------------------------------------
N_LAYERS        = 32
D_MODEL         = 768
RESIDUAL_SCALE  = 1.0 / math.sqrt(2.0 * N_LAYERS)   # = 0.125

# Keys per layer (12 total)
_LAYER_KEYS = {
    "norm.weight",
    "norm.bias",
    "A_log",           # vestigial (12,)
    "dt_bias",         # vestigial (12,)
    "mamba.in_proj.weight",
    "mamba.dt_bias",
    "mamba.B_bias",
    "mamba.C_bias",
    "mamba.B_norm.weight",
    "mamba.C_norm.weight",
    "mamba.D",
    "mamba.out_proj.weight",
}
assert len(_LAYER_KEYS) == 12, "Expected 12 keys per layer"
TOTAL_KEYS = N_LAYERS * 12   # 384


# ---------------------------------------------------------------------------
# LayerNorm (standard — with weight and bias)
# ---------------------------------------------------------------------------

def _layer_norm(x: np.ndarray, weight: np.ndarray, bias: np.ndarray,
                eps: float = 1e-5) -> np.ndarray:
    """Standard LayerNorm along the last dimension."""
    x = x.astype(np.float32)
    mean = x.mean(axis=-1, keepdims=True)
    var  = x.var(axis=-1, keepdims=True)
    xn   = (x - mean) / np.sqrt(var + eps)
    return xn * weight.astype(np.float32) + bias.astype(np.float32)


# ---------------------------------------------------------------------------
# Per-layer state container
# ---------------------------------------------------------------------------

class _LayerState:
    """Streaming state for one layer (O(1) per-step inference)."""
    def __init__(self):
        self.h_state   = None   # (B, 24, 64, 256)
        self.x_prev    = None   # (B, 24, 64)
        self.K_prev    = None   # (B, 24, 256)
        self.ang_state = None   # (B, 24, 128)

    def reset(self):
        self.h_state   = None
        self.x_prev    = None
        self.K_prev    = None
        self.ang_state = None


# ---------------------------------------------------------------------------
# Main stack class
# ---------------------------------------------------------------------------

class VersorMemMambaStackNP:
    """Pure-NumPy 32-layer VersorMemMamba V3 student stack.

    Usage
    -----
    from Inference.v3_student.loader import load_v3_student
    stack = load_v3_student("pythia_c3_v3_65k.npz")
    y = stack.forward(x)   # x: (B, T, 768) → (B, T, 768)
    """

    def __init__(
        self,
        norm_weights:  list,   # N_LAYERS × (768,)
        norm_biases:   list,   # N_LAYERS × (768,)
        mamba_params:  list,   # N_LAYERS × Mamba3Params
    ):
        assert len(norm_weights) == N_LAYERS
        assert len(norm_biases)  == N_LAYERS
        assert len(mamba_params) == N_LAYERS
        self._norm_w = norm_weights
        self._norm_b = norm_biases
        self._params = mamba_params
        self._is_ready = True
        self._states: Optional[list] = None   # list[_LayerState] — populated on step()

    # ------------------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        return self._is_ready

    # ------------------------------------------------------------------
    def forward(self, x: np.ndarray) -> np.ndarray:
        """Full-sequence forward pass.

        x: (B, T, 768) → (B, T, 768).
        """
        if x.ndim != 3 or x.shape[-1] != D_MODEL:
            raise ValueError(f"Expected (B, T, {D_MODEL}), got {x.shape}")
        x = x.astype(np.float32)
        for i in range(N_LAYERS):
            residual = x
            h = _layer_norm(x, self._norm_w[i], self._norm_b[i])
            h = mamba3_forward(h, self._params[i], use_recurrent=True)
            x = residual + RESIDUAL_SCALE * h
        return x

    # ------------------------------------------------------------------
    def step(self, x_t: np.ndarray) -> np.ndarray:
        """Single-step streaming inference (O(1) state update).

        x_t: (B, 768) → (B, 768)
        States are carried across calls. Call reset_state() to clear.
        """
        if self._states is None:
            self._states = [_LayerState() for _ in range(N_LAYERS)]

        x_t = x_t.astype(np.float32)
        if x_t.ndim == 2:
            x_t = x_t[:, np.newaxis, :]   # (B, 1, 768)

        B = x_t.shape[0]
        for i in range(N_LAYERS):
            st = self._states[i]
            residual = x_t
            h = _layer_norm(x_t, self._norm_w[i], self._norm_b[i])

            z, x_in, B_n, C_n, DT, ADT, trap, angles = _preprocess(h, self._params[i])
            y, h_state, x_prev, K_prev, ang = scan_recurrent(
                z, x_in, B_n, C_n, DT, ADT, trap, angles, self._params[i],
                h_state_init=st.h_state,
                x_prev_init=st.x_prev,
                K_prev_init=st.K_prev,
                angle_state_init=st.ang_state,
            )
            # out_proj
            from .numpy_mamba3 import D_INNER
            y_flat = y.reshape(B, 1, D_INNER)
            out = y_flat @ self._params[i].out_proj_weight.T   # (B, 1, 768)

            x_t = residual + RESIDUAL_SCALE * out

            # Persist state
            st.h_state   = h_state
            st.x_prev    = x_prev
            st.K_prev    = K_prev
            st.ang_state = ang

        return x_t.squeeze(1)   # (B, 768)

    # ------------------------------------------------------------------
    def reset_state(self):
        """Clear all per-layer streaming states."""
        if self._states is not None:
            for st in self._states:
                st.reset()

    # ------------------------------------------------------------------
    @classmethod
    def from_npz(cls, path: str) -> "VersorMemMambaStackNP":
        """Load from npz file. Hard-fails if key completeness is violated."""
        npz = np.load(path, allow_pickle=False)
        all_keys = set(npz.files)
        expected_count = TOTAL_KEYS
        if len(all_keys) != expected_count:
            raise ValueError(
                f"npz key count mismatch: expected {expected_count}, got {len(all_keys)}. "
                f"Check for missing or extra parameters."
            )

        norm_weights  = []
        norm_biases   = []
        mamba_params  = []
        consumed_keys = set()

        for n in range(N_LAYERS):
            prefix = f"layers.{n}"

            def _get(suffix: str) -> np.ndarray:
                k = f"{prefix}.{suffix}"
                if k not in npz:
                    raise KeyError(f"Missing npz key: '{k}'")
                consumed_keys.add(k)
                return npz[k]

            # LayerNorm
            norm_weights.append(_get("norm.weight"))
            norm_biases.append(_get("norm.bias"))

            # Vestigial — load to satisfy key-completeness, then discard
            _ = _get("A_log")
            _ = _get("dt_bias")

            # Mamba-3 kernel weights
            mp = Mamba3Params(
                in_proj_weight  = _get("mamba.in_proj.weight"),
                dt_bias         = _get("mamba.dt_bias"),
                B_bias          = _get("mamba.B_bias"),
                C_bias          = _get("mamba.C_bias"),
                B_norm_weight   = _get("mamba.B_norm.weight"),
                C_norm_weight   = _get("mamba.C_norm.weight"),
                D               = _get("mamba.D"),
                out_proj_weight = _get("mamba.out_proj.weight"),
            )
            mamba_params.append(mp)

        # Hard-fail on any unconsumed key
        leftover = all_keys - consumed_keys
        if leftover:
            raise ValueError(
                f"Unconsumed npz keys (schema mismatch): {sorted(leftover)}"
            )
        missing = consumed_keys - all_keys
        if missing:
            raise ValueError(f"Keys requested but not in npz: {sorted(missing)}")

        return cls(norm_weights, norm_biases, mamba_params)
