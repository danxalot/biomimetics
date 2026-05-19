# Mamba-3 NumPy Port Spec — V3 Student (65k)

Extracted from `mamba_ssm/modules/mamba3.py` (state-spaces/mamba, main branch)
and `mamba_ssm/ops/triton/mamba3/mamba3_siso_step.py`.

**Config:** d_model=768, d_state=256, headdim=64, ngroups=1, chunk_size=32,
rope_fraction=1.0, is_mimo=False, is_outproj_norm=False

Derived internals:
- d_inner = 2 × 768 = **1536**
- nheads = 1536 / 64 = **24**
- num_bc_heads = ngroups = **1**
- mimo_rank = **1** (is_mimo=False)
- rotary_dim_divisor = int(2/1.0) = **2**
- split_tensor_size = int(256 × 1.0) = **256** (even, no adjustment)
- num_rope_angles = 256 // 2 = **128**

---

## CORRECTIONS to V3_DEPLOYMENT_TASKS.md Section 2

The following keys listed in the task doc **DO NOT EXIST** in the npz:

| Incorrect entry | Reality |
|---|---|
| `layers.N.mamba.A_log or A (24,)` | **No stored A parameter.** A is derived at runtime from the `dd_A` segment of `in_proj` output via `-softplus(dd_A)`. |
| `layers.N.mamba.conv1d.*` | **No conv1d in Mamba-3.** The causal conv was removed. |
| `layers.N.mamba.norm.*` | **Only exists if `is_outproj_norm=True`.** Our config uses `is_outproj_norm=False` (default). |

**Actual 12 keys per layer × 32 layers = 384 total:**

| Key | Shape |
|---|---|
| `layers.N.norm.weight` | (768,) |
| `layers.N.norm.bias` | (768,) |
| `layers.N.A_log` | (12,) — **vestigial** — load, ignore |
| `layers.N.dt_bias` | (12,) — **vestigial** — load, ignore |
| `layers.N.mamba.in_proj.weight` | (3784, 768) |
| `layers.N.mamba.dt_bias` | (24,) |
| `layers.N.mamba.B_bias` | (24, 1, 256) |
| `layers.N.mamba.C_bias` | (24, 1, 256) |
| `layers.N.mamba.B_norm.weight` | (256,) |
| `layers.N.mamba.C_norm.weight` | (256,) |
| `layers.N.mamba.D` | (24,) |
| `layers.N.mamba.out_proj.weight` | (768, 1536) |

---

## 1. in_proj Output Split

```python
d_in_proj = 2*d_inner + 2*d_state*num_bc_heads*mimo_rank + 3*nheads + num_rope_angles
           = 2*1536   + 2*256*1*1                         + 3*24     + 128
           = 3072     + 512                                + 72       + 128
           = 3784
```

Split order (dim=-1):

```
[ z       | x       | B    | C    | dd_dt | dd_A | trap | angles ]
[ 1536    | 1536    | 256  | 256  | 24    | 24   | 24   | 128    ]
```

After split, reshape:
- `z`: (B, L, 24, 64) via `rearrange("b l (h p) -> b l h p", p=64)`
- `x`: (B, L, 24, 64) same
- `B`: (B, L, 1, 1, 256) via `rearrange("b l (r g n) -> b l r g n", r=1, g=1)` [SISO: squeeze r,g → (B,L,1,256)]
- `C`: (B, L, 1, 1, 256) same
- `dd_dt`: (B, L, 24)
- `dd_A`: (B, L, 24)
- `trap`: (B, L, 24) → rearranged to (B, 24, L)
- `angles`: (B, L, 24, 128) via `unsqueeze(-2).expand(-1,-1,nheads,-1)`

---

## 2. No conv1d

Mamba-3 does **not** have a causal conv1d layer. The `trap` parameter (trapezoidal
integration) replaces the conv's smoothing role.

---

## 3. dt / A Activation

```python
# From mamba3.py forward():
_A  = -F.softplus(dd_A.to(float32))         # (B, L, 24), always negative
_A  = torch.clamp(_A, max=-A_floor)          # A_floor = 1e-4, so A ≤ -1e-4
DT  = F.softplus(dd_dt + self.dt_bias)       # (B, L, 24), always positive
ADT = _A * DT                                # (B, L, 24), always negative
```

NumPy equivalents:
```python
A   = -np.log1p(np.exp(dd_A.astype(np.float32)))   # = -softplus(dd_A)
A   = np.minimum(A, -1e-4)                           # clamp
DT  = np.log1p(np.exp(dd_dt + dt_bias))              # = softplus(dd_dt + dt_bias)
ADT = A * DT
```

---

## 4. RoPE

rope_fraction=1.0 → rotates ALL 256 state dimensions (128 pairs).

**Angle accumulation (per position, per head):**
```
raw_angle[t] = tanh(angles[t]) * π * DT[t]   # angles from in_proj last 128 dims
angle_state[t] = (angle_state[t-1] + raw_angle[t]) mod 2π
```
angle_state shape: (nheads=24, num_rope_angles=128). Initialised to zeros.

**Pair-wise rotation** applied to both Q (=C+C_bias) and K (=B+B_bias):
- For each pair index i ∈ [0, 128), θ_i = angle_state[head, i]
- Input pair: (q[2i], q[2i+1])
- Output: (q[2i]·cos θ_i − q[2i+1]·sin θ_i, q[2i]·sin θ_i + q[2i+1]·cos θ_i)

Both Q and K are rotated by the **same** θ (not conjugate).

```python
def apply_rope(v, theta):
    """v: (..., 256), theta: (..., 128) → rotated v same shape."""
    v0 = v[..., 0::2]   # even indices
    v1 = v[..., 1::2]   # odd indices
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    out = np.empty_like(v)
    out[..., 0::2] = v0 * cos_t - v1 * sin_t
    out[..., 1::2] = v0 * sin_t + v1 * cos_t
    return out
```

---

## 5. B/C Path (order matters)

```
1. B_raw, C_raw = in_proj output segments  (B, L, 256) each [after SISO squeeze]
2. B_norm_out = rms_norm(B_raw, B_norm.weight)   # RMSNorm, no bias
3. C_norm_out = rms_norm(C_raw, C_norm.weight)
4. B_biased = B_norm_out + B_bias[head]           # add per-head bias (inside kernel)
5. C_biased = C_norm_out + C_bias[head]
6. K[t] = apply_rope(B_biased, angle_state[t])    # rotated
7. Q[t] = apply_rope(C_biased, angle_state[t])    # same angles
```

B_bias shape in npz: (24, 1, 256). When adding to B per head: `B_bias[h, 0, :]` (256,).
C_bias shape in npz: (24, 1, 256). Same convention.

RMSNorm (no bias):
```python
def rms_norm(x, weight, eps=1e-5):
    """x: (..., d), weight: (d,) → same shape."""
    rms = np.sqrt(np.mean(x.astype(np.float32)**2, axis=-1, keepdims=True) + eps)
    return (x / rms) * weight
```

---

## 6. Selective Scan Recurrence

From `mamba3_siso_step.py` kernel (ground truth for the recurrence):

**State shape:** h: (nheads=24, headdim_v=64, d_state=256) — outer product space.

Per head h, per time step t:

```python
alpha   = exp(ADT[t, h])               # scalar, ∈ (0, 1)
trap_t  = sigmoid(trap_raw[t, h])      # scalar, ∈ (0, 1)
beta    = alpha * DT[t, h] * (1 - trap_t)   # weight for prev (x, K) pair
gamma   = trap_t * DT[t, h]                 # weight for curr (x, K) pair

# x = V (headdim=64 values), K = rotated B (d_state=256)
delta_h = beta  * x[t-1, h, :, None] * K[t-1, h, None, :]   # (64, 256)
        + gamma * x[t,   h, :, None] * K[t,   h, None, :]   # (64, 256)

h_state[t] = alpha * h_state[t-1] + delta_h                  # (64, 256)

# Output for this head:
y[t, h] = h_state[t] @ Q[t, h]   # (64, 256) @ (256,) = (64,)
y[t, h] += D[h] * x[t, h]        # skip connection (scalar D per head)
y[t, h] *= silu(z[t, h])         # z: (64,) gate
```

**Key trapezoidal detail:** the SSM update uses BOTH the current `(x_t, K_t)` and
the previous `(x_{t-1}, K_{t-1})`, weighted by gamma and beta. This requires
carrying `x_{t-1}` and `K_{t-1}` (= v_state, k_state) across steps.

At t=0: `x_{-1} = 0`, `K_{-1} = 0` (zero-initialised states).

silu: `silu(x) = x * sigmoid(x) = x / (1 + exp(-x))`

---

## 7. Output Gate and Projection

```python
# After scan, y: (B, L, nheads=24, headdim=64)
y = y * silu(z)                    # z: (B, L, 24, 64) — applied per-element inside scan

# Reshape for out_proj:
y = y.reshape(B, L, 1536)         # (B, L, d_inner)

out = y @ out_proj.weight.T       # (B, L, 768) — out_proj.weight: (768, 1536)
```

No norm before out_proj (is_outproj_norm=False).

---

## 8. Full Layer Forward (VersorMemMambaBlock_v3)

```python
residual = x                                  # (B, T, 768)
h = layer_norm(x, norm.weight, norm.bias)     # standard LayerNorm, (B, T, 768)
h = mamba3_forward(h)                         # (B, T, 768)
x = residual + residual_scale * h            # residual_scale = 1/sqrt(2*32) = 0.125
```

Stack: 32 layers in sequence.

---

## 9. W&B Ground State (T5.5 anchor)

Zero input `zeros(1, 64, 768)` through the stack produces **all-zeros output** because:
- LayerNorm of zeros (with bias) = bias; if bias=0 (init) → 0 → in_proj → 0
- All segments from in_proj = 0 → x=0, so B*x=0 and D*x=0 regardless of biases
- Therefore h_state stays 0, y=0, residual=0

W&B `ground_state/post_mc_jepa/*` values confirm this (all zero except entropy):
```
mean    = 0.0
std     = 0.0
norm    = 0.0
min     = 0.0
max     = 0.0
entropy = 10.803   # = log(768 * 64) = log(49152), entropy of uniform softmax over zeros
```

T5.5 is trivially satisfied by any numerically correct implementation.
The load-bearing verification is T5.1 (scan equivalence).

---

## 10. Implementation Notes for numpy_mamba3.py

### scan_recurrent (deployed path, @numba.njit)

Loop over T. Track `h_state` (24, 64, 256), `x_prev` (24, 64), `K_prev` (24, 256).
All FP32. Apply angle accumulation at each step to get rotated K_t, Q_t.

### scan_quadratic (verification path)

Build lower-triangular cumulative-decay matrix L[t, s] = ∏_{i=s+1}^{t} alpha_i.
For trapezoidal: the input contribution at position s to position t includes both
`gamma_s * (x_s ⊗ K_s)` and `beta_s * (x_{s-1} ⊗ K_{s-1})` scaled by L[t,s].
Then y_t = Σ_s L[t,s] * contribution_s, contracted with Q_t.

### Numerical precision

The Triton kernel uses bfloat16 for the state dot product and float32 for
state accumulation. The NumPy port should use float32 throughout.
State accumulation: float64 for the (64, 256) matrix if precision issues arise.
