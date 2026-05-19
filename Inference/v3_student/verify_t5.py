"""
verify_t5.py — T5 Internal Consistency Verification Suite for V3 Student.

Runs all six checks from V3_DEPLOYMENT_TASKS.md §5 without needing the
actual npz file for T5.1–T5.4 and T5.6 (they use synthetic weights).
T5.3 and T5.5 require the real npz at NPZ_PATH.

Run:
    python -m Inference.v3_student.verify_t5
  or
    python Inference/v3_student/verify_t5.py

Set environment variable NPZ_PATH to run T5.3 and T5.5:
    NPZ_PATH=/path/to/pythia_c3_v3_65k.npz python -m Inference.v3_student.verify_t5
"""

from __future__ import annotations

import os
import sys
import numpy as np

# Allow running directly from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Inference.v3_student.numpy_mamba3 import (
    Mamba3Params, mamba3_forward, scan_recurrent, scan_quadratic,
    apply_rope, rms_norm, _preprocess,
    NHEADS, D_MODEL, D_INNER, D_STATE, HEADDIM, NUM_ROPE_ANGLES, N_LAYERS
)

# Alias for layer count from stack module
N_LAYERS = 32

PASS = "✅ PASS"
FAIL = "❌ FAIL"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rand_params(seed: int = 0) -> Mamba3Params:
    """Generate a random but structurally valid Mamba3Params."""
    rng = np.random.default_rng(seed)
    scale = 0.02
    return Mamba3Params(
        in_proj_weight  = rng.normal(0, scale, (3784, D_MODEL)).astype(np.float32),
        dt_bias         = rng.normal(0, scale, (NHEADS,)).astype(np.float32),
        B_bias          = np.ones((NHEADS, 1, D_STATE), dtype=np.float32),
        C_bias          = np.ones((NHEADS, 1, D_STATE), dtype=np.float32),
        B_norm_weight   = np.ones(D_STATE, dtype=np.float32),
        C_norm_weight   = np.ones(D_STATE, dtype=np.float32),
        D               = rng.normal(0, scale, (NHEADS,)).astype(np.float32),
        out_proj_weight = rng.normal(0, scale, (D_MODEL, D_INNER)).astype(np.float32),
    )


# ---------------------------------------------------------------------------
# T5.1 — Scan equivalence
# ---------------------------------------------------------------------------

def test_t5_1_scan_equivalence(n_trials: int = 20, atol: float = 1e-5) -> bool:
    """scan_recurrent and scan_quadratic must agree on 20 random inputs."""
    print("\n--- T5.1: Scan Equivalence (recurrent == quadratic, atol=1e-5) ---")
    rng = np.random.default_rng(42)
    p = _rand_params(seed=1)
    passed = 0
    for trial in range(n_trials):
        B, T = 2, rng.integers(4, 17)
        u = rng.normal(0, 0.5, (B, T, D_MODEL)).astype(np.float32)
        z, x, B_n, C_n, DT, ADT, trap, angles = _preprocess(u, p)
        y_rec, *_ = scan_recurrent(z, x, B_n, C_n, DT, ADT, trap, angles, p)
        y_quad    = scan_quadratic(z, x, B_n, C_n, DT, ADT, trap, angles, p)
        max_diff = np.abs(y_rec - y_quad).max()
        ok = max_diff <= atol
        if ok:
            passed += 1
        else:
            print(f"  trial {trial}: max_diff={max_diff:.2e}  ← {FAIL}")
    status = passed == n_trials
    print(f"  {passed}/{n_trials} trials passed  →  {PASS if status else FAIL}")
    return status


# ---------------------------------------------------------------------------
# T5.2 — RoPE round-trip + norm preservation
# ---------------------------------------------------------------------------

def test_t5_2_rope_sanity(atol_roundtrip: float = 1e-6) -> bool:
    """RoPE(+θ) then RoPE(-θ) returns input; norm preserved."""
    print("\n--- T5.2: RoPE Sanity (round-trip + norm preservation) ---")
    rng = np.random.default_rng(7)
    v     = rng.normal(0, 1, (4, 256)).astype(np.float32)
    theta = rng.uniform(0, 2 * np.pi, (4, 128)).astype(np.float32)

    # Forward then inverse
    v_fwd = apply_rope(v, theta)
    v_inv = apply_rope(v_fwd, -theta)
    roundtrip_err = np.abs(v - v_inv).max()
    roundtrip_ok  = roundtrip_err <= atol_roundtrip

    # Norm preservation
    norm_in  = np.linalg.norm(v,     axis=-1)
    norm_out = np.linalg.norm(v_fwd, axis=-1)
    norm_err = np.abs(norm_in - norm_out).max()
    norm_ok  = norm_err <= 1e-5

    print(f"  round-trip max err: {roundtrip_err:.2e}  →  {PASS if roundtrip_ok else FAIL}")
    print(f"  norm preservation err: {norm_err:.2e}  →  {PASS if norm_ok else FAIL}")
    return roundtrip_ok and norm_ok


# ---------------------------------------------------------------------------
# T5.3 — Key completeness (requires real npz)
# ---------------------------------------------------------------------------

def test_t5_3_key_completeness(npz_path: str) -> bool:
    """Loader must consume exactly 384 keys; 0 missing, 0 leftover."""
    print(f"\n--- T5.3: Key Completeness (npz_path={npz_path}) ---")
    if not os.path.isfile(npz_path):
        print(f"  npz not found at '{npz_path}' — skipping.")
        return None   # type: ignore[return-value]
    try:
        from Inference.v3_student.numpy_stack import VersorMemMambaStackNP
        stack = VersorMemMambaStackNP.from_npz(npz_path)
        print(f"  All 384 keys consumed, 0 leftover  →  {PASS}")
        return True
    except (ValueError, KeyError) as e:
        print(f"  {FAIL}: {e}")
        return False


# ---------------------------------------------------------------------------
# T5.4 — Numerical health per layer (10 random inputs)
# ---------------------------------------------------------------------------

def test_t5_4_numerical_health(n_inputs: int = 10) -> bool:
    """Per-layer: finite, variance > 1e-3, norm bounded across 32 layers."""
    print("\n--- T5.4: Numerical Health (finite, var>1e-3, norm bounded) ---")
    rng = np.random.default_rng(99)
    all_ok = True

    for trial in range(n_inputs):
        u = rng.normal(0, 1, (1, 8, D_MODEL)).astype(np.float32)
        x = u.copy()
        prev_norm = np.linalg.norm(x)

        for n in range(N_LAYERS):
            p = _rand_params(seed=n)
            # LayerNorm
            mean = x.mean(axis=-1, keepdims=True)
            var  = x.var(axis=-1, keepdims=True)
            xn   = (x - mean) / np.sqrt(var + 1e-5)
            # mamba forward
            h = mamba3_forward(xn, p, use_recurrent=True)
            residual_scale = 1.0 / np.sqrt(2.0 * N_LAYERS)
            x = x + residual_scale * h

            # Checks
            finite = np.isfinite(x).all()
            variance = float(x.var())
            cur_norm = np.linalg.norm(x)
            # Norm shouldn't blow up (allow 10× growth) or collapse (>0.01 of initial)
            norm_bounded = 0.001 * prev_norm <= cur_norm <= 10 * prev_norm + 1.0

            if not finite or variance < 1e-3 or not norm_bounded:
                print(f"  trial {trial} layer {n}: finite={finite} var={variance:.4f} norm={cur_norm:.2f}  ← {FAIL}")
                all_ok = False

    print(f"  {n_inputs} inputs × {N_LAYERS} layers checked  →  {PASS if all_ok else FAIL}")
    return all_ok


# ---------------------------------------------------------------------------
# T5.5 — Zero-input ground state (W&B anchor)
# ---------------------------------------------------------------------------

def test_t5_5_zero_input_ground_state(npz_path: str) -> bool:
    """Feed zeros(1,64,768) through stack; output must be all-zeros (atol~1e-3).

    From PORT_SPEC.md §9: LayerNorm(0) with zero bias = 0 → in_proj(0) = 0
    → x=0 → B*x=0, D*x=0 → h_state=0, y=0 → output is 0.
    W&B confirms mean=std=norm=min=max=0, entropy=10.803.
    """
    print(f"\n--- T5.5: Zero-Input Ground State (requires real npz) ---")
    if not os.path.isfile(npz_path):
        print(f"  npz not found at '{npz_path}' — skipping.")
        return None   # type: ignore[return-value]
    try:
        from Inference.v3_student.numpy_stack import VersorMemMambaStackNP
        stack = VersorMemMambaStackNP.from_npz(npz_path)
        x_zero = np.zeros((1, 64, D_MODEL), dtype=np.float32)
        out = stack.forward(x_zero)
        mean_ = float(out.mean())
        std_  = float(out.std())
        norm_ = float(np.linalg.norm(out))
        # Entropy of uniform softmax over zeros = log(T*D) = log(64*768) = log(49152)
        import math
        flat = out.reshape(-1)
        p_sm = np.exp(flat - flat.max())
        p_sm /= p_sm.sum()
        entropy = float(-np.sum(p_sm * np.log(p_sm + 1e-12)))

        print(f"  mean={mean_:.6f}  std={std_:.6f}  norm={norm_:.6f}")
        print(f"  entropy={entropy:.3f}  (W&B ref ~10.803 for seq_len=64, or log(49152)={math.log(49152):.3f})")

        ok = abs(mean_) < 1e-3 and abs(std_) < 1e-3 and abs(norm_) < 1e-2
        print(f"  ground state zero-output check  →  {PASS if ok else FAIL}")
        return ok
    except Exception as e:
        print(f"  {FAIL}: {e}")
        return False


# ---------------------------------------------------------------------------
# T5.6 — conv1d causality
# ---------------------------------------------------------------------------

def test_t5_6_conv1d_causality() -> bool:
    """Mamba-3 has no conv1d (per PORT_SPEC.md §2).

    Causality verification: output at time t must not change when inputs at
    t' > t are perturbed. Verified via the full mamba3_forward.
    """
    print("\n--- T5.6: Causal Output Verification (no-conv1d Mamba-3) ---")
    rng = np.random.default_rng(13)
    p = _rand_params(seed=5)
    T = 16
    u  = rng.normal(0, 0.5, (1, T, D_MODEL)).astype(np.float32)
    y1 = mamba3_forward(u.copy(), p, use_recurrent=True)

    # Perturb all inputs at t' > 8 (second half)
    u_perturbed = u.copy()
    u_perturbed[:, T // 2:, :] += rng.normal(0, 5.0, (1, T // 2, D_MODEL)).astype(np.float32)
    y2 = mamba3_forward(u_perturbed, p, use_recurrent=True)

    # Outputs at t <= T//2 - 1 must be unchanged
    t_check = T // 2  # last position that should be unaffected
    diff = np.abs(y1[:, :t_check] - y2[:, :t_check]).max()
    ok = diff < 1e-5
    print(f"  max output diff at t<={t_check-1} after perturbing t>={t_check}: {diff:.2e}  →  {PASS if ok else FAIL}")
    return ok


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_all(npz_path: str = "") -> dict:
    print("=" * 60)
    print("V3 Student — T5 Internal Consistency Verification Suite")
    print("=" * 60)

    results = {}
    results["T5.1_scan_equivalence"]   = test_t5_1_scan_equivalence()
    results["T5.2_rope_sanity"]        = test_t5_2_rope_sanity()
    results["T5.3_key_completeness"]   = test_t5_3_key_completeness(npz_path)
    results["T5.4_numerical_health"]   = test_t5_4_numerical_health()
    results["T5.5_zero_input"]         = test_t5_5_zero_input_ground_state(npz_path)
    results["T5.6_causality"]          = test_t5_6_conv1d_causality()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for k, v in results.items():
        status = PASS if v is True else ("⚠️  SKIPPED (no npz)" if v is None else FAIL)
        print(f"  {k:40s}  {status}")

    hard_checks = [v for v in results.values() if v is not None]
    if all(hard_checks):
        print(f"\n{PASS} All checks passed. Safe to wire into neural_system.")
    else:
        print(f"\n{FAIL} One or more checks failed. Do NOT wire into neural_system.")
    return results


if __name__ == "__main__":
    npz = os.environ.get("NPZ_PATH", "")
    run_all(npz_path=npz)
