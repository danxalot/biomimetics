"""
Conformal Geometric Algebra Lift (cga_lift)

Part of Stage 2: Physical Engine
Projects 512-dim vectors into 32-dim Cl(4,1) conformal geometric algebra space
"""

import numpy as np
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class CGALift:
    """
    Conformal Geometric Algebra (CGA) transformation

    Maps 512-dim semantic vectors to 32-dim multivectors in Cl(4,1) space
    Cl(4,1) = Space of 5D conformal geometric algebra
    """

    def __init__(self):
        # Cl(4,1) basis: e1, e2, e3, e4, e5
        # e1-e3: spatial dimensions
        # e4: time/nilpotent
        # e5: conformal origin
        self.dimension = 32

        # Learnable projection matrix (512 → 32)
        # Initialize with random weights, can be trained
        self.projection_matrix = np.random.randn(512, 32).astype(np.float32) * 0.01

        # CGA basis vectors (normalized)
        self.basis = np.eye(5, dtype=np.float32)

        logger.info(f"CGA Lift initialized: 512-dim → 32-dim Cl(4,1)")

    def lift(self, vector_512: List[float]) -> np.ndarray:
        """
        Lift 512-dim semantic vector to 32-dim CGA multivector

        Args:
            vector_512: 512-dim semantic embedding

        Returns:
            32-dim multivector in Cl(4,1)
        """
        # Project to 32 dimensions
        vector_array = np.array(vector_512, dtype=np.float32)
        if len(vector_array) != 512:
            raise ValueError(f"Expected 512-dim vector, got {len(vector_array)}")

        # Linear projection
        projected = vector_array @ self.projection_matrix

        # Reshape to multivector components
        # 32 components: scalars, vectors, bivectors, etc.
        multivector = projected.reshape(-1)

        # Apply CGA normalization
        # Ensure the multivector has the correct geometric structure
        multivector = self._normalize_multivector(multivector)

        return multivector

    def _normalize_multivector(self, multivector: np.ndarray) -> np.ndarray:
        """Normalize multivector to maintain geometric consistency"""
        # Separate scalar and geometric parts
        scalar_part = multivector[0]
        geometric_part = multivector[1:]

        # Normalize geometric part
        geo_norm = np.linalg.norm(geometric_part)
        if geo_norm > 0:
            geometric_part = geometric_part / geo_norm

        # Recombine
        result = np.concatenate([[scalar_part], geometric_part])

        return result

    def inverse_lift(self, multivector_32: np.ndarray) -> np.ndarray:
        """Inverse transformation: 32-dim multivector → 512-dim (approximate)"""
        # Simple inverse using transposed projection
        inverse_projection = self.projection_matrix.T @ np.linalg.inv(
            self.projection_matrix.T @ self.projection_matrix
        )

        return multivector_32 @ inverse_projection


# Singleton instance
_cga_lift: Optional[CGALift] = None


def get_cga_lift() -> CGALift:
    """Get or create CGA lift singleton"""
    global _cga_lift
    if _cga_lift is None:
        _cga_lift = CGALift()
    return _cga_lift


def cga_lift_vector(vector_512: List[float]) -> List[float]:
    """Convenience function to lift a 512-dim vector to CGA space"""
    lift = get_cga_lift()
    result = lift.lift(vector_512)
    return result.tolist()


def cga_inverse_lift(multivector_32: List[float]) -> List[float]:
    """Convenience function to inverse lift from CGA space"""
    lift = get_cga_lift()
    result = lift.inverse_lift(np.array(multivector_32))
    return result.tolist()


# ── Conformal Lift (NumPy version) ──────────────────────────────────────
def conformal_lift_numpy(points_3d: np.ndarray) -> np.ndarray:
    """
    Fixed mathematical mapping from R^3 to Cl(4,1) null cone.
    X = x + 0.5*x^2*e_inf + e_0
    """
    if points_3d.ndim == 2:
        points_3d = points_3d[np.newaxis, :, :]
    
    B, T, _ = points_3d.shape
    cga_vectors = np.zeros((B, T, 32), dtype=np.float32)
    cga_vectors[..., 1:4] = points_3d
    sq_norm = np.sum(points_3d**2, axis=-1)
    cga_vectors[..., 4] = 0.5 * sq_norm
    cga_vectors[..., 5] = 1.0
    return cga_vectors


def reverse_conformal_lift_numpy(cga_32d: np.ndarray) -> np.ndarray:
    """
    Extracts 3D Euclidean coordinates from a 32D Cl(4,1) conformal vector.
    Assuming standard basis: [Scalar(1), Vectors(5), Bivectors(10), Trivectors(10), Quadvectors(5), Pseudoscalar(1)]
    Indices 1, 2, 3 correspond to the e1, e2, e3 Euclidean axes.
    """
    mv = cga_32d.flatten().astype(np.float32)

    # Extract the Euclidean Grade 1 components (x, y, z)
    x_euclidean = mv[1:4]

    # In a true homogeneous space, we must normalize by the conformal weight.
    # To ensure visual stability in the WebGL projection, we L2 normalize
    # the Euclidean projection and scale it to the original [-5.0, 5.0] bounding box.
    norm = np.linalg.norm(x_euclidean) + 1e-12
    return (x_euclidean / norm) * 5.0
