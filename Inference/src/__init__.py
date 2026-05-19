"""ARCA NoumenalEngine — NumPy Inference Runtime.

Stage 5 GSA NumPy port. ARM64 / OCI Ampere A1 target.

Public surface:
  Phase 1 — Geometric Foundation
    config            : CONFIG, DOMAINS, GRADE_SLICES
    geometry          : conformal_lift, normalize_rotor, rotor_distance, cayley_map
    grade_projection  : GradeProjection, grade_loss
    slerp             : slerp, expand_state_dim_slerp

  Phase 2 — Core Components
    attention         : GeometricProductAttention
    note_block        : NoteBlock
    blocks            : VersorMemMambaBlock
    bridges           : KinematicBridge, ConformalKinematicBridge, LearnedKinematicBridge
    hamiltonian       : HamiltonianExpert, SparseMixtureHamiltonianExperts
    symplectic        : HamiltonianDynamics
    lyapunov          : LyapunovStability
    hopfield          : ModernHopfield, SandboxHopfieldMemory
    jepa              : JEPA

  Phase 3 — Engine
    engine            : NoumenalEngine

Excluded (training-only / C3+ cognitive suite):
  quant.py, koopman.py, kuramoto.py, memory_sdm.py,
  memory_infini.py, riemann.py
"""

# ── Phase 1 ──────────────────────────────────────────────────────────────────
from .config          import CONFIG, DOMAINS, GRADE_SLICES
from .geometry        import conformal_lift, normalize_rotor, rotor_distance, cayley_map
from .grade_projection import GradeProjection, grade_loss
from .slerp           import slerp, expand_state_dim_slerp

# ── Phase 2 ──────────────────────────────────────────────────────────────────
from .attention       import GeometricProductAttention
from .note_block      import NoteBlock
from .blocks          import VersorMemMambaBlock
from .bridges         import KinematicBridge, ConformalKinematicBridge, LearnedKinematicBridge
from .hamiltonian     import HamiltonianExpert, SparseMixtureHamiltonianExperts
from .symplectic      import HamiltonianDynamics
from .lyapunov        import LyapunovStability
from .hopfield        import ModernHopfield, SandboxHopfieldMemory
from .jepa            import JEPA

# ── Phase 3 ──────────────────────────────────────────────────────────────────
from .engine          import NoumenalEngine

__all__ = [
    # Phase 1
    "CONFIG", "DOMAINS", "GRADE_SLICES",
    "conformal_lift", "normalize_rotor", "rotor_distance", "cayley_map",
    "GradeProjection", "grade_loss",
    "slerp", "expand_state_dim_slerp",
    # Phase 2
    "GeometricProductAttention",
    "NoteBlock",
    "VersorMemMambaBlock",
    "KinematicBridge", "ConformalKinematicBridge", "LearnedKinematicBridge",
    "HamiltonianExpert", "SparseMixtureHamiltonianExperts",
    "HamiltonianDynamics",
    "LyapunovStability",
    "ModernHopfield", "SandboxHopfieldMemory",
    "JEPA",
    # Phase 3
    "NoumenalEngine",
]
