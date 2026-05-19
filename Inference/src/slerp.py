"""Spherical Linear Interpolation — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/slerp.py.
All torch operations replaced with NumPy equivalents.
FP32 strict. No autograd.

Note: expand_state_dim_slerp / salvage_and_expand_state_dict are utility
functions for weight transplanting (C1 → C2). They are included here for
archive completeness but are NOT called during live inference.
"""
import logging
import numpy as np

log = logging.getLogger("slerp")


def slerp(val: float, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """Spherical linear interpolation between two vectors on the unit sphere.

    Args:
        val:       interpolation parameter in [0, 1]. 0 → low, 1 → high.
        low, high: np.ndarray of matching shape (last dim is the spherical dim).

    Returns:
        np.ndarray — interpolated vector, same shape as inputs.

    Falls back to linear interpolation when sin(omega) is near zero
    (vectors nearly collinear) to avoid division-by-zero.
    """
    low  = np.asarray(low,  dtype=np.float32)
    high = np.asarray(high, dtype=np.float32)

    # Normalise onto unit sphere
    low_norm  = low  / np.linalg.norm(low,  axis=-1, keepdims=True).clip(1e-8)
    high_norm = high / np.linalg.norm(high, axis=-1, keepdims=True).clip(1e-8)

    dot = np.clip((low_norm * high_norm).sum(axis=-1), -1.0, 1.0)
    omega = np.arccos(dot)     # angle between vectors on the sphere
    so = np.sin(omega)         # sin of that angle

    # Where sin(omega) ≈ 0, vectors are nearly identical → linear fallback
    near_collinear = np.abs(so) < 1e-6   # shape [...] (no last dim)

    linear_interp = (1.0 - val) * low + val * high

    # Safe division: wherever collinear, denominator ≠ 0 (we pick 1.0)
    safe_so = np.where(near_collinear, 1.0, so)
    w_low   = (np.sin((1.0 - val) * omega) / safe_so)[..., np.newaxis]
    w_high  = (np.sin(val * omega)         / safe_so)[..., np.newaxis]
    slerp_interp = w_low * low + w_high * high

    # Broadcast mask to last dim for element-wise select
    mask = near_collinear[..., np.newaxis]
    return np.where(mask, linear_interp, slerp_interp)


def expand_state_dim_slerp(
    old_tensor: np.ndarray,
    new_state_dim: int,
    rng: np.random.Generator = None,
) -> np.ndarray:
    """Expand a Mamba A_log-shaped array's state dimension via SLERP.

    Pads C1's trained state (e.g. 16-D) into the first slots of the new array
    and fills the remainder by SLERP-interpolating between a random anchor and
    the last trained state vector. Preserves geometric manifold structure.

    Args:
        old_tensor:    np.ndarray [d_inner, old_state_dim] float32
        new_state_dim: target last-axis size (e.g. 256)
        rng:           optional np.random.Generator for reproducibility.

    Returns:
        np.ndarray [d_inner, new_state_dim] float32
    """
    old_tensor = np.asarray(old_tensor, dtype=np.float32)
    old_state_dim = old_tensor.shape[-1]

    if new_state_dim <= old_state_dim:
        return old_tensor[..., :new_state_dim]

    new_tensor = np.zeros(
        old_tensor.shape[:-1] + (new_state_dim,), dtype=np.float32
    )
    new_tensor[..., :old_state_dim] = old_tensor

    # Random anchor ↔ last trained state column
    if rng is None:
        rng = np.random.default_rng()
    anchor_low  = rng.standard_normal(old_tensor.shape[:-1]).astype(np.float32)
    anchor_high = old_tensor[..., -1]

    span = new_state_dim - old_state_dim
    for i in range(span):
        val = (i + 1) / (span + 1)    # never 0 or 1 — SLERP stays well-defined
        new_tensor[..., old_state_dim + i] = slerp(val, anchor_low, anchor_high)

    return new_tensor


def salvage_and_expand_state_dict(
    old_state_dict: dict,
    new_state_dict: dict,
    rng: np.random.Generator = None,
) -> dict:
    """Walk a state-dict pair, copy matching keys, SLERP-expand A_log keys.

    Parity with pytorch salvage_and_expand_state_dict().
    State-dicts here are {str: np.ndarray} rather than {str: torch.Tensor}.

    Returns:
        dict ready for manual weight loading into NumPy weight stores.
    """
    out = dict(new_state_dict)
    transplanted, expanded, skipped = 0, 0, 0

    for key, new_arr in new_state_dict.items():
        if key not in old_state_dict:
            skipped += 1
            continue

        old_arr = np.asarray(old_state_dict[key], dtype=np.float32)
        new_arr = np.asarray(new_arr, dtype=np.float32)

        if old_arr.shape == new_arr.shape:
            out[key] = old_arr
            transplanted += 1
        elif (
            "A_log" in key
            and old_arr.ndim == new_arr.ndim
            and old_arr.shape[:-1] == new_arr.shape[:-1]
            and new_arr.shape[-1] > old_arr.shape[-1]
        ):
            out[key] = expand_state_dim_slerp(old_arr, new_arr.shape[-1], rng=rng)
            expanded += 1
            log.info(
                "SLERP-expanded %s: %s → %s",
                key, old_arr.shape, out[key].shape,
            )
        else:
            skipped += 1
            log.debug(
                "Shape mismatch on %s: old %s vs new %s — keeping new init.",
                key, old_arr.shape, new_arr.shape,
            )

    log.info(
        "Salvage summary: %d transplanted, %d SLERP-expanded, %d skipped.",
        transplanted, expanded, skipped,
    )
    return out
