"""
Kinematic Bridge — Pure NumPy Implementation
============================================

Stand-alone, pure-numpy replica of the trained KinematicBridge (nn.Module).

Architecture (matches C2 checkpoint ``bridge_state``):
    Linear(4 → 32)  →  SiLU  →  Linear(32 → 3)  →  tanh × 5.0
    →  conformal_lift_numpy  →  [B, 32] Cl(4,1) multivectors

Total trainable params: 259 (approx. 227 in legacy docs)
"""

import logging
import math
import os
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Path defaults ────────────────────────────────────────────────────────────
_MODULE_ROOT = Path(__file__).resolve().parent
_DEFAULT_BRIDGE_WEIGHTS_PATH = "/Users/danexall/Documents/VS Code Projects/ARCA/models/kinematic_bridge_c2.npz"

# ═══════════════════════════════════════════════════════════════════════════════
# NUMPY MATH PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════════

def _silu_numpy(x: np.ndarray) -> np.ndarray:
    """SiLU / Swish activation: x · σ(x). Matches torch.nn.SiLU exactly."""
    return x * (1.0 / (1.0 + np.exp(-x)))

def normalize_rotor_numpy(r: np.ndarray) -> np.ndarray:
    """Normalize a multivector to ensure it represents a valid rotor (R·R̃ = 1)."""
    norm = np.linalg.norm(r, axis=-1, keepdims=True)
    return r / np.maximum(norm, 1e-12)

def conformal_lift_numpy(points: np.ndarray) -> np.ndarray:
    """
    Lift R³ points into Cl(4,1) conformal space as null vectors.
    X = x·e₁ + y·e₂ + z·e₃ + (½ − ½‖x‖²)·e₊ + (½ + ½‖x‖²)·e₋
    """
    if points.ndim == 1:
        points = points[np.newaxis, :]
    B = points.shape[0]
    mv = np.zeros((B, 32), dtype=np.float32)
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    x_sq = x**2 + y**2 + z**2
    mv[:, 1] = x
    mv[:, 2] = y
    mv[:, 3] = z
    mv[:, 4] = 0.5 - 0.5 * x_sq
    mv[:, 5] = 0.5 + 0.5 * x_sq
    return mv

# ═══════════════════════════════════════════════════════════════════════════════
# KINEMATIC BRIDGE
# ═══════════════════════════════════════════════════════════════════════════════

class NumpyKinematicBridge:
    """
    Pure-numpy replica of the trained KinematicBridge (nn.Module).
    """

    def __init__(self, weights_path: Optional[str] = None):
        loaded = False
        path = weights_path or str(_DEFAULT_BRIDGE_WEIGHTS_PATH)

        if path and os.path.isfile(path):
            try:
                data = np.load(path)
                self.w1 = data["encoder.0.weight"].astype(np.float32)  # (32, 4)
                self.b1 = data["encoder.0.bias"].astype(np.float32)    # (32,)
                self.w2 = data["encoder.2.weight"].astype(np.float32)  # (3, 32)
                self.b2 = data["encoder.2.bias"].astype(np.float32)    # (3,)
                loaded = True
                logger.info(f"KinematicBridge weights loaded from {path}")
            except Exception as exc:
                logger.warning(f"Failed to load KinematicBridge weights from {path}: {exc}")

        if not loaded:
            logger.warning("KinematicBridge using random-init weights.")
            rng = np.random.RandomState(2024)
            limit1 = math.sqrt(6.0 / (4 + 32))
            self.w1 = rng.uniform(-limit1, limit1, (32, 4)).astype(np.float32)
            self.b1 = np.zeros(32, dtype=np.float32)
            limit2 = math.sqrt(6.0 / (32 + 3))
            self.w2 = rng.uniform(-limit2, limit2, (3, 32)).astype(np.float32)
            self.b2 = np.zeros(3, dtype=np.float32)

    def physics_to_cga(self, physics_4d: np.ndarray) -> np.ndarray:
        """
        4D physics state → 32D Cl(4,1) multivector.
        The mandatory pipeline: 4 → Linear → SiLU → Linear → tanh×5 → conformal_lift
        """
        if physics_4d.ndim == 1:
            physics_4d = physics_4d[np.newaxis, :]

        # Layer 1: Linear(4→32) + SiLU
        h = physics_4d @ self.w1.T + self.b1
        h = _silu_numpy(h)

        # Layer 2: Linear(32→3) + tanh × 5.0
        points_3d = h @ self.w2.T + self.b2
        points_3d = np.tanh(points_3d) * 5.0

        # Conformal lift: R³ → Cl(4,1) null cone
        return conformal_lift_numpy(points_3d)

# ═══════════════════════════════════════════════════════════════════════════════
# TRACK B — NumpyCliffordHDCBridge  (10k HDC → 3D → 32D CGA)
# ═══════════════════════════════════════════════════════════════════════════════

class NumpyCliffordHDCBridge:
    """
    Pure-numpy equivalent of CliffordHDCBridge.
    Handles the transformation between various HDC dimensions and CGA space.
    """
    def __init__(self, input_dim: int = 512, output_dim: int = 10000):
        # We use consistent seeds to match trained projection subspaces
        self.rng_jl = np.random.RandomState(42)
        self.rng_3d = np.random.RandomState(99)
        self.input_dim = input_dim
        self.output_dim = output_dim
        
        # JL Projection from Input Space (e.g. 512) to Latent Manifold (64)
        self.in_proj = self.rng_jl.randn(input_dim, 64).astype(np.float32) / math.sqrt(64)
        
        # 3D Point Projection (bounded [-5, 5] via tanh)
        self.proj_3d = self.rng_3d.randn(64, 3).astype(np.float32) / math.sqrt(3)
        
        # Expansion Projection from Manifold (64) to High-D HDC (e.g. 10000)
        # Note: We re-init the RNG to ensure deterministic 10k expansion
        rng_expand = np.random.RandomState(42)
        self.out_proj = rng_expand.randn(output_dim, 64).astype(np.float32) / math.sqrt(64)

    def hdc_to_cga(self, hdc_vector: np.ndarray) -> np.ndarray:
        """HDC [B, input_dim] -> Cl(4,1) [B, 32]."""
        if hdc_vector.ndim == 1:
            hdc_vector = hdc_vector[np.newaxis, :]
        compressed = hdc_vector @ self.in_proj  # [B, 64]
        points_3d = np.tanh(compressed @ self.proj_3d) * 5.0  # [B, 3]
        return conformal_lift_numpy(points_3d)  # [B, 32]

    def cga_to_hdc(self, cga_32d: np.ndarray) -> np.ndarray:
        """CGA [B, 32] -> HDC [B, output_dim]."""
        if cga_32d.ndim == 1:
            cga_32d = cga_32d[np.newaxis, :]
        # Pad 32d to 64d
        B = cga_32d.shape[0]
        cga_64 = np.zeros((B, 64), dtype=np.float32)
        cga_64[:, :32] = cga_32d
        # Expand to high-dim space
        hdc_out = np.maximum(cga_64 @ self.out_proj.T, 0.0) # [B, output_dim]
        return hdc_out

if __name__ == "__main__":
    bridge = NumpyKinematicBridge()
    test_4d = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    cga = bridge.physics_to_cga(test_4d)
    print(f"Test CGA (indices 1-5): {cga[0, 1:6]}")
    print(f"CGA Shape: {cga.shape}")
