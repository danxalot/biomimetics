"""Spherical Linear Interpolation + state-dim expansion utilities.

Used to transplant C1 (16-dim Mamba state) weights into C2 (128-dim) by
populating the new state dimensions with SLERP-interpolated vectors that
preserve geometric manifold structure rather than zero-padding.

Originally from `Gold_Standard_Archive/C2/master_c2_kinematics.py:109-122`
plus the `salvage_and_expand_weights` flow at lines 356-393.

Training-only — runtime never expands weights.
"""
import torch


def slerp(val: float, low: torch.Tensor, high: torch.Tensor) -> torch.Tensor:
    """Spherical linear interpolation between two vectors on the unit sphere.

    Args:
        val: interpolation parameter in [0, 1]. 0 → low, 1 → high.
        low, high: vectors of matching shape (last dim is the spherical dim).

    Returns:
        Interpolated vector of the same shape as inputs.

    Falls back to linear interpolation when sin(omega) is near zero
    (i.e. when low and high are nearly identical), avoiding division by zero.
    """
    low_norm = low / torch.norm(low, dim=-1, keepdim=True).clamp(min=1e-8)
    high_norm = high / torch.norm(high, dim=-1, keepdim=True).clamp(min=1e-8)
    omega = torch.acos((low_norm * high_norm).sum(dim=-1).clamp(-1, 1))
    so = torch.sin(omega)

    mask = (so.abs() < 1e-6).unsqueeze(-1)
    linear_interp = (1.0 - val) * low + val * high
    slerp_interp = (
        (torch.sin((1.0 - val) * omega) / so).unsqueeze(-1) * low
        + (torch.sin(val * omega) / so).unsqueeze(-1) * high
    )
    return torch.where(mask, linear_interp, slerp_interp)


def expand_state_dim_slerp(
    old_tensor: torch.Tensor, new_state_dim: int
) -> torch.Tensor:
    """Expand a Mamba A_log-shaped tensor's state dimension via SLERP.

    Pads C1's trained state (e.g. 16-D) into the first slots of the new tensor
    and fills the remainder by SLERP-interpolating between random init and the
    last trained state vector. Preserves the geometric manifold the C1 weights
    learned rather than abruptly zero-padding.

    Args:
        old_tensor: shape [d_inner, old_state_dim] (e.g. [d_inner, 16])
        new_state_dim: target last-axis size (e.g. 128)

    Returns:
        new_tensor: shape [d_inner, new_state_dim] with C1 weights at [:, :old_state_dim]
                    and SLERP-interpolated extension at [:, old_state_dim:].
    """
    old_state_dim = old_tensor.shape[-1]
    if new_state_dim <= old_state_dim:
        return old_tensor[..., :new_state_dim]

    new_tensor = torch.zeros(
        *old_tensor.shape[:-1], new_state_dim,
        device=old_tensor.device, dtype=old_tensor.dtype,
    )
    new_tensor[..., :old_state_dim] = old_tensor

    # Extend via SLERP from random-init to the LAST trained state column.
    anchor_low = torch.randn_like(old_tensor[..., 0])
    anchor_high = old_tensor[..., -1]
    span = new_state_dim - old_state_dim
    for i in range(span):
        val = (i + 1) / (span + 1)        # never 0 or 1, so SLERP is well-defined
        new_tensor[..., old_state_dim + i] = slerp(val, anchor_low, anchor_high)
    return new_tensor


def salvage_and_expand_state_dict(
    old_state_dict: dict, new_state_dict: dict
) -> dict:
    """Walk a state-dict pair, copy matching keys, SLERP-expand A_log keys.

    Returns a state-dict ready for `model.load_state_dict(...)`.
    Logs (via standard logging) which keys were transplanted, expanded, or skipped.
    """
    import logging
    log = logging.getLogger("slerp")
    out = dict(new_state_dict)  # start from the new model's shape contract
    transplanted, expanded, skipped = 0, 0, 0

    for key, new_tensor in new_state_dict.items():
        if key not in old_state_dict:
            skipped += 1
            continue
        old_tensor = old_state_dict[key]
        if old_tensor.shape == new_tensor.shape:
            out[key] = old_tensor
            transplanted += 1
        elif (
            "A_log" in key
            and old_tensor.dim() == new_tensor.dim()
            and old_tensor.shape[:-1] == new_tensor.shape[:-1]
            and new_tensor.shape[-1] > old_tensor.shape[-1]
        ):
            out[key] = expand_state_dim_slerp(old_tensor, new_tensor.shape[-1])
            expanded += 1
            log.info(
                f"SLERP-expanded {key}: {tuple(old_tensor.shape)} → {tuple(out[key].shape)}"
            )
        else:
            skipped += 1
            log.debug(
                f"Shape mismatch on {key}: old {tuple(old_tensor.shape)} vs "
                f"new {tuple(new_tensor.shape)} — keeping new init."
            )

    log.info(
        f"Salvage summary: {transplanted} transplanted, {expanded} SLERP-expanded, "
        f"{skipped} skipped."
    )
    return out
