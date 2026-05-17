"""Gold Standard Archive - PyTorch Neural Components.

Canonical implementations for ARCA C2 production training.
"""

# Stage 1 — Geometric Foundation
from .config import DOMAINS
from .geometry import conformal_lift, rotor_distance, normalize_rotor, cayley_map
from .quant import Int8SaturationFakeQuantize, fake_quant_int8
from .slerp import slerp, expand_state_dim_slerp, salvage_and_expand_state_dict

# Stage 2 — Core Attention & Blocks
from .attention import GeometricProductAttention
from .note_block import NoteBlock
from .blocks import VersorMemMambaBlock, real_mamba_available
from .hamiltonian import HamiltonianExpert, SparseMixtureHamiltonianExperts
from .hopfield import ModernHopfield
from .bridges import ConformalKinematicBridge, LearnedKinematicBridge

# Stage 3 — Kuramoto & Dynamics
from .kuramoto import KuramotoLayer, GOLDEN_RATIO
from .symplectic import HamiltonianDynamics
from .lyapunov import LyapunovStability

# Stage 4 — Engine & Projections
from .engine import NoumenalEngine, GradeProjection

__all__ = [
    "DOMAINS",
    "conformal_lift", "rotor_distance", "normalize_rotor", "cayley_map",
    "Int8SaturationFakeQuantize", "fake_quant_int8",
    "slerp", "expand_state_dim_slerp", "salvage_and_expand_state_dict",
    "GeometricProductAttention",
    "NoteBlock",
    "VersorMemMambaBlock", "real_mamba_available",
    "HamiltonianExpert", "SparseMixtureHamiltonianExperts",
    "ModernHopfield",
    "ConformalKinematicBridge", "LearnedKinematicBridge",
    "KuramotoLayer", "GOLDEN_RATIO",
    "HamiltonianDynamics",
    "LyapunovStability",
    "GradeProjection", "NoumenalEngine",
]
