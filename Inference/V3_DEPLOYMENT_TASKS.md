# V3 Student (65k) — NumPy Deployment Task

Full, self-contained task spec. No GPU, no PyTorch, no external reference run.
Hand this to Gemini Flash; verification is built in via internal consistency.

---

## 0. Objective

Make the C2.6 65k Mamba-3 student (`pythia_c3_v3_65k.npz`) run inside the OCI
`neural_system` service as a pure-NumPy module, so the engine stops being
`None` and `/engine/state`, `/system/vitals`, `/energy`, `/resonance` work.

## 1. Hard constraints

- **NumPy only.** No PyTorch, no ONNX, no llama.cpp/GGUF in the container.
  `numba` is allowed (JIT for the scan loop); a NEON C extension is allowed if
  numba is insufficient.
- **CPU only.** OCI Ampere A1 ARM64. No inference GPU exists.
- **Reference available.** [/Users/danexall/biomimetics/pythia/Gold_Standard_Archive/Data/c2.6_data] data from wandb mc-jepa completed run. Correctness is established by internal
  consistency checks (Section 5), not by comparing to a trusted run.
- Modules mount as read-only volumes — no container rebuild to iterate on `.py`.

## 2. Architecture — fully resolved (do not re-derive)

Source of truth: `pythia/training/c2.2/50x0_train/mamba_v3.py`.

The deployed `pythia_c3_v3_65k.npz` is the `v3_student_state` of
`c2.6_mc_jepa_65k.pth`. It is a `VersorMemMambaStack_v3`: **32 layers**.

### Per-layer forward (exact)
```
residual = x                              # x: (B, T, 768)
h = LayerNorm(x)                           # layers.N.norm.{weight,bias} (768)
h = Mamba3(h)                              # layers.N.mamba.*
x = residual + (1/8) * h                   # residual_scale = 1/sqrt(2*32)
```
Stack forward = 32 layers in sequence. Final output: (B, T, 768).

- `layers.N.A_log (12,)`, `layers.N.dt_bias (12,)` — **VESTIGIAL.** Entropy-probe
  params, NEVER used in forward. Load to satisfy key-completeness, then ignore.

### The Mamba3 kernel (`layers.N.mamba.*`)
Real `mamba_ssm.modules.mamba3.Mamba3` with:
`d_model=768, d_state=256, headdim=64, ngroups=1, chunk_size=32,
rope_fraction=1.0 (full RoPE), is_mimo=False`.
Internal: `d_inner = 2*768 = 1536`, `n_internal_heads = 1536/64 = 24`.

npz keys (per layer):
```
layers.N.mamba.in_proj.weight    (3784, 768)   no bias
layers.N.mamba.conv1d.*          (vendor source: depthwise causal, d_conv=4)
layers.N.mamba.dt_bias           (24,)
layers.N.mamba.A_log  or  A      (24,)          per-head decay
layers.N.mamba.D                 (24,)          skip connection
layers.N.mamba.B_bias            (24, 1, 256)
layers.N.mamba.C_bias            (24, 1, 256)
layers.N.mamba.B_norm.weight     (256,)         RMSNorm on B
layers.N.mamba.C_norm.weight     (256,)         RMSNorm on C
layers.N.mamba.norm.*            (gated RMSNorm before out_proj)
layers.N.mamba.out_proj.weight   (768, 1536)    no bias
```
**The exact `in_proj` output split (3784 = z + xBC + dt + ...) MUST be read
from the reference source (Section 3) — never inferred by arithmetic.**

## 3. T1 — Obtain the reference source (read-only, no execution)

Clone or browse `github.com/state-spaces/mamba`. Copy into
`Inference/v3_student/reference/`:
- `mamba_ssm/modules/mamba3.py`
- any helper it imports for the **non-Triton reference path** (layernorm /
  RMSNorm, RoPE, the reference scan).

From `mamba3.py`, extract and write down precisely (this is the port spec):
1. `in_proj` output split — order and width of each segment (z, x, B, C, dt, …).
2. conv1d: which segments it is applied to, kernel size, causal padding.
3. `dt` activation: `softplus(dt + dt_bias)`, any clamping.
4. RoPE: how `rope_fraction=1.0` rotates the state; the frequency schedule.
5. B/C path: `B_norm`/`C_norm` (RMSNorm) and `B_bias`/`C_bias` — apply order.
6. The selective-scan recurrence: `h_t = decay_t*h_{t-1} + B_t*x_t`,
   `y_t = C_t·h_t + D*x_t` — exact einsum shapes for 24 heads × headdim 64 ×
   d_state 256, ngroups=1.
7. Output gate: `y = y * silu(z)`, the gated `norm`, then `out_proj`.

> If the W&B run `Pythia-Phase-C3` synced online, `ground_state/post_mc_jepa/*`
> on wandb.ai is an extra free check (zero-input forward stats). W&B is cloud-
> hosted — it survives the GPU instance being destroyed. Optional; the task
> below does not depend on it.

## 4. Implementation

### T2 — `Inference/v3_student/numpy_mamba3.py`
Pure-NumPy `Mamba3` forward. Two scan implementations (both required — they
are the verification, see T5):
- **`scan_recurrent(...)`** — sequential loop over T. `@numba.njit`. This is the
  deployed inference path (also supports O(1) single-step streaming).
- **`scan_quadratic(...)`** — materialized form: build the lower-triangular
  cumulative-decay matrix `L` and compute `y` by matmul. Independent codepath.
Parameter names/shapes match the npz keys exactly.
RoPE in its own function `apply_rope(...)` (verified separately, T5).

### T3 — `Inference/v3_student/numpy_stack.py`
`VersorMemMambaStackNP`:
- Loads `pythia_c3_v3_65k.npz`. **Assert all 384 keys are consumed** — hard
  fail (raise) on any missing or leftover key. No silent skips.
- 32 layers, each: LayerNorm → `numpy_mamba3` → `residual + 0.125*h`.
- Vestigial `A_log`/`dt_bias` (the `(12,)` ones): loaded, unused.
- Public `forward(x)` → (B,T,768) and `step(x_t, state)` → streaming.

### T4 — `Inference/v3_student/loader.py`
Single entry point `load_v3_student(npz_path) -> VersorMemMambaStackNP`,
used by `neural_system` to replace `NumpyPythiaManifold`'s weight-loading.

## 5. T5 — Verification (no golden reference — internal consistency)

All checks must pass before wiring into `neural_system`.

1. **Scan equivalence (the core correctness proof).**
   `scan_recurrent` and `scan_quadratic` must produce identical output
   (atol=1e-5) on 20 random inputs. They are independent implementations of
   the same recurrence — agreement is strong evidence the scan math is right;
   a bug would have to be replicated identically in both, which is unlikely.

2. **RoPE sanity.** RoPE is an orthogonal rotation: applying angle θ then −θ
   returns the input (atol=1e-6); it preserves vector norm. Verify both.

3. **Key completeness.** Loader consumes exactly the 384 npz keys; 0 missing,
   0 leftover. (Catches the original teacher-vs-student schema bug.)

4. **Numerical health, per layer, on 10 random inputs:**
   - output finite — no NaN / Inf
   - variance > 1e-3 (flatline guard — matches the system's existing 0.001
     abort threshold)
   - L2 norm bounded — the 1/8 residual scale must keep norm stable across all
     32 layers (no blow-up, no decay-to-zero).

5. **Zero-input ground state — externally anchored.** Feed `zeros(1,64,768)`
   through the full stack. Its output mean/std/norm/entropy/max/min must MATCH
   (atol ~1e-3) the values logged by the real run in W&B:
   `ground_state/post_mc_jepa/*` (from `Pythia-Phase-C3` →
   `wandb-summary.json`). This is a real external gate — deterministic, no
   seed. NOTE: it is the *skeleton* check (zero input does not drive the
   signal-dependent scan), so it confirms LayerNorm/bias/dt_bias/D across all
   32 layers but NOT the scan dynamics — T5.1 remains the primary scan proof.

6. **conv1d causality.** Output at time t must not change when inputs at t' > t
   are perturbed. Verify on one sample.

## 6. T6 — Integrate into neural_system

- In `phenomenological_core.py`, replace `NumpyPythiaManifold`'s weight-loading
  with `load_v3_student(...)`. The engine object exposes `forward` / `step`.
- Keep the `is_ready` guard pattern; engine becomes ready only after a
  successful load + T5 pass.
- Update `/debug/engine`, `/engine/state`, `/system/vitals` to read from the
  new stack (32 layers, d_model 768).

## 7. T7 — Redeploy + independent fixes

- Rebuild the `neural_system` image (picks up the `/resonance` guard fix —
  `phenomenological_core.py:687` still calls `engine.absorb_pulse()` unguarded
  → HTTP 500 every pulse tick).
- Bring up `geometry_embedding` (port 8081, currently down — only a stale
  `embedding-1024` container, exited 13 days ago).

## 8. Final acceptance checklist

- [ ] T5.1 scan equivalence passes (recurrent == quadratic, atol 1e-5)
- [ ] T5.2 RoPE round-trip + norm-preservation passes
- [ ] T5.3 all 384 npz keys consumed, none skipped
- [ ] T5.4 per-layer: finite, variance > 1e-3, norm bounded across 32 layers
- [ ] T5.5 zero-input ground state matches W&B `ground_state/post_mc_jepa/*`
- [ ] T5.6 conv1d causality verified
- [ ] OCI `/engine/state` returns real hidden state, not `NoneType`
- [ ] OCI `/system/vitals` → `mamba_pulse_l2 > 0`, `hamiltonian_energy > 0`
- [ ] OCI `/energy` → status != `no_data`
- [ ] OCI `/resonance` POST → 200
- [ ] `geometry_embedding:8081/health` → healthy

## 9. Risk note

Without a golden reference, T5.1 (scan equivalence) is the load-bearing check.
It proves the *recurrence* is self-consistent but cannot prove the *spec* (the
in_proj split, RoPE schedule, B/C order) was read correctly from T1. Mitigation:
T1 must be done carefully against the actual `mamba3.py` source, and the port
should mirror it line-by-line. If outputs later look behaviorally wrong despite
T5 passing, the fault is almost certainly a T1 spec-reading error, not a scan
bug — re-audit T1 first.
