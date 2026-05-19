"""NoumenalEngine — NumPy runtime (ARM64 / OCI Ampere A1).

1:1 parity port of Gold_Standard_Archive/pytorch/engine.py.

Architecture:
  1. KinematicBridges       — domain-aware lifting to Cl(4,1) manifold [→ 32D mv]
  2. input_proj             — mv_dim → embed_dim linear projection
  3. VersorMemMambaBlocks   — GPA → SSM → NoteBlock → LayerNorm (×n_layers)
  4. phase_head             — latent → phase-space (q, p split)
  5. SMoE-HE                — Hamiltonian Sparse Mixture of Experts
  6. rotor_head             — embed_dim → mv_dim  (Rosetta projection)
  7. GradeProjection        — grade-aware loss slices
  8. SandboxHopfieldMemory  — attractor energy regularization

ROSETTA BRIDGE CONTRACT:
  outputs["rosetta_vector"]  — np.ndarray [2048] float32
  This is the flat vector for direct C-array injection into llama_batch.
  Derived from rosetta_head(predicted_mv) → 2048D.
  rosetta_head is an additional Linear [rosetta_output_dim, mv_dim] applied
  after rotor_head — loaded from checkpoint key "rosetta_head.*" if present,
  otherwise uses an identity-pad expansion.

WEIGHT LOADING:
  Call engine.load_weights(state_dict) where state_dict is the numpy dict
  extracted from c2_baseline_30k.pth via torch.load + .numpy().

  Key mapping from checkpoint (PyTorch) → engine attribute:
    bridges.{domain}.higher_grade_encoder.0.weight   → bridges[domain].W0
    bridges.{domain}.higher_grade_encoder.0.bias     → bridges[domain].b0
    bridges.{domain}.higher_grade_encoder.2.weight   → bridges[domain].ln_w  (LayerNorm)
    bridges.{domain}.higher_grade_encoder.2.bias     → bridges[domain].ln_b
    bridges.{domain}.higher_grade_encoder.3.weight   → bridges[domain].W3
    bridges.{domain}.higher_grade_encoder.3.bias     → bridges[domain].b3
    input_proj.weight / .bias                        → self.W_input / b_input
    blocks.{i}.gpa.W_q.weight / .bias etc.           → blocks[i].gpa.*
    blocks.{i}.mamba.*                               → blocks[i].mamba.*
    blocks.{i}.note_block.*                          → blocks[i].note_block.*
    blocks.{i}.norm1.weight / .bias etc.             → blocks[i].norm*_w/b
    phase_head.weight / .bias                        → self.W_phase / b_phase
    smoe_he.gate.weight / .bias                      → smoe_he.W_gate / b_gate
    smoe_he.experts.{i}.potential.0.weight etc.      → smoe_he.experts[i].*
    rotor_head.weight / .bias                        → self.W_rotor / b_rotor
    hopfield.query_lift.weight / .bias               → hopfield.W_lift / b_lift
    hopfield.input_projection.weight / .bias         → hopfield.W_proj / b_proj
    hopfield.stored_patterns                         → hopfield.stored_patterns
"""
import numpy as np
from .config import CONFIG, DOMAINS
from .bridges import KinematicBridge
from .blocks import VersorMemMambaBlock
from .hamiltonian import SparseMixtureHamiltonianExperts
from .grade_projection import GradeProjection
from .hopfield import ModernHopfield, SandboxHopfieldMemory


class NoumenalEngine:
    """Core ARCA C2 inference engine — NumPy / ARM64.

    Args:
        domains:    dict {name: in_dim} — same as CONFIG DOMAINS.
        weights:    flat numpy weight dict (extracted from .pth checkpoint).
                    If None, all sub-modules are randomly initialized for testing.
    """

    def __init__(self, domains: dict, weights: dict = None):
        self.domains = domains
        d_model = CONFIG["embed_dim"]
        mv_dim  = CONFIG["mv_dim"]

        # ── 1. Kinematic Bridges ────────────────────────────────────────────
        self.bridges = {
            domain: KinematicBridge(
                in_dim=in_dim,
                domain=domain,
                weights=self._extract(weights, f"bridges.{domain}") if weights else None,
            )
            for domain, in_dim in domains.items()
        }

        # ── 2. Input Projection: mv_dim → d_model ───────────────────────────
        if weights and "input_proj.weight" in weights:
            self.W_input = np.asarray(weights["input_proj.weight"], dtype=np.float32)
            self.b_input = np.asarray(weights["input_proj.bias"],   dtype=np.float32)
        else:
            rng = np.random.default_rng(10)
            self.W_input = rng.standard_normal((d_model, mv_dim)).astype(np.float32) * 0.02
            self.b_input = np.zeros(d_model, dtype=np.float32)

        # ── 3. Backbone — VersorMemMambaBlocks ──────────────────────────────
        self.blocks = [
            VersorMemMambaBlock(
                d_model=d_model,
                n_heads=CONFIG["n_heads"],
                mv_dim=mv_dim,
                layer_idx=i,
                total_layers=CONFIG["n_layers"],
                weights=self._extract_block(weights, i) if weights else None,
            )
            for i in range(CONFIG["n_layers"])
        ]

        # ── 4. Phase-Space Head ─────────────────────────────────────────────
        if weights and "phase_head.weight" in weights:
            self.W_phase = np.asarray(weights["phase_head.weight"], dtype=np.float32)
            self.b_phase = np.asarray(weights["phase_head.bias"],   dtype=np.float32)
        else:
            rng = np.random.default_rng(11)
            self.W_phase = rng.standard_normal((d_model, d_model)).astype(np.float32) * 0.02
            self.b_phase = np.zeros(d_model, dtype=np.float32)

        # ── 5. SMoE-HE ──────────────────────────────────────────────────────
        self.smoe_he = SparseMixtureHamiltonianExperts(
            dim=d_model // 2,
            n_experts=CONFIG["n_experts"],
            weights=self._extract_smoe(weights) if weights else None,
        )

        # ── 6. Rotor Head: d_model → mv_dim ────────────────────────────────
        if weights and "rotor_head.weight" in weights:
            self.W_rotor = np.asarray(weights["rotor_head.weight"], dtype=np.float32)
            self.b_rotor = np.asarray(weights["rotor_head.bias"],   dtype=np.float32)
        else:
            rng = np.random.default_rng(12)
            self.W_rotor = rng.standard_normal((mv_dim, d_model)).astype(np.float32) * 0.02
            self.b_rotor = np.zeros(mv_dim, dtype=np.float32)

        # ── 6b. Rosetta Head: mv_dim → 2048D (Rosetta Bridge) ───────────────
        rosetta_dim = CONFIG["rosetta_output_dim"]   # 2048
        if weights and "rosetta_head.weight" in weights:
            self.W_rosetta = np.asarray(weights["rosetta_head.weight"], dtype=np.float32)
            self.b_rosetta = np.asarray(weights["rosetta_head.bias"],   dtype=np.float32)
        else:
            # Identity pad: project mv_dim → rosetta_dim via random orthogonal init
            rng = np.random.default_rng(13)
            self.W_rosetta = rng.standard_normal((rosetta_dim, mv_dim)).astype(np.float32) * (1.0 / np.sqrt(mv_dim))
            self.b_rosetta = np.zeros(rosetta_dim, dtype=np.float32)

        # ── 7. Grade Projection ─────────────────────────────────────────────
        self.grade_proj = GradeProjection()

        # ── 8. Hopfield Memory ──────────────────────────────────────────────
        if CONFIG.get("use_legacy_hopfield", False):
            self.hopfield = ModernHopfield(
                hv_dim=mv_dim,
                internal_dim=CONFIG.get("hopfield_internal", 128),
                weights=self._extract(weights, "hopfield") if weights else None,
            )
            self._hopfield_mode = "modern_mv"
        else:
            self.hopfield = SandboxHopfieldMemory(
                attractor_dim=CONFIG.get("hopfield_attractor_dim", 256),
                query_dim=d_model // 2,
                pattern_projection_dim=CONFIG.get("hopfield_pattern_dim", 512),
                beta=CONFIG.get("hopfield_beta", 4.0),
                weights=self._extract(weights, "hopfield") if weights else None,
            )
            self._hopfield_mode = "sandbox_q"

    # ── Weight extraction helpers ────────────────────────────────────────────

    @staticmethod
    def _extract(weights: dict, prefix: str) -> dict:
        """Extract sub-dict with keys matching 'prefix.*' → stripped key."""
        if weights is None:
            return None
        p = prefix + "."
        return {k[len(p):]: v for k, v in weights.items() if k.startswith(p)}

    @staticmethod
    def _extract_block(weights: dict, idx: int) -> dict:
        """Extract per-block weights for VersorMemMambaBlock[idx]."""
        if weights is None:
            return None
        prefix = f"blocks.{idx}."
        raw = {k[len(prefix):]: v for k, v in weights.items() if k.startswith(prefix)}

        # Sub-group into gpa / mamba / note_block / cross_attn + norms
        block_w = {}

        # GPA
        gpa_keys = {k[4:]: v for k, v in raw.items() if k.startswith("gpa.")}
        if gpa_keys:
            # Remap torch Linear names → engine names
            remap = {
                "W_q.weight": "W_q", "W_q.bias": "W_q_bias",
                "W_k.weight": "W_k", "W_k.bias": "W_k_bias",
                "W_v.weight": "W_v", "W_v.bias": "W_v_bias",
                "W_out.weight": "W_out", "W_out.bias": "W_out_bias",
                "scalar_weight": "scalar_weight",
                "bivector_weight": "bivector_weight",
            }
            block_w["gpa"] = {remap.get(k, k): v for k, v in gpa_keys.items()}

        # Mamba
        mamba_keys = {k[6:]: v for k, v in raw.items() if k.startswith("mamba.")}
        if mamba_keys:
            block_w["mamba"] = mamba_keys

        # NoteBlock
        nb_keys = {k[11:]: v for k, v in raw.items() if k.startswith("note_block.")}
        if nb_keys:
            remap_nb = {
                "importance_scorer.weight": "importance_scorer_weight",
                "importance_scorer.bias":   "importance_scorer_bias",
                "compressor.weight":        "compressor_weight",
                "compressor.bias":          "compressor_bias",
            }
            block_w["note_block"] = {remap_nb.get(k, k): v for k, v in nb_keys.items()}

        # CrossAttn
        ca_keys = {k[11:]: v for k, v in raw.items() if k.startswith("cross_attn.")}
        if ca_keys:
            block_w["cross_attn"] = ca_keys

        # LayerNorms — expose at block level
        for key in ["norm1.weight", "norm1.bias", "norm2.weight", "norm2.bias", "norm3.weight", "norm3.bias"]:
            if key in raw:
                block_w[key.replace(".", "_")] = raw[key]

        return block_w

    def _extract_smoe(self, weights: dict) -> dict:
        """Extract SMoE-HE weights into the flat format expected by the class."""
        if weights is None:
            return None
        prefix = "smoe_he."
        raw = {k[len(prefix):]: v for k, v in weights.items() if k.startswith(prefix)}

        smoe_w = {}
        # Gate
        if "gate.weight" in raw: smoe_w["gate_weight"] = raw["gate.weight"]
        if "gate.bias"   in raw: smoe_w["gate_bias"]   = raw["gate.bias"]

        # Experts
        for k, v in raw.items():
            # e.g. experts.0.potential.0.weight
            parts = k.split(".")
            if len(parts) >= 4 and parts[0] == "experts":
                i     = parts[1]
                layer = parts[3]   # '0' or '2'
                kind  = parts[4]   # 'weight' or 'bias'
                smoe_w[f"expert_{i}_potential_{layer}_{kind}"] = v

        return smoe_w

    # ── Linear utility ───────────────────────────────────────────────────────

    @staticmethod
    def _linear(x: np.ndarray, W: np.ndarray, b: np.ndarray) -> np.ndarray:
        return x @ W.T + b

    # ── Hopfield bootstrap ───────────────────────────────────────────────────

    def _maybe_bootstrap_hopfield(self, mv_states: np.ndarray) -> None:
        """Bootstrap Hopfield from mv_states if not yet seeded (modern_mv mode only)."""
        if self.hopfield.stored_patterns.shape[0] == 0:
            if self._hopfield_mode == "modern_mv":
                seeds = mv_states.reshape(-1, mv_states.shape[-1])[:64]
                if seeds.shape[0] > 0:
                    self.hopfield.store(seeds)
            # sandbox_q: wait for external seed_from_redis() call

    # ── Forward ──────────────────────────────────────────────────────────────

    def forward(self, x: np.ndarray, domain_name: str) -> dict:
        """Run the NoumenalEngine and return outputs including the Rosetta vector.

        Args:
            x:           [B, T, in_dim] float32 — raw sensor / kinematic input.
            domain_name: one of DOMAINS keys.
        Returns:
            dict:
              predicted_next_state  [B, T, 32]   — predicted next multivector
              mv_states             [B, T, 32]   — bridge output
              hamiltonian           [B, T]       — H(q, p) for conservation check
              q                     [B, T, d/2]  — position phase-space coord
              p                     [B, T, d/2]  — momentum phase-space coord
              grades                dict         — grade-sliced predicted_mv
              hopfield_energy       [B, T]       — attractor proximity energy
              rosetta_vector        [2048]       — FLAT FP32 for llama_batch C-array
                                                  (mean over B and T)
        """
        x = np.asarray(x, dtype=np.float32)

        # 1. Bridge → Cl(4,1) manifold
        mv_states = self.bridges[domain_name](x)          # [B, T, 32]
        self._maybe_bootstrap_hopfield(mv_states)

        # 2. Input projection
        h = self._linear(mv_states, self.W_input, self.b_input)  # [B, T, d_model]

        # 3. Backbone
        for block in self.blocks:
            h = block(h)                                          # [B, T, d_model]

        # 4. Phase-space head → split q, p
        latent_phase = self._linear(h, self.W_phase, self.b_phase)  # [B, T, d_model]
        d_half = latent_phase.shape[-1] // 2
        q = latent_phase[..., :d_half]                            # [B, T, d_model/2]
        p = latent_phase[..., d_half:]                            # [B, T, d_model/2]

        # 5. SMoE-HE Hamiltonian evolution
        q_next, p_next = self.smoe_he(q, p)

        # 6. Rotor head: → predicted multivector [B, T, 32]
        combined     = np.concatenate([q_next, p_next], axis=-1)
        predicted_mv = self._linear(combined, self.W_rotor, self.b_rotor)

        # 7. Hamiltonian value for conservation monitoring
        hamiltonian = self.smoe_he.compute_hamiltonian(q, p)

        # 7. Grade projection — dict {grade_idx → [..., grade_size]}
        grades = {g: self.grade_proj.get_grade(predicted_mv, g) for g in range(6)}

        # 9. Hopfield energy
        if self._hopfield_mode == "sandbox_q":
            hopfield_energy = self.hopfield.compute_energy(q)
        else:
            hopfield_energy = self.hopfield.energy(predicted_mv)

        # ── ROSETTA BRIDGE ───────────────────────────────────────────────────
        # predicted_mv: [B, T, 32] → rosetta_head → [B, T, 2048]
        # Mean over batch and time → [2048] flat vector for C-array injection
        mv_flat      = predicted_mv.reshape(-1, predicted_mv.shape[-1])  # [B*T, 32]
        rosetta_2048 = self._linear(mv_flat, self.W_rosetta, self.b_rosetta)  # [B*T, 2048]
        rosetta_vec  = rosetta_2048.mean(axis=0).astype(np.float32)           # [2048]

        return {
            "predicted_next_state": predicted_mv,
            "mv_states":            mv_states,
            "hamiltonian":          hamiltonian,
            "q":                    q,
            "p":                    p,
            "grades":               grades,
            "hopfield_energy":      hopfield_energy,
            "rosetta_vector":       rosetta_vec,
        }

    def __call__(self, x: np.ndarray, domain_name: str) -> dict:
        return self.forward(x, domain_name)

    def load_weights(self, state_dict: dict) -> None:
        """Load weights from a flat numpy state_dict (extracted from .pth).

        Usage:
            import torch
            ckpt = torch.load("c2_baseline_30k.pth", map_location="cpu")
            sd   = {k: v.numpy() for k, v in ckpt["model_state"].items()}
            engine.load_weights(sd)
        """
        self.__init__(self.domains, weights=state_dict)
