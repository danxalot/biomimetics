"""
Conformal Lift — R³ → Cl(4,1) Null Cone Embedding
===================================================

Standalone, pure-numpy implementation of the conformal lift used throughout
the ARCA Noumenal Engine pipeline.

Mathematical definition:

    X = x·e₁ + y·e₂ + z·e₃ + (½ − ½‖x‖²)·e₊ + (½ + ½‖x‖²)·e₋

This maps 3-dimensional Euclidean points onto the null cone of the
Cl(4,1) conformal geometric algebra, producing 32-dimensional
multivector representations.

The 32 components correspond to the full Cl(4,1) basis:
    Index 0:   scalar (1)
    Index 1-5: grade-1 vectors (e₁, e₂, e₃, e₊, e₋)
    Index 6+:  higher-grade blades (bivectors, trivectors, etc.)

Only indices 1–5 are populated by the lift; all others remain zero.
This places the point exactly on the null cone (X·X = 0).

The "No-Direct-Lift" Rule
--------------------------
The conformal lift accepts ONLY 3-dimensional Euclidean points.
Any input of dimension ≠ 3 MUST first pass through a trained bridge:

  - 4D physics state → NumpyKinematicBridge (4→32→SiLU→3→tanh×5) → lift
  - 10k HDC vector   → NumpyCliffordHDCBridge (JL 10k→64→3)      → lift
  - Arbitrary N-dim  → PROHIBITED — geometrically meaningless

This file is a reference copy stored alongside the model weights
in the ARCA/models/ directory.  The authoritative runtime copy lives
in ARCA/services/neural_system/phenomenological_core.py.

Usage
-----
>>> from conformal_lift import conformal_lift_numpy, normalize_rotor_numpy
>>> points = np.array([[1.0, 2.0, 3.0], [-0.5, 0.0, 0.5]])
>>> cga = conformal_lift_numpy(points)
>>> cga.shape
(2, 32)
"""

import numpy as np


def conformal_lift_numpy(points: np.ndarray) -> np.ndarray:
    """
    Lift R³ points into Cl(4,1) conformal space as null vectors.

    X = x·e₁ + y·e₂ + z·e₃ + (½ − ½‖x‖²)·e₊ + (½ + ½‖x‖²)·e₋

    Args:
        points: shape (3,) for a single point, or (B, 3) for a batch.

    Returns:
        shape (B, 32) — multivector components in Cl(4,1).
        For single-point input, B=1.
    """
    if points.ndim == 1:
        points = points[np.newaxis, :]

    if points.shape[-1] != 3:
        raise ValueError(
            f"conformal_lift_numpy expects R³ input (dim=3), got dim={points.shape[-1]}. "
            f"Use NumpyKinematicBridge (4D→3D) or NumpyCliffordHDCBridge (10kD→3D) first."
        )

    B = points.shape[0]
    mv = np.zeros((B, 32), dtype=np.float32)

    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]
    x_sq = x**2 + y**2 + z**2

    # Grade-1 vector components
    mv[:, 1] = x  # e₁
    mv[:, 2] = y  # e₂
    mv[:, 3] = z  # e₃
    mv[:, 4] = 0.5 - 0.5 * x_sq  # e₊  (null basis)
    mv[:, 5] = 0.5 + 0.5 * x_sq  # e₋  (null basis)

    return mv


def normalize_rotor_numpy(r: np.ndarray) -> np.ndarray:
    """
    Project a multivector onto the Spin manifold via normalisation.

    Ensures ‖R‖ = 1 so that the sandwich product R·M·R̃ is a
    proper conformal transformation.

    Args:
        r: shape (..., 32) — raw rotor multivector(s).

    Returns:
        shape (..., 32) — normalised rotor(s).
    """
    norm = np.linalg.norm(r, axis=-1, keepdims=True).clip(min=1e-8)
    return r / norm


def _silu_numpy(x: np.ndarray) -> np.ndarray:
    """SiLU / Swish activation: x · σ(x).  Matches torch.nn.SiLU exactly."""
    return x * (1.0 / (1.0 + np.exp(-x)))


def _gelu_numpy(x: np.ndarray) -> np.ndarray:
    """
    GELU activation (tanh approximation).
    Matches torch.nn.GELU(approximate='tanh').
    """
    return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x**3)))


# ═══════════════════════════════════════════════════════════════════════════════
# Verification
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Conformal Lift — Cl(4,1) Reference Implementation")
    print("=" * 55)

    # Test 1: Single point
    p1 = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    mv1 = conformal_lift_numpy(p1)
    assert mv1.shape == (1, 32), f"Expected (1, 32), got {mv1.shape}"

    x_sq = 1.0 + 4.0 + 9.0  # = 14.0
    assert np.isclose(mv1[0, 1], 1.0), "e₁ should be x"
    assert np.isclose(mv1[0, 2], 2.0), "e₂ should be y"
    assert np.isclose(mv1[0, 3], 3.0), "e₃ should be z"
    assert np.isclose(mv1[0, 4], 0.5 - 0.5 * x_sq), "e₊ mismatch"
    assert np.isclose(mv1[0, 5], 0.5 + 0.5 * x_sq), "e₋ mismatch"
    print(f"  ✅ Single point: [1,2,3] → mv[1:6] = {mv1[0, 1:6]}")

    # Null cone check: X·X should equal 0
    # In Cl(4,1) with signature (+,+,+,+,-):
    #   X·X = x² + y² + z² + e₊² − e₋²
    #       = x² + y² + z² + (0.5 - 0.5*s)² - (0.5 + 0.5*s)²
    #       = s + 0.25 - 0.5s + 0.25s² - 0.25 - 0.5s - 0.25s²
    #       = s - s = 0  ✓
    e_plus = mv1[0, 4]
    e_minus = mv1[0, 5]
    inner = x_sq + e_plus**2 - e_minus**2
    assert abs(inner) < 1e-5, f"Not on null cone: X·X = {inner}"
    print(f"  ✅ Null cone check: X·X = {inner:.2e} ≈ 0")

    # Test 2: Batch
    batch = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [-0.5, 0.5, -0.5],
            [5.0, 5.0, 5.0],
        ],
        dtype=np.float32,
    )
    mv_batch = conformal_lift_numpy(batch)
    assert mv_batch.shape == (4, 32), f"Expected (4, 32), got {mv_batch.shape}"
    print(f"  ✅ Batch lift: {batch.shape} → {mv_batch.shape}")

    # Origin maps to: e₊ = 0.5, e₋ = 0.5
    assert np.isclose(mv_batch[0, 4], 0.5), "Origin e₊ should be 0.5"
    assert np.isclose(mv_batch[0, 5], 0.5), "Origin e₋ should be 0.5"
    print(f"  ✅ Origin: e₊={mv_batch[0, 4]:.1f}, e₋={mv_batch[0, 5]:.1f}")

    # Test 3: Dimension guard
    try:
        conformal_lift_numpy(np.array([1.0, 2.0, 3.0, 4.0]))
        assert False, "Should have raised ValueError for 4D input"
    except ValueError as e:
        print(f"  ✅ Dimension guard: correctly rejected 4D input")

    # Test 4: Rotor normalisation
    raw = np.random.randn(5, 32).astype(np.float32)
    normed = normalize_rotor_numpy(raw)
    norms = np.linalg.norm(normed, axis=-1)
    assert np.allclose(norms, 1.0, atol=1e-6), f"Norms should be 1.0, got {norms}"
    print(f"  ✅ Rotor normalisation: all ‖R‖ = 1.0")

    # Test 5: Activations
    x = np.array([-2.0, -1.0, 0.0, 1.0, 2.0], dtype=np.float32)
    silu_out = _silu_numpy(x)
    gelu_out = _gelu_numpy(x)
    assert np.isclose(silu_out[2], 0.0), "SiLU(0) should be 0"
    assert np.isclose(gelu_out[2], 0.0), "GELU(0) should be 0"
    print(f"  ✅ SiLU: {silu_out}")
    print(f"  ✅ GELU: {gelu_out}")

    # Test 6: All other components should be zero
    assert np.all(mv1[0, 0] == 0.0), "Scalar component should be 0"
    assert np.all(mv1[0, 6:] == 0.0), "Higher-grade components should be 0"
    print(f"  ✅ Sparsity: only indices 1-5 populated, rest zero")

    print()
    print("All checks passed.")
    print("=" * 55)
