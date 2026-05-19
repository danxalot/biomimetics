"""Inference-time configuration — NumPy runtime.

Direct port of Gold_Standard_Archive/pytorch/config.py.
All DEVICE and torch references removed. FP32 strict. No QAT.
Single source of truth for all CONFIG[...] reads across the numpy/ inference package.
"""
import os

# Cl(4,1) multivector dimension breakdown (32D total):
#   Grade 0: scalar          → indices [0:1]   (1 component)
#   Grade 1: vectors         → indices [1:6]   (5 components)
#   Grade 2: bivectors       → indices [6:16]  (10 components)
#   Grade 3: trivectors      → indices [16:26] (10 components)
#   Grade 4: quadvectors     → indices [26:31] (5 components)
#   Grade 5: pseudoscalar    → indices [31:32] (1 component)

CONFIG = {
    # ── Algebra ──
    "algebra":          "Cl(4,1)",
    "mv_dim":           32,
    "embed_dim":        256,
    "n_heads":          8,
    "n_layers":         6,

    # ── MemMamba-3 ──
    "mamba_d_model":    256,
    "mamba_d_state":    256,
    "mamba_d_conv":     4,
    "mamba_expand":     2,
    "mamba_dt_min":     0.01,
    "mamba_dt_max":     1.0,
    "mamba_dt_init":    "constant",
    "mamba_dt_scale":   0.1,
    "note_block_threshold": 0.7,
    "cross_layer_interval": 4,

    # ── Hamiltonian (Akasha 2) ──
    "n_experts":        4,
    "symplectic_dt":    0.1,

    # ── Quantization (inference: disabled) ──
    "qat_enabled":      False,
    "qat_warmup_steps": 5000,

    # ── Training (retained for checkpoint compatibility, not used at runtime) ──
    "batch_size":       16,
    "lr_max":           3e-4,
    "weight_decay":     1e-4,
    "total_steps":      30000,
    "warmup_steps":     5000,
    "smoe_frozen":      True,
    "gradient_clip":    1.0,
    "num_workers":      2,
    "seq_len":          128,

    # ── Loss weights ──
    "alpha_rotor":      0.4,
    "alpha_ham":        0.3,
    "alpha_lyap":       0.2,
    "alpha_hopfield":   0.1,
    "domain_ham_weight": {
        "susy": 1.5, "totem": 1.5,
        "jepa_wms": 0.0, "jepa_intuitive_physics": 0.0,
    },
    "alpha_jepa_cosine":        0.5,
    "ema_decay_init":           0.99,
    "ema_decay_final":          0.999,
    "ema_decay_warmup_steps":   5000,
    "domain_freq_weight": {
        "thermodynamics":         0.7,
        "doublePendulum":         1.0,
        "kth_flow":               1.0,
        "emf_field":              1.0,
        "quantum_spin":           1.2,
        "susy":                   1.3,
        "totem":                  1.3,
        "relativity":             1.5,
        "jepa_wms":               1.5,
        "jepa_intuitive_physics": 1.5,
    },
    "gradient_clip_rotor":  0.5,
    "rotor_param_patterns": ("rotor_head", "bridge"),

    # ── Safety ──
    "rewind_loss_threshold":    50.0,
    "rewind_max_attempts":      3,
    "rewind_lr_decay":          0.5,
    "plateau_window":           5000,
    "plateau_min_improvement":  0.001,
    "plateau_patience":         3,

    # ── Infrastructure ──
    "checkpoint_dir": os.environ.get("CHECKPOINT_DIR", "/kaggle/working/checkpoints"),
    "data_dir":       os.environ.get("DATA_DIR", "/kaggle/input/pythia-kinematics"),
    "wandb_project":  "Pythia-Phase-C2",
    "redis_url":      os.environ.get("REDIS_URL", "redis://redis_hdc:6379"),

    # ── Rosetta Bridge (inference) ──
    # The final output of the NoumenalEngine must be a 2048D FP32 flat vector
    # for direct injection into llama_batch C-array.
    "rosetta_output_dim":   2048,
    "rosetta_dtype":        "float32",
}

# Domain → input feature dim contract.
# Parity with pytorch/config.py DOMAINS dict — do not alter.
DOMAINS = {
    "doublePendulum":           8,
    "jepa_intuitive_physics":   32,
    "jepa_wms":                 32,
    "kth_flow":                 8,
    "emf_field":                8,
    "quantum_spin":             8,
    "relativity":               8,
    "thermodynamics":           8,
    "susy":                     32,
    "totem":                    32,
}

# Cl(4,1) grade index slices — canonical reference used by grade_projection.py
GRADE_SLICES = {
    0: slice(0, 1),
    1: slice(1, 6),
    2: slice(6, 16),
    3: slice(16, 26),
    4: slice(26, 31),
    5: slice(31, 32),
}
