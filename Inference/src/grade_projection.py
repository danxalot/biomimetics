"""Grade isolation for Cl(4,1) multivectors — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/grade_projection.py.
Replaces torch.nn.Module with a plain Python class (no autograd needed).
FP32 strict. No quantization.

Cl(4,1) grade structure (32D total):
  Grade 0: scalar          → [0:1]   (1 component)
  Grade 1: vectors         → [1:6]   (5 components)
  Grade 2: bivectors       → [6:16]  (10 components)
  Grade 3: trivectors      → [16:26] (10 components)
  Grade 4: quadvectors     → [26:31] (5 components)
  Grade 5: pseudoscalar    → [31:32] (1 component)
"""
import numpy as np
from .config import CONFIG, GRADE_SLICES


class GradeProjection:
    """Isolates specific grades from a Cl(4,1) multivector.

    Drop-in parity with pytorch GradeProjection(nn.Module).
    Callable as gp(mv, grade=k) to match forward() signature.
    """

    def __init__(self):
        # Canonical Cl(4,1) grade index slices — sourced from config.GRADE_SLICES
        self.indices = GRADE_SLICES

    def get_grade(self, mv: np.ndarray, grade: int) -> np.ndarray:
        """Extract components of a specific grade.

        Args:
            mv:    np.ndarray [..., 32] float32
            grade: int in 0..5

        Returns:
            np.ndarray [..., grade_size] float32
        """
        if grade not in self.indices:
            raise ValueError(f"Invalid grade {grade} for Cl(4,1). Must be 0–5.")
        return np.asarray(mv, dtype=np.float32)[..., self.indices[grade]]

    def project(self, mv: np.ndarray, grades: list) -> np.ndarray:
        """Return a multivector retaining only the specified grades (others zeroed).

        Args:
            mv:     np.ndarray [..., 32] float32
            grades: list of int  — grade indices to keep

        Returns:
            np.ndarray [..., 32] float32  — masked multivector.
        """
        mv = np.asarray(mv, dtype=np.float32)
        mask = np.zeros(mv.shape[-1], dtype=np.float32)
        for g in grades:
            mask[self.indices[g]] = 1.0
        return mv * mask

    def __call__(self, mv: np.ndarray, grade: int = None) -> np.ndarray:
        """Mirrors pytorch forward(): grade=None → identity pass-through."""
        if grade is not None:
            return self.get_grade(mv, grade)
        return np.asarray(mv, dtype=np.float32)


def grade_loss(
    pred: np.ndarray,
    target: np.ndarray,
    weights: dict = None,
) -> float:
    """Weighted MSE loss across Cl(4,1) grades.

    Parity with pytorch grade_loss(). Returns a Python float (no autograd).

    Args:
        pred, target: np.ndarray [..., 32] float32
        weights:      dict {grade: float_weight} or None for uniform MSE.

    Returns:
        float — scalar loss value.
    """
    pred   = np.asarray(pred,   dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)

    if weights is None:
        return float(np.mean((pred - target) ** 2))

    proj = GradeProjection()
    total = 0.0
    for grade, w in weights.items():
        p_g = proj.get_grade(pred,   grade)
        t_g = proj.get_grade(target, grade)
        total += w * float(np.mean((p_g - t_g) ** 2))
    return total
