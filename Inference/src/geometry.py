"""Cl(4,1) Conformal Geometric Algebra primitives — PyTorch.

Source-of-truth implementations of:
- conformal_lift   : R³ → 32D Cl(4,1) multivector
- normalize_rotor  : project onto Spin manifold (||R||=1)
- rotor_distance   : geodesic distance on Spin manifold
- cayley_map       : bivector → rotor (Lie algebra → Lie group), first-order

Originally extracted from `scripts/vultr_backup/scripts/train_script.py:147-222`.
NumPy mirror lives at `Gold_Standard_Archive/numpy/geometry.py`.
"""
import torch
from .config import CONFIG


def conformal_lift(points: torch.Tensor) -> torch.Tensor:
    """Lift R³ points into Cl(4,1) conformal space.

    The conformal model embeds Euclidean points as null vectors:
        X = x + 0.5*x²*e∞ + e₀
    with e₀ = 0.5*(e₄+e₅) and e∞ = e₅-e₄.

    Args:
        points: [..., 3] Euclidean coordinates.

    Returns:
        [..., 32] multivector components in Cl(4,1).
    """
    leading_shape = points.shape[:-1]
    mv = torch.zeros(*leading_shape, CONFIG["mv_dim"], device=points.device, dtype=points.dtype)

    x, y, z = points[..., 0], points[..., 1], points[..., 2]
    x_sq = x * x + y * y + z * z

    mv[..., 1] = x                # e1
    mv[..., 2] = y                # e2
    mv[..., 3] = z                # e3
    mv[..., 4] = 0.5 - 0.5 * x_sq # e4 (n_o)
    mv[..., 5] = 0.5 + 0.5 * x_sq # e5 (n_inf)
    return mv


def rotor_distance(r1: torch.Tensor, r2: torch.Tensor) -> torch.Tensor:
    """Geodesic distance between two rotors on the Spin manifold.
    d(R₁, R₂) = arccos(|⟨R₁, R̃₂⟩|).

    FP32 internally to prevent inner-product saturation in mixed precision.
    """
    r1_f32 = r1.float()
    r2_f32 = r2.float()
    inner = torch.sum(r1_f32 * r2_f32, dim=-1)
    inner = torch.clamp(inner.abs(), max=1.0 - 1e-6)
    return torch.acos(inner).mean().to(r1.dtype)


def normalize_rotor(r: torch.Tensor) -> torch.Tensor:
    """Project onto Spin manifold via L2 normalisation. Enforces ||R||=1."""
    r_f32 = r.float()
    norm = torch.norm(r_f32, dim=-1, keepdim=True).clamp(min=1e-8)
    return (r_f32 / norm).to(r.dtype)


def cayley_map(bivector: torch.Tensor) -> torch.Tensor:
    """First-order Cayley map: unconstrained bivector → unit rotor.

    R = (1 - B/2)^{-1} (1 + B/2) ≈ normalize(1 + B).
    """
    identity = torch.zeros_like(bivector)
    identity[..., 0] = 1.0
    rotor = identity + bivector
    return normalize_rotor(rotor)
