import torch
import torch.nn as nn
from .config import CONFIG

class GradeProjection(nn.Module):
    """
    Isolates specific grades from a Cl(4,1) multivector.
    Cl(4,1) basis components (32 total):
    - Grade 0: Scalar (1)
    - Grade 1: Vectors (5)
    - Grade 2: Bivectors (10)
    - Grade 3: Trivectors (10)
    - Grade 4: Quadvectors (5)
    - Grade 5: Pseudoscalar (1)
    """

    def __init__(self):
        super().__init__()
        # Grade indices for Cl(4,1)
        self.indices = {
            0: slice(0, 1),
            1: slice(1, 6),
            2: slice(6, 16),
            3: slice(16, 26),
            4: slice(26, 31),
            5: slice(31, 32)
        }

    def get_grade(self, mv: torch.Tensor, grade: int) -> torch.Tensor:
        """Extract components of a specific grade."""
        if grade not in self.indices:
            raise ValueError(f"Invalid grade {grade} for Cl(4,1). Must be 0-5.")
        return mv[..., self.indices[grade]]

    def project(self, mv: torch.Tensor, grades: list) -> torch.Tensor:
        """Returns a multivector containing only the specified grades (masked)."""
        mask = torch.zeros_like(mv)
        for g in grades:
            mask[..., self.indices[g]] = 1.0
        return mv * mask

    def forward(self, mv: torch.Tensor, grade: int = None) -> torch.Tensor:
        """If grade is specified, returns only those components. Otherwise returns the whole MV."""
        if grade is not None:
            return self.get_grade(mv, grade)
        return mv

def grade_loss(pred: torch.Tensor, target: torch.Tensor, weights: dict = None) -> torch.Tensor:
    """
    Calculates weighted MSE loss across different grades.
    Example weights: {0: 1.0, 1: 0.5, 2: 0.8}
    """
    proj = GradeProjection()
    total_loss = torch.tensor(0.0, device=pred.device)
    
    # Default to equal weighting if not provided
    if weights is None:
        return torch.nn.functional.mse_loss(pred, target)

    for grade, weight in weights.items():
        p_g = proj.get_grade(pred, grade)
        t_g = proj.get_grade(target, grade)
        total_loss += weight * torch.nn.functional.mse_loss(p_g, t_g)
        
    return total_loss
