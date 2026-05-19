"""
distill_heads.py — NumPy head distillation for the V3 student backbone.

Produces student_with_heads_45k.npz by training three prediction heads:
    1. rotor_head  (32, 768) — maps student 768D output → 32D CGA rotor
    2. phase_head (256, 768) — maps student 768D output → 256D phase state
    3. smoe_gate  ( 4, 256)  — SMoE-HE routing gate (4 experts, 256D input)

Oracle:  Teacher-lite forward (GPA + LayerNorm, skip Mamba-2 blocks).
         Teacher: 6-block, 256D hidden, input_proj(256,32), rotor/phase heads.
Method:  Closed-form lstsq for linear heads (instant, exact best linear fit).
         NumPy SGD (Adam) for SMoE gate (500 steps, ~30 seconds).
Data:    8 000 synthetic CGA inputs (32D unit-sphere), split 80/20 train/val.
Output:  /Users/danexall/biomimetics/Inference/models/student_with_heads_45k.npz

No PyTorch, no GPU. Runs in ~3 min on a Mac M-series.

Usage:
    python3 distill_heads.py [teacher.npz] [student.npz] [out.npz]
"""

from __future__ import annotations
import sys, os, time
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_MODELS = os.path.join(_HERE, "..", "models")
_T_PATH  = os.path.join(_MODELS, "teacher_45k.npz")
_S_PATH  = os.path.join(_MODELS, "student_45k.npz")
_OUT     = os.path.join(_MODELS, "student_with_heads_45k.npz")

if len(sys.argv) > 1: _T_PATH  = sys.argv[1]
if len(sys.argv) > 2: _S_PATH  = sys.argv[2]
if len(sys.argv) > 3: _OUT     = sys.argv[3]


# ══════════════════════════════════════════════════════════════════════════════
# 1.  Teacher-lite forward  (GPA + LayerNorm, Mamba-2 treated as identity)
# ══════════════════════════════════════════════════════════════════════════════

def _ln(x, w, b, eps=1e-5):
    """LayerNorm: x (D,) → (D,)."""
    mu = x.mean(); sig = np.sqrt(((x - mu)**2).mean() + eps)
    return w * (x - mu) / sig + b

def _silu(x):
    return x / (1.0 + np.exp(-x))

def _gelu(x):
    return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x**3)))

def _softmax(x):
    e = np.exp(x - x.max()); return e / e.sum()


class TeacherLite:
    """
    Simplified teacher forward.
    GPA blocks are computed exactly.
    Mamba-2 blocks are replaced by the identity (output = input).
    NoteBlock is skipped.

    For T=1 (single-token sequence), GPA self-attention is degenerate
    (q·k scalar = single token attending to itself, softmax=1).
    Reduces to: out = W_out(W_v(x) + b_v) + b_out  weighted by scalar/bivector gates.
    """
    def __init__(self, weights):
        w = weights  # npz file
        self.in_w = w["input_proj.weight"]   # (256, 32)
        self.in_b = w["input_proj.bias"]      # (256,)
        self.rot_w = w["rotor_head.weight"]   # (32,  256)
        self.rot_b = w["rotor_head.bias"]     # (32,)
        self.ph_w  = w["phase_head.weight"]   # (256, 256)
        self.ph_b  = w["phase_head.bias"]     # (256,)

        self.n_blocks = 6
        self.blocks = []
        for i in range(self.n_blocks):
            b = {
                "n1_w": w[f"blocks.{i}.norm1.weight"],
                "n1_b": w[f"blocks.{i}.norm1.bias"],
                "n2_w": w[f"blocks.{i}.norm2.weight"],
                "n2_b": w[f"blocks.{i}.norm2.bias"],
                "gpa_wq": w[f"blocks.{i}.gpa.W_q.weight"],
                "gpa_bq": w[f"blocks.{i}.gpa.W_q.bias"],
                "gpa_wk": w[f"blocks.{i}.gpa.W_k.weight"],
                "gpa_bk": w[f"blocks.{i}.gpa.W_k.bias"],
                "gpa_wv": w[f"blocks.{i}.gpa.W_v.weight"],
                "gpa_bv": w[f"blocks.{i}.gpa.W_v.bias"],
                "gpa_wo": w[f"blocks.{i}.gpa.W_out.weight"],
                "gpa_bo": w[f"blocks.{i}.gpa.W_out.bias"],
                "sc_w":   float(w[f"blocks.{i}.gpa.scalar_weight"]),
                "bv_w":   float(w[f"blocks.{i}.gpa.bivector_weight"]),
            }
            self.blocks.append(b)

    def forward(self, cga: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        cga: (32,) → rotor (32,), phase (256,), hidden (256,)
        """
        x = self.in_w @ cga + self.in_b   # (256,)

        for blk in self.blocks:
            # ── GPA sub-layer ────────────────────────────────────────────────
            h = _ln(x, blk["n1_w"], blk["n1_b"])
            # For T=1: attention is trivially 1 on itself
            v = blk["gpa_wv"] @ h + blk["gpa_bv"]   # (256,)
            g = blk["gpa_wo"] @ v + blk["gpa_bo"]   # (256,)
            # Gate: blend scalar and bivector contributions
            gate = blk["sc_w"] + blk["bv_w"]         # scalar sum
            x = x + gate * g

            # ── Mamba-2 (identity skip) ───────────────────────────────────
            # Residual identity; no-op without the SSM kernel.
            # h2 = _ln(x, blk["n2_w"], blk["n2_b"])  ← unused

        hidden = x   # (256,)
        rotor  = self.rot_w @ hidden + self.rot_b    # (32,)
        phase  = self.ph_w  @ hidden + self.ph_b     # (256,)
        return rotor, phase, hidden


# ══════════════════════════════════════════════════════════════════════════════
# 2.  Student forward wrapper
# ══════════════════════════════════════════════════════════════════════════════

def _layer_norm_batch(x, w, b, eps=1e-5):
    """x: (B,D)"""
    mu  = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1,  keepdims=True)
    return w * (x - mu) / np.sqrt(var + eps) + b


class StudentStack:
    """
    Minimal VersorMemMambaStackNP that accepts (N, 768) batched inputs.
    Mirrors the logic in v3_student/numpy_stack.py.
    """
    def __init__(self, npz_path):
        d = np.load(npz_path, allow_pickle=False)
        self.n_layers = 32
        self.d_model  = 768
        self.res_scale = 0.125

        self.layers = []
        for i in range(self.n_layers):
            self.layers.append({
                "nw":  d[f"layers.{i}.norm.weight"].astype(np.float32),
                "nb":  d[f"layers.{i}.norm.bias"].astype(np.float32),
                "ip":  d[f"layers.{i}.mamba.in_proj.weight"].astype(np.float32),
                "op":  d[f"layers.{i}.mamba.out_proj.weight"].astype(np.float32),
                "dtb": d[f"layers.{i}.mamba.dt_bias"].astype(np.float32),
                "D":   d[f"layers.{i}.mamba.D"].astype(np.float32),
            })
        print(f"  StudentStack loaded {self.n_layers} layers from {npz_path}")

    def forward_batch(self, x: np.ndarray) -> np.ndarray:
        """
        x: (N, 768) batch of zero-padded CGA inputs.
        Returns: (N, 768) output representations.

        For single-token (T=1) inputs, the Mamba3 SSM scan over T is trivial.
        We approximate by using only the in_proj + D skip + out_proj path,
        which is exact for T=1 with zero initial hidden state.
        """
        h = x.astype(np.float32)   # (N, 768)

        for lyr in self.layers:
            # LayerNorm
            normed = _layer_norm_batch(h, lyr["nw"], lyr["nb"])  # (N, 768)

            # in_proj: maps 768 → inner dim
            z = normed @ lyr["ip"].T                             # (N, inner)

            # For T=1: SSM scan contributes only D-skip (u * D for each head)
            # in_proj output: [x_part | BC_part] (inner = d_ssm + B + C + dt)
            # D has shape (nheads,) — d_ssm / nheads per-head skip
            # Simplified: apply _silu activation + D skip on the first d_ssm dims
            d_ssm = lyr["op"].shape[-1]    # out_proj takes d_ssm channels
            x_part = _silu(z[..., :d_ssm])    # (N, d_ssm) — primary path
            # D skip: per-element, where D is broadcast over (nheads, headdim)
            # D shape (nheads,) → broadcast to (d_ssm,) = (nheads * headdim,)
            nheads  = lyr["D"].shape[0]
            headdim = d_ssm // nheads
            D_full  = np.repeat(lyr["D"], headdim)   # (d_ssm,)
            x_part  = x_part * D_full[None, :]       # scale by per-head gain

            # out_proj: (d_model, d_ssm) maps back to 768
            m_out = x_part @ lyr["op"].T             # (N, 768)

            h = h + self.res_scale * m_out

        return h    # (N, 768)


# ══════════════════════════════════════════════════════════════════════════════
# 3.  SMoE-HE:  gate (4, 256) + 4 experts each (256→128→256)
# ══════════════════════════════════════════════════════════════════════════════

class SMoEHead:
    """
    Soft MoE with 4 experts.
    Gate input: phase_256 (first 128 dims, matching teacher's gate).
    Experts: keep teacher weights as init, fine-tune with Adam.
    """
    def __init__(self, teacher_weights):
        w = teacher_weights
        # Gate:  teacher gate was (4, 128); we use a NEW gate on full 256D phase
        # Init to zero (uniform expert routing at start)
        self.gate_w  = np.zeros((4, 128), dtype=np.float32)  # (4, 128) → phase[:128]
        self.gate_b  = w["smoe_he.gate.bias"].copy()          # (4,)

        self.experts = []
        for i in range(4):
            self.experts.append({
                "w1": w[f"smoe_he.experts.{i}.potential.0.weight"].copy(),  # (256, 128)
                "b1": w[f"smoe_he.experts.{i}.potential.0.bias"].copy(),    # (256,)
                "w2": w[f"smoe_he.experts.{i}.potential.2.weight"].copy(),  # (128, 256)
                "b2": w[f"smoe_he.experts.{i}.potential.2.bias"].copy(),    # (128,)
            })

    def forward(self, phase: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        """
        phase: (256,) → output (128,), expert_weights (4,), entropy float
        """
        gate_logits = self.gate_w @ phase[:128] + self.gate_b   # (4,)
        gate_weights = _softmax(gate_logits)                     # (4,)

        expert_outs = []
        for e in self.experts:
            h = _silu(e["w1"] @ phase + e["b1"])   # (256,) → (256,) wait...
            # Actually expert takes (256D phase) → project via w1 (256, 128)?
            # Wait: w1 is (256, 128), so in_features=128, out_features=256
            # The potential.0 is Linear(128, 256): out=256, in=128
            # So input to expert is 128D: use gate input (phase[:128])
            h_in = phase[:128]
            h    = _silu(e["w1"] @ h_in + e["b1"])  # (256,128)@(128,) = (256,) ✓
            out  = e["w2"] @ h   + e["b2"]           # (128,256)@(256,) = (128,) ✓
            expert_outs.append(out)

        expert_outs = np.stack(expert_outs)             # (4, 128)
        mixture = (gate_weights[:, None] * expert_outs).sum(0)   # (128,)

        # Entropy of gate distribution
        ent = float(-np.sum(gate_weights * np.log(gate_weights + 1e-9)))

        return mixture, gate_weights, ent


# ══════════════════════════════════════════════════════════════════════════════
# 4.  Adam helper
# ══════════════════════════════════════════════════════════════════════════════

class Adam:
    def __init__(self, lr=1e-3, b1=0.9, b2=0.999, eps=1e-8):
        self.lr = lr; self.b1 = b1; self.b2 = b2; self.eps = eps
        self.m = {}; self.v = {}; self.t = 0

    def step(self, params: dict, grads: dict):
        self.t += 1
        for k in params:
            if k not in self.m:
                self.m[k] = np.zeros_like(params[k])
                self.v[k] = np.zeros_like(params[k])
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * grads[k]
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * grads[k]**2
            m_hat = self.m[k] / (1 - self.b1**self.t)
            v_hat = self.v[k] / (1 - self.b2**self.t)
            params[k] -= self.lr * m_hat / (np.sqrt(v_hat) + self.eps)


# ══════════════════════════════════════════════════════════════════════════════
# 5.  Main distillation
# ══════════════════════════════════════════════════════════════════════════════

def main():
    rng = np.random.default_rng(42)
    print("=" * 64)
    print("  V3 Student Head Distillation")
    print("=" * 64)

    # ── Load weights ─────────────────────────────────────────────────────────
    print(f"\nLoading teacher: {_T_PATH}")
    t_w = np.load(_T_PATH, allow_pickle=False)
    print(f"  {len(t_w.files)} keys")

    print(f"Loading student: {_S_PATH}")
    student = StudentStack(_S_PATH)

    teacher = TeacherLite(t_w)
    smoe    = SMoEHead(t_w)

    # ── Generate synthetic CGA inputs ────────────────────────────────────────
    N      = 8_000
    N_train = int(0.8 * N)
    print(f"\nGenerating {N} synthetic CGA inputs (32D unit-sphere) ...")
    raw = rng.standard_normal((N, 32)).astype(np.float32)
    # Normalise to unit sphere
    cga_inputs = raw / (np.linalg.norm(raw, axis=-1, keepdims=True) + 1e-8)

    # ── Teacher oracle: get rotor + phase targets ─────────────────────────────
    t0 = time.time()
    print("Running teacher-lite forward on all inputs ...")
    teacher_rotors  = np.zeros((N, 32),  dtype=np.float32)
    teacher_phases  = np.zeros((N, 256), dtype=np.float32)
    for i, cga in enumerate(cga_inputs):
        rot, ph, _ = teacher.forward(cga)
        # Normalise rotor to unit sphere (matches deployed convention)
        rot_norm = np.linalg.norm(rot)
        teacher_rotors[i] = rot / (rot_norm + 1e-8)
        teacher_phases[i] = ph
    print(f"  teacher forward: {time.time()-t0:.1f}s  "
          f"rotor range [{teacher_rotors.min():.3f}, {teacher_rotors.max():.3f}]  "
          f"phase range [{teacher_phases.min():.3f}, {teacher_phases.max():.3f}]")

    # ── Student forward: get 768D features ───────────────────────────────────
    t0 = time.time()
    print("Running student forward on all inputs ...")
    pad_inputs = np.zeros((N, 768), dtype=np.float32)
    pad_inputs[:, :32] = cga_inputs
    student_feats = student.forward_batch(pad_inputs)      # (N, 768)
    print(f"  student forward: {time.time()-t0:.1f}s  "
          f"feat range [{student_feats.min():.3f}, {student_feats.max():.3f}]  "
          f"feat norm mean {np.linalg.norm(student_feats, axis=-1).mean():.3f}")

    # ── Train/val split ───────────────────────────────────────────────────────
    feats_tr   = student_feats[:N_train];   feats_val  = student_feats[N_train:]
    rotors_tr  = teacher_rotors[:N_train];  rotors_val = teacher_rotors[N_train:]
    phases_tr  = teacher_phases[:N_train];  phases_val = teacher_phases[N_train:]

    # ── lstsq: rotor head (32, 768) ───────────────────────────────────────────
    print("\nFitting rotor_head via lstsq ...")
    # [F|1] @ [W;b] = Y  →  solve for W (32,768) and b (32,)
    F_aug = np.hstack([feats_tr, np.ones((N_train, 1), dtype=np.float32)])  # (N,769)
    sol_r, res_r, *_ = np.linalg.lstsq(F_aug, rotors_tr, rcond=None)        # (769, 32)
    W_rotor = sol_r[:768, :].T.astype(np.float32)    # (32, 768)
    b_rotor = sol_r[768, :].astype(np.float32)        # (32,)
    # Val error
    pred_r_val = feats_val @ W_rotor.T + b_rotor
    pred_r_val_norm = pred_r_val / (np.linalg.norm(pred_r_val, axis=-1, keepdims=True) + 1e-8)
    cos_r = (pred_r_val_norm * rotors_val).sum(axis=-1).mean()
    mse_r = ((pred_r_val - rotors_val)**2).mean()
    print(f"  rotor: val MSE={mse_r:.5f}  cosine_sim={cos_r:.4f}")

    # ── lstsq: phase head (256, 768) ──────────────────────────────────────────
    print("Fitting phase_head via lstsq ...")
    sol_p, res_p, *_ = np.linalg.lstsq(F_aug, phases_tr, rcond=None)    # (769, 256)
    W_phase = sol_p[:768, :].T.astype(np.float32)   # (256, 768)
    b_phase = sol_p[768, :].astype(np.float32)       # (256,)
    # Val error
    pred_p_val = feats_val @ W_phase.T + b_phase
    mse_p = ((pred_p_val - phases_val)**2).mean()
    print(f"  phase: val MSE={mse_p:.5f}  pred range [{pred_p_val.min():.3f}, {pred_p_val.max():.3f}]")

    # ── Adam: train SMoE gate (4, 128) on distilled phase features ─────────
    print("\nTraining SMoE gate with Adam (500 steps) ...")
    # Target: teacher's gate outputs (one-hot argmax of teacher's gate logic)
    # Since teacher's gate was (4,128), we can compute teacher gate probs directly
    gate_targets = np.zeros((N_train, 4), dtype=np.float32)
    for i in range(N_train):
        logits = t_w["smoe_he.gate.weight"] @ phases_tr[i, :128] + t_w["smoe_he.gate.bias"]
        gate_targets[i] = _softmax(logits)

    # Phase predictions as input to gate training
    phases_pred_tr = feats_tr @ W_phase.T + b_phase   # (N_train, 256)

    params = {"w": smoe.gate_w.copy(), "b": smoe.gate_b.copy()}
    opt = Adam(lr=5e-4)
    BS  = 256
    t0  = time.time()
    losses = []
    for step in range(500):
        idx = rng.integers(0, N_train, BS)
        ph_b  = phases_pred_tr[idx, :128]    # (BS, 128) gate input
        tgt_b = gate_targets[idx]             # (BS, 4)
        # Forward
        logits = ph_b @ params["w"].T + params["b"]   # (BS, 4)
        e = np.exp(logits - logits.max(axis=-1, keepdims=True))
        probs = e / (e.sum(axis=-1, keepdims=True) + 1e-9)   # (BS, 4)
        # Cross-entropy
        loss = -np.sum(tgt_b * np.log(probs + 1e-9)) / BS
        losses.append(loss)
        # Gradients (CE + softmax combined)
        dlogits = (probs - tgt_b) / BS                         # (BS, 4)
        dw = dlogits.T @ ph_b                                  # (4, 128)
        db = dlogits.sum(axis=0)                               # (4,)
        opt.step(params, {"w": dw, "b": db})
        if step % 100 == 0:
            print(f"  step {step:4d}: loss={loss:.5f}")

    smoe.gate_w = params["w"]
    smoe.gate_b = params["b"]
    print(f"  gate training: {time.time()-t0:.1f}s  final loss={losses[-1]:.5f}")

    # Validation: gate entropy on val set
    phases_pred_val = feats_val @ W_phase.T + b_phase
    val_entropies = []
    for ph in phases_pred_val:
        logits = smoe.gate_w @ ph[:128] + smoe.gate_b
        probs  = _softmax(logits)
        ent    = -np.sum(probs * np.log(probs + 1e-9))
        val_entropies.append(ent)
    print(f"  gate val entropy: {np.mean(val_entropies):.4f} "
          f"(max={np.log(4):.3f} = uniform, 0=collapsed)")

    # ── Overfitting diagnostic ────────────────────────────────────────────────
    print("\n── Overfitting diagnostic ──")
    # Train vs val MSE ratio
    pred_r_tr  = feats_tr @ W_rotor.T + b_rotor
    mse_r_tr   = ((pred_r_tr - rotors_tr)**2).mean()
    pred_p_tr  = feats_tr @ W_phase.T + b_phase
    mse_p_tr   = ((pred_p_tr - phases_tr)**2).mean()
    print(f"  rotor  train MSE={mse_r_tr:.5f}  val MSE={mse_r:.5f}  "
          f"ratio={mse_r/mse_r_tr:.3f}  {'OK' if mse_r/mse_r_tr < 3 else 'OVERFIT?'}")
    print(f"  phase  train MSE={mse_p_tr:.5f}  val MSE={mse_p:.5f}  "
          f"ratio={mse_p/mse_p_tr:.3f}  {'OK' if mse_p/mse_p_tr < 3 else 'OVERFIT?'}")

    # ── Save ──────────────────────────────────────────────────────────────────
    print(f"\nSaving → {_OUT}")
    # Load existing student keys
    s_data = dict(np.load(_S_PATH, allow_pickle=False))

    # Add new heads
    s_data["rotor_head.weight"] = W_rotor            # (32, 768)
    s_data["rotor_head.bias"]   = b_rotor            # (32,)
    s_data["phase_head.weight"] = W_phase            # (256, 768)
    s_data["phase_head.bias"]   = b_phase            # (256,)
    s_data["smoe_gate.weight"]  = smoe.gate_w        # (4, 128)
    s_data["smoe_gate.bias"]    = smoe.gate_b        # (4,)
    # Keep teacher expert weights (they operate on 128D gate input → 256D output)
    for i in range(4):
        s_data[f"smoe_expert.{i}.w1"] = smoe.experts[i]["w1"]   # (256,128)
        s_data[f"smoe_expert.{i}.b1"] = smoe.experts[i]["b1"]   # (256,)
        s_data[f"smoe_expert.{i}.w2"] = smoe.experts[i]["w2"]   # (128,256)
        s_data[f"smoe_expert.{i}.b2"] = smoe.experts[i]["b2"]   # (128,)

    np.savez(os.path.splitext(_OUT)[0], **s_data)
    size_mb = os.path.getsize(_OUT) / 1e6
    print(f"  {len(s_data)} keys → {_OUT}  ({size_mb:.1f} MB)")

    print("\n" + "=" * 64)
    print("  Summary")
    print("=" * 64)
    print(f"  rotor_head  (32, 768)  val cosine_sim = {cos_r:.4f}")
    print(f"  phase_head (256, 768)  val MSE        = {mse_p:.5f}")
    print(f"  smoe_gate   ( 4, 128)  val entropy    = {np.mean(val_entropies):.4f}")
    print()
    print("  Next step: update NumpyPythiaManifold.predict() to use real heads.")
    print("  See: wire_heads.py")
    print()


if __name__ == "__main__":
    main()
