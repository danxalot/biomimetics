"""NoumenalEngine — the core ARCA C2 production engine.

Integrates the Conformal Geometric Algebra manifold with the State-Space backbone
(Mamba) and Hamiltonian Sparse Mixture of Experts.

Architecture:
1.  KinematicBridge (Lifts raw input to Cl(4,1) manifold)
2.  VersorMemMambaBlocks (GPA → Mamba → NoteBlock)
3.  SMoE-HE (Sparse Mixture of Hamiltonian Experts)
4.  GradeProjection (Loss regularization)
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import CONFIG
from .bridges import KinematicBridge
from .blocks import VersorMemMambaBlock
# SMoE-HE has historically been declared in two places (blocks.py and
# hamiltonian.py). hamiltonian.py is the canonical source — pull from there
# to remove drift.
from .hamiltonian import SparseMixtureHamiltonianExperts
from .grade_projection import GradeProjection
from .hopfield import ModernHopfield, SandboxHopfieldMemory


class NoumenalEngine(nn.Module):
    def __init__(self, domains: dict):
        super().__init__()
        self.domains = domains
        
        # 1. Kinematic Bridges (Domain-specific lifting)
        self.bridges = nn.ModuleDict({
            domain: KinematicBridge(in_dim, domain=domain) 
            for domain, in_dim in domains.items()
        })
        
        d_model = CONFIG["embed_dim"]
        mv_dim = CONFIG["mv_dim"]
        
        # 2. Input Projection
        self.input_proj = nn.Linear(mv_dim, d_model)
        
        # 3. Backbone (Versor blocks)
        self.blocks = nn.ModuleList([
            VersorMemMambaBlock(
                d_model=d_model,
                n_heads=CONFIG["n_heads"],
                mv_dim=mv_dim,
                layer_idx=i,
                total_layers=CONFIG["n_layers"]
            ) for i in range(CONFIG["n_layers"])
        ])
        
        # 4. Phase-Space Head
        # Splits latent into q (coordinates) and p (momenta)
        self.phase_head = nn.Linear(d_model, d_model)
        
        # 5. SMoE-HE (Hamiltonian Experts)
        self.smoe_he = SparseMixtureHamiltonianExperts(
            dim=d_model // 2,
            n_experts=CONFIG["n_experts"]
        )
        
        # 6. Output Head (Rotor prediction)
        self.rotor_head = nn.Linear(d_model, mv_dim)
        
        # 7. Grade Projection (For manifold-aware loss weighting)
        self.grade_proj = GradeProjection()

        # 8. Hopfield Attractor Memory (Round 7.4 — switched to C1-compatible format)
        # SandboxHopfieldMemory matches C1's training-time format (256-dim raw
        # attractors → 512-dim internal storage), allowing the 1868 C1 attractor
        # patterns to be loaded directly via `seed_from_redis()`. Receives the
        # 128-dim phase-space q from the engine instead of the 32-dim multivector.
        # Use_legacy_hopfield=True falls back to ModernHopfield (32-dim mv input,
        # 128-dim internal) for ablation/legacy.
        if CONFIG.get("use_legacy_hopfield", False):
            self.hopfield = ModernHopfield(
                hv_dim=mv_dim,
                internal_dim=CONFIG.get("hopfield_internal", 128),
            )
            self._hopfield_mode = "modern_mv"
        else:
            self.hopfield = SandboxHopfieldMemory(
                attractor_dim=CONFIG.get("hopfield_attractor_dim", 256),
                query_dim=d_model // 2,                # 128 = q-dim
                pattern_projection_dim=CONFIG.get("hopfield_pattern_dim", 512),
                beta=CONFIG.get("hopfield_beta", 4.0),
            )
            self._hopfield_mode = "sandbox_q"

    def forward(self, x: torch.Tensor, domain_name: str, step: int = 0) -> dict:
        # `step` drives QAT warmup inside SMoE-HE — must be propagated from the
        # trainer so quantisation actually engages after qat_warmup_steps.
        # Lifts raw input to multivector manifold
        mv_states = self.bridges[domain_name](x)

        # ── Hopfield bootstrap (only if not already seeded from C1 attractors) ──
        # Sandbox mode: seeded externally via seed_from_redis() with the 1868 C1
        #               attractors. If seeding hasn't happened yet, fall through
        #               and energy will be zero until externally seeded.
        # Modern mode: bootstrap from first batch's mv_states as before.
        if self.hopfield.stored_patterns.shape[0] == 0:
            if self._hopfield_mode == "modern_mv":
                with torch.no_grad():
                    seeds = mv_states.detach().reshape(-1, mv_states.shape[-1])[:64]
                    if seeds.shape[0] > 0:
                        self.hopfield.store(seeds)
            # sandbox_q mode: don't bootstrap from runtime data — expect external
            # seeding from C1 attractors. Energy stays at 0 until then.
        
        # Embed and process through backbone
        h = self.input_proj(mv_states)
        for block in self.blocks:
            h = block(h)
            
        # Split into q, p
        latent_phase = self.phase_head(h)
        q, p = latent_phase.chunk(2, dim=-1)
        
        # Hamiltonian evolution
        q_next, p_next = self.smoe_he(q, p, step)
        
        # Predict next state in MV space
        combined = torch.cat([q_next, p_next], dim=-1)
        predicted_mv = self.rotor_head(combined)
        
        # Compute Hamiltonian for conservation loss
        hamiltonian = self.smoe_he.compute_hamiltonian(q, p)
        
        # Grade-based slicing for loss weighting
        grades = self.grade_proj(predicted_mv)

        # Hopfield Energy (Regularization).
        # Sandbox mode: queries the 128-dim phase-space q against 1868 C1 attractors.
        # Modern  mode: queries the 32-dim predicted multivector against bootstrap patterns.
        if self._hopfield_mode == "sandbox_q":
            hopfield_energy = self.hopfield.compute_energy(q)
        else:
            hopfield_energy = self.hopfield.energy(predicted_mv)
        
        return {
            "predicted_next_state": predicted_mv,
            "mv_states": mv_states,
            "hamiltonian": hamiltonian,
            "q": q,
            "p": p,
            "grades": grades,
            "hopfield_energy": hopfield_energy
        }
