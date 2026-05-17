"""KinematicBridge — polymorphic input gateway.

Each domain in DOMAINS gets its own KinematicBridge that maps raw sensor data
(pendulum angles, optical flow, lattice spins, etc.) into the 32D Cl(4,1)
conformal manifold.

Two flavours coexist for historical reasons:
- ``ConformalKinematicBridge`` — direct mapping, no learned encoder. Pads raw
  features into multivector slots after a log-squash. This is the version used
  in the active Kaggle script. Domain-aware: when ``domain == "relativity"``,
  ``x[0]`` is treated as time and routed to the scalar grade ``mv[..., 0]``.
- ``LearnedKinematicBridge`` — encoder MLP → 3D points → conformal_lift. This
  is the version from `Gold_Standard_Archive/C2/master_c2_kinematics.py:157-172`.
  Used when the trained `.npz` weights at `math_modules/kinematic_bridge_c2.npz`
  are intended.

The active training run uses the conformal-direct flavour. The learned flavour
is preserved here for ablations and for pre-trained-weights compatibility.
"""
import torch
import torch.nn as nn

from .config import CONFIG
from .geometry import conformal_lift


class ConformalKinematicBridge(nn.Module):
    """Domain-aware bridge populating ALL grades 0-5 of Cl(4,1).

    Forward shape: x [..., in_dim] → mv [..., 32].

    Cl(4,1) grade decomposition (32 components total):
      grade 0 (scalar):       1 comp  → mv[0]      (time for relativity, magnitude otherwise)
      grade 1 (vectors):      5 comps → mv[1:6]    (e1-e3 spatial + e4=n_inf + e5=n_o)
      grade 2 (bivectors):   10 comps → mv[6:16]   (rotation/orientation planes)
      grade 3 (trivectors):  10 comps → mv[16:26]  (oriented volumes)
      grade 4 (quadvectors):  5 comps → mv[26:31]  (pseudovectors)
      grade 5 (pseudoscalar): 1 comp  → mv[31]     (I = e1e2e3e4e5, chirality/volume)

    Round 7.4 — opened bridge from "grades 0-1 + raw-feature dump in bivector slots"
    to FULL grades 0-5 via a learned encoder. The earlier C1 conformal_lift hardcoded
    only grade-1 (mv[1:6]); subsequent C2 attempts dumped raw features into mv[6:6+n]
    without grade-aware structure. Now: algebraic grade-0/1 + learned grades 2-5.

    Initialization is near-zero on the higher-grade encoder output so the C1 prior
    (which never saw signal at mv[6:32]) gets a smooth ramp into the new content as
    training progresses, rather than a discontinuous jump that would destabilize the
    transplanted weights.
    """

    def __init__(self, in_dim: int, domain: str = ""):
        super().__init__()
        self.in_dim = in_dim
        self.domain = domain
        self.is_relativity = (domain == "relativity")

        # Learned encoder: raw input → 26 components for grades 2-5
        hidden = max(64, in_dim * 4)
        self.higher_grade_encoder = nn.Sequential(
            nn.Linear(in_dim, hidden),
            nn.SiLU(),
            nn.LayerNorm(hidden),
            nn.Linear(hidden, 26),
            nn.Tanh(),  # bound output to [-1, 1]
        )

        # Near-zero init on the final projection so the bridge starts close to
        # the legacy grade-0/1-only behavior. Critical for C1 weight transplant:
        # C1's input_proj never saw signal at mv[6:32] and the columns 6-31 of
        # input_proj.weight are essentially random from C1's perspective. Ramp
        # the higher-grade content in gradually so input_proj has time to adapt.
        with torch.no_grad():
            # The final Linear is index -2 (Tanh is index -1)
            self.higher_grade_encoder[-2].weight.mul_(0.01)
            self.higher_grade_encoder[-2].bias.zero_()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Log-squash to keep values bounded under FP16 / int8 quant.
        x_squashed = torch.sign(x) * torch.log1p(torch.abs(x))

        mv = torch.zeros(*x.shape[:-1], CONFIG["mv_dim"], device=x.device, dtype=x.dtype)

        # ── Grade 0 (scalar) and Grade 1 (vectors): algebraic content ─────
        # Relativity: x[0]=time → mv[0] (scalar grade); x[1:4]=spatial.
        # Other domains: x[0:3]=spatial; mv[0] left at 0 (could carry magnitude).
        if self.is_relativity:
            mv[..., 0:1] = x_squashed[..., 0:1]
            spatial_core = x_squashed[..., 1:4]
        else:
            spatial_core = x_squashed[..., :3]

        # Conformal anchors (grade-1 vectors)
        r2 = torch.sum(spatial_core ** 2, dim=-1, keepdim=True)
        mv[..., 1:4] = spatial_core
        mv[..., 4:5] = 0.5 * r2 - 0.5      # n_inf (e4)
        mv[..., 5:6] = 0.5 * r2 + 0.5      # n_o   (e5)

        # ── Grades 2-5 (bivectors through pseudoscalar): learned content ──
        # The encoder sees the FULL raw input (not just extras), so it can
        # learn grade-2+ content from any combination of input features —
        # not just the leftovers after spatial extraction.
        higher_features = self.higher_grade_encoder(x_squashed.to(self.higher_grade_encoder[0].weight.dtype))
        higher_features = higher_features.to(mv.dtype)
        mv[..., 6:32] = higher_features  # bivectors + trivectors + quadvectors + pseudoscalar
        return mv


class LearnedKinematicBridge(nn.Module):
    """MLP-encoded bridge: x → 3D points → conformal_lift.

    Use this when you have pre-trained bridge weights (`kinematic_bridge_c2.npz`)
    or for ablation runs where the bridge is learned end-to-end.
    """

    def __init__(self, in_dim: int):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(in_dim, 64),
            nn.SiLU(),
            nn.Linear(64, 3),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        leading = x.shape[:-1]
        points_3d = torch.tanh(self.encoder(x)) * 5.0
        points_flat = points_3d.view(-1, 3)
        mv_flat = conformal_lift(points_flat)
        return mv_flat.view(*leading, CONFIG["mv_dim"])


# Default alias used by the Kaggle bundle.
KinematicBridge = ConformalKinematicBridge
