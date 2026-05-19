"""Cl(4,1) Conformal Geometric Algebra primitives — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/geometry.py.
All torch.Tensor operations replaced with np.ndarray equivalents.
FP32 strict. No quantization.

Functions:
  conformal_lift   : R³ → 32D Cl(4,1) multivector
  normalize_rotor  : project onto Spin manifold (||R||=1)
  rotor_distance   : geodesic distance on Spin manifold
  cayley_map       : bivector → rotor (Lie algebra → Lie group), first-order
"""
import numpy as np
from .config import CONFIG


def conformal_lift(points: np.ndarray) -> np.ndarray:
    """Lift R³ points into Cl(4,1) conformal space.

    The conformal model embeds Euclidean points as null vectors:
        X = x + 0.5*|x|²*e∞ + e₀
    with e₀ = 0.5*(e₄+e₅) and e∞ = e₅-e₄.

    Args:
        points: np.ndarray [..., 3] float32  — Euclidean coordinates.

    Returns:
        np.ndarray [..., 32] float32  — multivector components in Cl(4,1).
    """
    points = np.asarray(points, dtype=np.float32)
    leading_shape = points.shape[:-1]
    mv = np.zeros(leading_shape + (CONFIG["mv_dim"],), dtype=np.float32)

    x = points[..., 0]
    y = points[..., 1]
    z = points[..., 2]
    x_sq = x * x + y * y + z * z

    mv[..., 1] = x                  # e1
    mv[..., 2] = y                  # e2
    mv[..., 3] = z                  # e3
    mv[..., 4] = 0.5 - 0.5 * x_sq  # e4  (origin basis vector n_o)
    mv[..., 5] = 0.5 + 0.5 * x_sq  # e5  (infinity basis vector n_inf)
    return mv


def normalize_rotor(r: np.ndarray) -> np.ndarray:
    """Project onto Spin manifold via L2 normalisation. Enforces ||R||=1.

    Args:
        r: np.ndarray [..., mv_dim] float32

    Returns:
        np.ndarray [..., mv_dim] float32  — unit-norm rotor.
    """
    r = np.asarray(r, dtype=np.float32)
    norm = np.linalg.norm(r, axis=-1, keepdims=True)
    norm = np.clip(norm, a_min=1e-8, a_max=None)
    return r / norm


def rotor_distance(r1: np.ndarray, r2: np.ndarray) -> float:
    """Geodesic distance between two rotors on the Spin manifold.

    d(R₁, R₂) = arccos(|⟨R₁, R̃₂⟩|).

    Args:
        r1, r2: np.ndarray [..., mv_dim] float32

    Returns:
        float — mean geodesic distance across the batch.
    """
    r1 = np.asarray(r1, dtype=np.float32)
    r2 = np.asarray(r2, dtype=np.float32)
    # Use float64 accumulation to prevent FP32 rounding errors in the dot product
    # from producing |inner| > 1.0 (which would cause arccos domain errors) or
    # self-distance artifacts where d(r, r) > 0 due to summation order.
    inner = np.sum(r1.astype(np.float64) * r2.astype(np.float64), axis=-1)
    inner = np.clip(np.abs(inner), a_min=None, a_max=1.0)
    return float(np.mean(np.arccos(inner)))


def cayley_map(bivector: np.ndarray) -> np.ndarray:
    """First-order Cayley map: unconstrained bivector → unit rotor.

    R = (1 - B/2)^{-1} (1 + B/2) ≈ normalize(1 + B).

    Args:
        bivector: np.ndarray [..., mv_dim] float32

    Returns:
        np.ndarray [..., mv_dim] float32  — unit rotor.
    """
    bivector = np.asarray(bivector, dtype=np.float32)
    identity = np.zeros_like(bivector)
    identity[..., 0] = 1.0          # scalar component = 1
    rotor = identity + bivector
    return normalize_rotor(rotor)
