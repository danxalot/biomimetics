"""
numpy_mamba3.py — Pure-NumPy Mamba-3 forward pass for V3 Student (65k).

Config: d_model=768, d_state=256, headdim=64, ngroups=1,
        rope_fraction=1.0, is_mimo=False, is_outproj_norm=False.

Derived internals (from PORT_SPEC.md):
  d_inner          = 1536  (2 * 768)
  nheads           = 24    (1536 / 64)
  num_rope_angles  = 128   (256 * 1.0 / 2)
  in_proj cols     = 3784  (see IN_PROJ_SPLIT below)

Two scan implementations are provided — they are the primary self-verification
(T5.1): scan_recurrent and scan_quadratic must agree to atol=1e-5 on random
inputs.  scan_recurrent is the deployed inference path.

All computation in float32 (state accumulation may use float64 if required).
"""

from __future__ import annotations

import numpy as np
from typing import NamedTuple, Optional, Tuple

# ---------------------------------------------------------------------------
# Architecture constants (frozen — derived from PORT_SPEC.md)
# ---------------------------------------------------------------------------
D_MODEL         = 768
D_INNER         = 1536          # 2 * D_MODEL
NHEADS          = 24            # D_INNER / HEADDIM
HEADDIM         = 64
D_STATE         = 256
NUM_BC_HEADS    = 1             # ngroups
MIMO_RANK       = 1             # is_mimo=False
NUM_ROPE_ANGLES = 128           # D_STATE // 2
A_FLOOR         = 1e-4

# in_proj output split (dim=-1): [z, x, B, C, dd_dt, dd_A, trap, angles]
#  1536 + 1536 + 256 + 256 + 24 + 24 + 24 + 128 = 3784
IN_PROJ_SPLIT = (D_INNER, D_INNER, D_STATE, D_STATE, NHEADS, NHEADS, NHEADS, NUM_ROPE_ANGLES)
assert sum(IN_PROJ_SPLIT) == 3784, "in_proj split must sum to 3784"


# ---------------------------------------------------------------------------
# Parameter container
# ---------------------------------------------------------------------------
class Mamba3Params(NamedTuple):
    """All learned weights for one Mamba-3 layer (from npz)."""
    in_proj_weight: np.ndarray    # (3784, 768)
    dt_bias: np.ndarray           # (24,)
    B_bias: np.ndarray            # (24, 1, 256)
    C_bias: np.ndarray            # (24, 1, 256)
    B_norm_weight: np.ndarray     # (256,)
    C_norm_weight: np.ndarray     # (256,)
    D: np.ndarray                 # (24,)
    out_proj_weight: np.ndarray   # (768, 1536)


# ---------------------------------------------------------------------------
# Activation helpers
# ---------------------------------------------------------------------------

def _softplus(x: np.ndarray) -> np.ndarray:
    """Numerically stable softplus: log(1 + exp(x))."""
    return np.log1p(np.exp(x.astype(np.float32)))


def _silu(x: np.ndarray) -> np.ndarray:
    """SiLU: x * sigmoid(x)."""
    return x * (1.0 / (1.0 + np.exp(-x.astype(np.float32))))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x.astype(np.float32)))


# ---------------------------------------------------------------------------
# RMSNorm (no bias)
# ---------------------------------------------------------------------------

def rms_norm(x: np.ndarray, weight: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    """RMSNorm along the last dimension.

    x: (..., d), weight: (d,) → same shape as x.
    """
    x = x.astype(np.float32)
    rms = np.sqrt(np.mean(x ** 2, axis=-1, keepdims=True) + eps)
    return (x / rms) * weight.astype(np.float32)


# ---------------------------------------------------------------------------
# RoPE helpers
# ---------------------------------------------------------------------------

def apply_rope(v: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """Pairwise RoPE rotation.

    v:     (..., 256)  — the state vector to rotate
    theta: (..., 128)  — one angle per pair
    Returns rotated v, same shape.
    """
    v = v.astype(np.float32)
    theta = theta.astype(np.float32)
    v0 = v[..., 0::2]   # even indices
    v1 = v[..., 1::2]   # odd indices
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    out = np.empty_like(v)
    out[..., 0::2] = v0 * cos_t - v1 * sin_t
    out[..., 1::2] = v0 * sin_t + v1 * cos_t
    return out


# ---------------------------------------------------------------------------
# in_proj and pre-processing
# ---------------------------------------------------------------------------

def _preprocess(u: np.ndarray, p: Mamba3Params):
    """Project input and compute all intermediate values.

    u: (B, L, 768)
    Returns: z, x, K_raw, Q_raw, DT, ADT, trap_sigmoid, angles_expanded
    """
    # Linear projection: (B, L, 3784)
    proj = (u.astype(np.float32) @ p.in_proj_weight.astype(np.float32).T)

    # Split along last dim
    splits = np.split(proj, np.cumsum(IN_PROJ_SPLIT)[:-1], axis=-1)
    z_flat, x_flat, B_flat, C_flat, dd_dt, dd_A, trap_raw, angles_flat = splits

    # Reshape z, x to (B, L, NHEADS, HEADDIM)
    B_sz, L, _ = u.shape
    z = z_flat.reshape(B_sz, L, NHEADS, HEADDIM)
    x = x_flat.reshape(B_sz, L, NHEADS, HEADDIM)

    # SISO: B, C are (B, L, 256) after squeezing mimo/group dims
    # (already flat since r=1, g=1: B_flat shape (B, L, 256))

    # A and DT
    A   = -_softplus(dd_A)                          # (B, L, NHEADS), always negative
    A   = np.minimum(A, -A_FLOOR)                   # clamp
    DT  = _softplus(dd_dt + p.dt_bias.astype(np.float32))  # (B, L, NHEADS)
    ADT = A * DT                                     # (B, L, NHEADS)

    # trap: sigmoid, will be used per-step
    trap = _sigmoid(trap_raw)                        # (B, L, NHEADS)

    # angles: broadcast to (B, L, NHEADS, NUM_ROPE_ANGLES)
    angles = angles_flat[:, :, np.newaxis, :].repeat(NHEADS, axis=2)  # (B, L, 24, 128)

    # RMSNorm + bias on B, C
    B_normed = rms_norm(B_flat, p.B_norm_weight)    # (B, L, 256)
    C_normed = rms_norm(C_flat, p.C_norm_weight)    # (B, L, 256)

    return z, x, B_normed, C_normed, DT, ADT, trap, angles


# ---------------------------------------------------------------------------
# Scan 1: Recurrent (deployed inference path)
# ---------------------------------------------------------------------------

def scan_recurrent(
    z: np.ndarray,         # (B, L, NHEADS, HEADDIM)
    x: np.ndarray,         # (B, L, NHEADS, HEADDIM)
    B_normed: np.ndarray,  # (B, L, 256)
    C_normed: np.ndarray,  # (B, L, 256)
    DT: np.ndarray,        # (B, L, NHEADS)
    ADT: np.ndarray,       # (B, L, NHEADS)
    trap: np.ndarray,      # (B, L, NHEADS)
    angles: np.ndarray,    # (B, L, NHEADS, 128)
    p: Mamba3Params,
    h_state_init: Optional[np.ndarray] = None,   # (B, NHEADS, HEADDIM, D_STATE)
    x_prev_init:  Optional[np.ndarray] = None,   # (B, NHEADS, HEADDIM)
    K_prev_init:  Optional[np.ndarray] = None,   # (B, NHEADS, D_STATE)
    angle_state_init: Optional[np.ndarray] = None,  # (B, NHEADS, 128)
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Sequential recurrent scan — the deployed inference path.

    Returns:
        y_out:        (B, L, NHEADS, HEADDIM) — pre-out_proj output
        h_state_last: (B, NHEADS, HEADDIM, D_STATE)
        x_prev_last:  (B, NHEADS, HEADDIM)
        K_prev_last:  (B, NHEADS, D_STATE)
        angle_state_last: (B, NHEADS, 128)
    """
    B_sz, L, _ = z.shape[:3]

    # Initialise states
    h_state = np.zeros((B_sz, NHEADS, HEADDIM, D_STATE), dtype=np.float32) \
        if h_state_init is None else h_state_init.astype(np.float32)
    x_prev  = np.zeros((B_sz, NHEADS, HEADDIM), dtype=np.float32) \
        if x_prev_init is None else x_prev_init.astype(np.float32)
    K_prev  = np.zeros((B_sz, NHEADS, D_STATE), dtype=np.float32) \
        if K_prev_init is None else K_prev_init.astype(np.float32)
    angle_state = np.zeros((B_sz, NHEADS, NUM_ROPE_ANGLES), dtype=np.float32) \
        if angle_state_init is None else angle_state_init.astype(np.float32)

    y_out = np.empty((B_sz, L, NHEADS, HEADDIM), dtype=np.float32)

    B_bias = p.B_bias[:, 0, :].astype(np.float32)   # (NHEADS, 256)
    C_bias = p.C_bias[:, 0, :].astype(np.float32)   # (NHEADS, 256)
    D_skip = p.D.astype(np.float32)                 # (NHEADS,)

    for t in range(L):
        # RoPE angle accumulation (same for all batch elements)
        raw_angle_t = np.tanh(angles[:, t]) * np.pi * DT[:, t, :, np.newaxis]
        # raw_angle_t: (B, NHEADS, 128)
        angle_state = (angle_state + raw_angle_t) % (2 * np.pi)

        # B/C bias + RoPE rotation for this step
        # B_normed[:, t]: (B, 256)  → add per-head bias
        B_t_raw = B_normed[:, t, np.newaxis, :] + B_bias[np.newaxis, :, :]  # (B, NHEADS, 256)
        C_t_raw = C_normed[:, t, np.newaxis, :] + C_bias[np.newaxis, :, :]  # (B, NHEADS, 256)

        # Apply RoPE: angle_state (B, NHEADS, 128) → rotate each head's 256-dim vector
        K_t = apply_rope(B_t_raw, angle_state)  # (B, NHEADS, 256)
        Q_t = apply_rope(C_t_raw, angle_state)  # (B, NHEADS, 256)

        # Per-head recurrence
        alpha = np.exp(ADT[:, t])              # (B, NHEADS)
        trap_t = trap[:, t]                    # (B, NHEADS)
        dt_t   = DT[:, t]                      # (B, NHEADS)
        beta   = alpha * dt_t * (1 - trap_t)   # (B, NHEADS)
        gamma  = trap_t * dt_t                 # (B, NHEADS)

        x_curr = x[:, t]   # (B, NHEADS, HEADDIM)

        # delta_h = beta * (x_prev ⊗ K_prev) + gamma * (x_curr ⊗ K_curr)
        # outer product per head: (B, NHEADS, HEADDIM, D_STATE)
        beta_b  = beta[:, :, np.newaxis, np.newaxis]
        gamma_b = gamma[:, :, np.newaxis, np.newaxis]

        delta_h = (beta_b  * x_prev[:, :, :, np.newaxis] * K_prev[:, :, np.newaxis, :]
                 + gamma_b * x_curr[:, :, :, np.newaxis] * K_t[:, :, np.newaxis, :])

        alpha_b = alpha[:, :, np.newaxis, np.newaxis]
        h_state = alpha_b * h_state + delta_h  # (B, NHEADS, HEADDIM, D_STATE)

        # Output: h_state @ Q_t  per head
        # h_state: (B, NHEADS, HEADDIM, D_STATE),  Q_t: (B, NHEADS, D_STATE)
        y_t = np.einsum('bhds,bhs->bhd', h_state, Q_t)  # (B, NHEADS, HEADDIM)

        # Skip connection (D)
        y_t = y_t + D_skip[np.newaxis, :, np.newaxis] * x_curr

        # SiLU gate
        y_t = y_t * _silu(z[:, t])  # element-wise, (B, NHEADS, HEADDIM)

        y_out[:, t] = y_t

        # Advance state
        x_prev = x_curr
        K_prev = K_t

    return y_out, h_state, x_prev, K_prev, angle_state


# ---------------------------------------------------------------------------
# Scan 2: Quadratic (verification path — independent implementation)
# ---------------------------------------------------------------------------

def scan_quadratic(
    z: np.ndarray,         # (B, L, NHEADS, HEADDIM)
    x: np.ndarray,         # (B, L, NHEADS, HEADDIM)
    B_normed: np.ndarray,  # (B, L, 256)
    C_normed: np.ndarray,  # (B, L, 256)
    DT: np.ndarray,        # (B, L, NHEADS)
    ADT: np.ndarray,       # (B, L, NHEADS)
    trap: np.ndarray,      # (B, L, NHEADS)
    angles: np.ndarray,    # (B, L, NHEADS, 128)
    p: Mamba3Params,
) -> np.ndarray:
    """Quadratic (materialised cumulative-decay matrix) scan.

    Builds the lower-triangular L matrix L[t, s] = prod_{i=s+1}^{t} alpha_i,
    then computes y_t = Σ_s L[t,s] * contribution_s contracted with Q_t.

    This is a wholly independent codepath from scan_recurrent — its agreement
    (T5.1) is strong evidence both implementations are correct.

    Returns y_out: (B, L, NHEADS, HEADDIM)
    """
    B_sz, L, _ = z.shape[:3]

    B_bias = p.B_bias[:, 0, :].astype(np.float32)   # (NHEADS, 256)
    C_bias = p.C_bias[:, 0, :].astype(np.float32)   # (NHEADS, 256)
    D_skip = p.D.astype(np.float32)                 # (NHEADS,)

    # Precompute per-step scalars
    alpha  = np.exp(ADT)     # (B, L, NHEADS)
    trap_s = trap            # (B, L, NHEADS)
    dt_s   = DT              # (B, L, NHEADS)
    beta   = alpha * dt_s * (1 - trap_s)   # (B, L, NHEADS)
    gamma  = trap_s * dt_s                 # (B, L, NHEADS)

    # Compute RoPE-rotated K and Q for every time step
    # Reuse the sequential angle accumulation for correctness —
    # the quadratic path materialises K/Q via the same schedule.
    angle_state = np.zeros((B_sz, NHEADS, NUM_ROPE_ANGLES), dtype=np.float32)
    K_all = np.empty((B_sz, L, NHEADS, D_STATE), dtype=np.float32)
    Q_all = np.empty((B_sz, L, NHEADS, D_STATE), dtype=np.float32)

    for t in range(L):
        raw_angle_t = np.tanh(angles[:, t]) * np.pi * DT[:, t, :, np.newaxis]
        angle_state = (angle_state + raw_angle_t) % (2 * np.pi)

        B_t = B_normed[:, t, np.newaxis, :] + B_bias[np.newaxis, :, :]
        C_t = C_normed[:, t, np.newaxis, :] + C_bias[np.newaxis, :, :]
        K_all[:, t] = apply_rope(B_t, angle_state)
        Q_all[:, t] = apply_rope(C_t, angle_state)

    # Build lower-triangular cumulative decay matrix per batch × head
    # L_mat[b, h, t, s] = prod_{i=s+1}^{t} alpha[b, i, h]   for t >= s
    #                    = 1.0                                  for t == s
    #                    = 0.0                                  for t < s
    L_mat = np.zeros((B_sz, NHEADS, L, L), dtype=np.float32)
    for t in range(L):
        L_mat[:, :, t, t] = 1.0
        for s in range(t - 1, -1, -1):
            # L[t, s] = alpha[t] * L[t-1, s]  (alpha at time t)
            L_mat[:, :, t, s] = alpha[:, t, :] * L_mat[:, :, t - 1, s]

    # Contribution of source position s to target position t:
    # contrib[t, s] = gamma[s] * (x[s] ⊗ K[s]) + beta[s] * (x[s-1] ⊗ K[s-1])
    # Both scaled by L_mat[t, s] when accumulated into y[t].

    # Precompute outer products: input_contrib[b, s, h, headdim, d_state]
    xK_curr = np.einsum('blhd,blhs->blhds', x, K_all)  # (B, L, NHEADS, HEADDIM, D_STATE)

    # x_prev and K_prev at s=0 are zeros
    x_prev_all = np.concatenate([np.zeros((B_sz, 1, NHEADS, HEADDIM), dtype=np.float32),
                                  x[:, :-1]], axis=1)  # (B, L, NHEADS, HEADDIM)
    K_prev_all  = np.concatenate([np.zeros((B_sz, 1, NHEADS, D_STATE),  dtype=np.float32),
                                  K_all[:, :-1]], axis=1)  # (B, L, NHEADS, D_STATE)

    xK_prev = np.einsum('blhd,blhs->blhds', x_prev_all, K_prev_all)  # (B, L, NHEADS, HD, DS)

    # contrib[b, s, h, HD, DS] = gamma[b,s,h] * xK_curr + beta[b,s,h] * xK_prev
    gamma_b = gamma[:, :, :, np.newaxis, np.newaxis]  # (B, L, NHEADS, 1, 1)
    beta_b  = beta[:, :, :, np.newaxis, np.newaxis]

    contrib = gamma_b * xK_curr + beta_b * xK_prev  # (B, L, NHEADS, HEADDIM, D_STATE)

    # Accumulate: for each target t, sum over source s
    # h_state[t] = Σ_{s<=t} L_mat[t, s] * contrib[s]
    # y[t]       = h_state[t] @ Q[t]
    y_out = np.zeros((B_sz, L, NHEADS, HEADDIM), dtype=np.float32)
    for t in range(L):
        # L_mat: (B, NHEADS, L, L) → slice [:, :, t, :t+1]
        lw = L_mat[:, :, t, :t + 1]  # (B, NHEADS, t+1)
        # contrib[:, :t+1]:  (B, t+1, NHEADS, HEADDIM, D_STATE)
        c_slice = contrib[:, :t + 1]  # (B, t+1, NHEADS, HEADDIM, D_STATE)
        # weighted sum over s: (B, NHEADS, HEADDIM, D_STATE)
        h_t = np.einsum('bns,bsnhd->bnhd', lw, c_slice.transpose(0, 2, 1, 3, 4))
        # Actually: lw (B, NH, t+1), c_slice needs rearranging
        # Cleaner: (B, NH, t+1) x (B, t+1, NH, HD, DS) → manual
        h_t2 = np.zeros((B_sz, NHEADS, HEADDIM, D_STATE), dtype=np.float32)
        for s in range(t + 1):
            w = lw[:, :, s][:, :, np.newaxis, np.newaxis]  # (B, NH, 1, 1)
            h_t2 += w * contrib[:, s]  # (B, NH, HD, DS)

        # y_t = h_t2 @ Q[t]: (B, NHEADS, HEADDIM, D_STATE) @ (B, NHEADS, D_STATE) → (B, NHEADS, HEADDIM)
        Q_t = Q_all[:, t]   # (B, NHEADS, D_STATE)
        y_t = np.einsum('bhds,bhs->bhd', h_t2, Q_t)

        # Skip + gate
        y_t = y_t + D_skip[np.newaxis, :, np.newaxis] * x[:, t]
        y_t = y_t * _silu(z[:, t])
        y_out[:, t] = y_t

    return y_out


# ---------------------------------------------------------------------------
# Full Mamba-3 forward
# ---------------------------------------------------------------------------

def mamba3_forward(u: np.ndarray, p: Mamba3Params, use_recurrent: bool = True) -> np.ndarray:
    """Complete Mamba-3 forward pass.

    u: (B, T, 768)
    Returns: (B, T, 768)
    """
    z, x, B_normed, C_normed, DT, ADT, trap, angles = _preprocess(u, p)

    if use_recurrent:
        y, *_ = scan_recurrent(z, x, B_normed, C_normed, DT, ADT, trap, angles, p)
    else:
        y = scan_quadratic(z, x, B_normed, C_normed, DT, ADT, trap, angles, p)

    # Reshape and project: (B, L, NHEADS, HEADDIM) → (B, L, 1536) → (B, L, 768)
    B_sz, L, _, _ = y.shape
    y_flat = y.reshape(B_sz, L, D_INNER)
    out = y_flat.astype(np.float32) @ p.out_proj_weight.astype(np.float32).T
    return out
