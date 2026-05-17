"""Canonical training-time configuration.

Single source of truth for all `CONFIG[...]` reads across the pytorch/ package.
Bundled into the Kaggle script verbatim — edit here, rebuild bundle, push.
"""
import os
import torch

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

CONFIG = {
    # ── Algebra ──
    "algebra": "Cl(4,1)",
    "mv_dim": 32,
    "embed_dim": 256,
    "n_heads": 8,
    "n_layers": 6,                  # Block count (NOT 128; 128 is state-dim)

    # ── MemMamba-3 ──
    "mamba_d_model": 256,
    "mamba_d_state": 256,           # Round 7.4: was 128. More state dims for trajectory mode tracking.
    "mamba_d_conv": 4,              # Round 7.4.1 (Hotfix): capped at 4 for causal_conv1d CUDA support.
    "mamba_expand": 2,
    # Round 7.4 — Δt aligned to symplectic_dt (physics step) instead of language-default ranges.
    "mamba_dt_min": 0.01,
    "mamba_dt_max": 1.0,
    "mamba_dt_init": "constant",
    "mamba_dt_scale": 0.1,
    "note_block_threshold": 0.7,
    "cross_layer_interval": 4,

    # ── Hamiltonian (Akasha 2) ──
    "n_experts": 4,
    "symplectic_dt": 0.1,

    # ── Quantization ──
    "qat_enabled": True,
    "qat_warmup_steps": 5000,

    # ── Training ──
    "batch_size": 16,
    "lr_max": 3e-4,
    "weight_decay": 1e-4,           # Round 7.4: bumped — now applied selectively (no decay on biases/norms/embeds)
    "total_steps": 30000,           # Round 7.4: bumped from 15K — C1→C2 grade-prior revision needs the budget
    "warmup_steps": 5000,           # Round 7.4: matches qat_warmup_steps so LR + QAT engage on same schedule.

    # Round 7.4 — SMoE-HE (Akasha experts) freeze for this run.
    # Per-expert/per-domain unfreezing happens in the Akasha phase.
    "smoe_frozen": True,
    "gradient_clip": 1.0,
    "num_workers": 2,
    "seq_len": 128,

    # ── Loss weights ──
    "alpha_rotor": 0.4,
    "alpha_ham": 0.3,
    "alpha_lyap": 0.2,
    "alpha_hopfield": 0.1,
    # Round 7.4 — per-domain Hamiltonian multiplier.
    # CERN ×1.5 (strict symmetry); JEPA ×0.0 (Hamiltonian is fictional for learned
    # representations — JEPA domains use stop-gradient + smooth-L1 + cosine SSL loss
    # in the rotor branch instead).
    "domain_ham_weight": {
        "susy": 1.5, "totem": 1.5,
        "jepa_wms": 0.0, "jepa_intuitive_physics": 0.0,
    },
    # JEPA SSL loss — cosine-similarity term weight relative to smooth-L1 (=1.0).
    "alpha_jepa_cosine": 0.5,
    # EMA target encoder (canonical JEPA teacher) — decay schedule and warmup.
    "ema_decay_init": 0.99,
    "ema_decay_final": 0.999,
    "ema_decay_warmup_steps": 5000,
    # Per-domain batch frequency weights (sampler).
    "domain_freq_weight": {
        "thermodynamics":          0.7,
        "doublePendulum":          1.0,
        "kth_flow":                1.0,
        "emf_field":               1.0,
        "quantum_spin":            1.2,
        "susy":                    1.3,
        "totem":                   1.3,
        "relativity":              1.5,
        "jepa_wms":                1.5,
        "jepa_intuitive_physics":  1.5,
    },
    # Round 7.4 — manifold-aware gradient clipping.
    "gradient_clip_rotor": 0.5,
    "rotor_param_patterns": ("rotor_head", "bridge"),

    # ── Safety ──
    "rewind_loss_threshold": 50.0,
    "rewind_max_attempts": 3,
    "rewind_lr_decay": 0.5,
    "plateau_window": 5000,
    "plateau_min_improvement": 0.001,
    "plateau_patience": 3,

    # ── Infrastructure ──
    "checkpoint_dir": os.environ.get("CHECKPOINT_DIR", "/kaggle/working/checkpoints"),
    "data_dir": os.environ.get("DATA_DIR", "/kaggle/input/pythia-kinematics"),
    "wandb_project": "Pythia-Phase-C2",
    "redis_url": os.environ.get("REDIS_URL", "redis://redis_hdc:6379"),
}

# Domain → input feature dim contract.
DOMAINS = {
    "doublePendulum": 8,
    "jepa_intuitive_physics": 32,
    "jepa_wms": 32,
    "kth_flow": 8,
    "emf_field": 8,
    "quantum_spin": 8,
    "relativity": 8,
    "thermodynamics": 8,
    "susy": 32,
    "totem": 32,
}
