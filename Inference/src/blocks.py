"""VersorMemMambaBlock — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/blocks.py.
Architecture per block:
    GPA → SSM scan → (optional CrossTokenAttention) → NoteBlock → LayerNorm

Mamba is ported as a simplified linear SSM (inference-only: no selective scan
CUDA kernel). The SSM scan is implemented as a recurrent scan over the time
dimension using the SSD (State-Space Dual) formulation. This is exact for
inference (no approximation) and avoids any dependency on mamba_ssm or CUDA.

QAT / fake_quant: stripped — inference runtime is FP32 strict.
CrossTokenAttention: implemented via numpy matmul (no nn.MultiheadAttention).

Weight contract — per block, indexed by layer_idx:
    gpa.*:            see attention.py weight contract
    mamba.*:          see _MambaSSM weight contract below
    note_block.*:     see note_block.py weight contract
    norm1_weight/bias, norm2_weight/bias, norm3_weight/bias: [d_model]
    cross_attn.*:     optional, only if layer_idx in cross_attn_layers
"""
import math
import numpy as np
from .config import CONFIG
from .attention import GeometricProductAttention
from .note_block import NoteBlock


# ─────────────────────────────────────────────────────────────────────────────
# Minimal SSM inference kernel (Mamba-compatible)
# ─────────────────────────────────────────────────────────────────────────────

class _MambaSSM:
    """Inference-only SSM scan with Mamba1-compatible weight shapes.

    Implements the parallel prefix scan formulation for inference.
    Parameter shapes mirror Mamba1 (mamba_ssm.Mamba):
        in_proj:   [d_inner*2, d_model]  (fused x+z projection)
        conv1d:    [d_inner, 1, d_conv]
        x_proj:    [dt_rank+d_state*2, d_inner]
        dt_proj:   [d_inner, dt_rank]
        A_log:     [d_inner, d_state]
        D:         [d_inner]
        out_proj:  [d_model, d_inner]
    plus biases: in_proj_bias*, conv1d_bias, x_proj_bias*, dt_proj_bias, out_proj_bias*
    (* Mamba1 uses bias=False for in_proj and x_proj by default; included for compat)

    For Mamba2 checkpoints, weight_loader must remap to this interface.
    """

    def __init__(self, d_model: int, d_state: int, d_conv: int, expand: int, weights: dict):
        self.d_model  = d_model
        self.d_inner  = d_model * expand
        self.d_state  = d_state
        self.d_conv   = d_conv

        # Load weights — all float32
        def _w(key): return np.asarray(weights[key], dtype=np.float32)

        self.W_in    = _w("in_proj_weight")      # [d_inner*2, d_model]
        self.b_in    = weights.get("in_proj_bias")
        self.b_in    = np.asarray(self.b_in, dtype=np.float32) if self.b_in is not None else np.zeros(self.d_inner * 2, dtype=np.float32)

        self.W_conv  = _w("conv1d_weight")       # [d_inner, 1, d_conv]
        self.b_conv  = _w("conv1d_bias")         # [d_inner]

        self.W_xproj = _w("x_proj_weight")       # [dt_rank+d_state*2, d_inner]
        self.b_xproj = weights.get("x_proj_bias")
        self.b_xproj = np.asarray(self.b_xproj, dtype=np.float32) if self.b_xproj is not None else np.zeros(self.W_xproj.shape[0], dtype=np.float32)

        self.W_dt    = _w("dt_proj_weight")      # [d_inner, dt_rank]
        self.b_dt    = _w("dt_proj_bias")        # [d_inner]

        self.A_log   = _w("A_log")               # [d_inner, d_state]
        self.D       = _w("D")                   # [d_inner]

        self.W_out   = _w("out_proj_weight")     # [d_model, d_inner]
        self.b_out   = weights.get("out_proj_bias")
        self.b_out   = np.asarray(self.b_out, dtype=np.float32) if self.b_out is not None else np.zeros(d_model, dtype=np.float32)

        # Derived shapes
        dt_rank_plus = self.W_xproj.shape[0]
        self.dt_rank = dt_rank_plus - d_state * 2

    @staticmethod
    def _silu(x: np.ndarray) -> np.ndarray:
        return x / (1.0 + np.exp(-x))

    @staticmethod
    def _softplus(x: np.ndarray) -> np.ndarray:
        return np.log1p(np.exp(x))

    def _causal_conv1d(self, x: np.ndarray) -> np.ndarray:
        """Causal depthwise conv1d.

        Args:
            x: [B, T, d_inner]
        Returns:
            [B, T, d_inner]
        """
        B, T, Di = x.shape
        d_conv = self.d_conv
        # Pad left with zeros (causal)
        padded = np.concatenate([np.zeros((B, d_conv - 1, Di), dtype=np.float32), x], axis=1)  # [B, T+d_conv-1, Di]

        # Kernel: [d_inner, 1, d_conv] → [d_inner, d_conv]
        kernel = self.W_conv[:, 0, :]  # [d_inner, d_conv]
        out = np.zeros((B, T, Di), dtype=np.float32)

        # Depthwise: for each output position t, sum over window
        for t in range(T):
            window = padded[:, t:t + d_conv, :]          # [B, d_conv, d_inner]
            out[:, t, :] = np.einsum("bkd,dk->bd", window, kernel) + self.b_conv

        return out

    def _ssm_scan(self, x: np.ndarray, dt: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray) -> np.ndarray:
        """Sequential SSM scan (inference-safe, no CUDA).

        Args:
            x:  [B, T, d_inner]
            dt: [B, T, d_inner]  — discretized time-step
            A:  [d_inner, d_state]   — continuous A (negative by construction)
            B:  [B, T, d_state]
            C:  [B, T, d_state]
        Returns:
            y:  [B, T, d_inner]
        """
        B_sz, T, Di = x.shape
        Ds = self.d_state

        # ZOH discretization: dA = exp(dt * A), dB = dt * B
        # dt: [B, T, Di], A: [Di, Ds] → dA: [B, T, Di, Ds]
        dA = np.exp(dt[:, :, :, np.newaxis] * A[np.newaxis, np.newaxis, :, :])  # [B, T, Di, Ds]
        # dB: [B, T, Di, Ds]
        dB = dt[:, :, :, np.newaxis] * B[:, :, np.newaxis, :]                   # [B, T, Di, Ds]

        # Recurrent scan
        h = np.zeros((B_sz, Di, Ds), dtype=np.float32)   # hidden state
        y = np.zeros((B_sz, T, Di), dtype=np.float32)

        for t in range(T):
            h = dA[:, t, :, :] * h + dB[:, t, :, :] * x[:, t, :, np.newaxis]  # [B, Di, Ds]
            # y_t = sum_s h_t * C_t: [B, Di]
            y[:, t, :] = np.einsum("bds,bs->bd", h, C[:, t, :])

        return y

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """Forward pass — inference equivalent of mamba_ssm forward.

        Args:
            x: [B, T, d_model] float32
        Returns:
            [B, T, d_model] float32
        """
        x = np.asarray(x, dtype=np.float32)
        B, T, D = x.shape
        Di = self.d_inner

        # 1. Input projection + split
        xz = x @ self.W_in.T + self.b_in          # [B, T, d_inner*2]
        xi, z = xz[..., :Di], xz[..., Di:]        # each [B, T, d_inner]

        # 2. Causal conv1d on xi
        xi_conv = self._causal_conv1d(xi)          # [B, T, d_inner]
        xi_conv = self._silu(xi_conv)

        # 3. SSM parameters (x_proj)
        xproj = xi_conv @ self.W_xproj.T + self.b_xproj   # [B, T, dt_rank+d_state*2]
        dt_raw = xproj[..., :self.dt_rank]                  # [B, T, dt_rank]
        B_ssm  = xproj[..., self.dt_rank:self.dt_rank + self.d_state]   # [B, T, d_state]
        C_ssm  = xproj[..., self.dt_rank + self.d_state:]               # [B, T, d_state]

        # 4. dt: low-rank → d_inner, softplus, clamp
        dt = dt_raw @ self.W_dt.T + self.b_dt               # [B, T, d_inner]
        dt = np.clip(self._softplus(dt), 1e-4, None)

        # 5. A — negative exponential of A_log
        A = -np.exp(self.A_log)                              # [d_inner, d_state]

        # 6. SSM scan
        y = self._ssm_scan(xi_conv, dt, A, B_ssm, C_ssm)   # [B, T, d_inner]

        # 7. Skip connection with D
        y = y + xi_conv * self.D[np.newaxis, np.newaxis, :]

        # 8. Gate with z
        y = y * self._silu(z)

        # 9. Output projection
        return y @ self.W_out.T + self.b_out                 # [B, T, d_model]


# ─────────────────────────────────────────────────────────────────────────────
# Cross-Token Attention (Tier A — interleaved MHA)
# ─────────────────────────────────────────────────────────────────────────────

class _CrossTokenAttention:
    """Tier A: MHA for long-range cross-token physics coupling.

    Mirrors pytorch CrossTokenAttention. Simple self-attention with residual.

    Weight contract:
        mha_q_proj_weight: [d_model, d_model]
        mha_q_proj_bias:   [d_model]
        mha_k_proj_weight: [d_model, d_model]
        mha_k_proj_bias:   [d_model]
        mha_v_proj_weight: [d_model, d_model]
        mha_v_proj_bias:   [d_model]
        mha_out_proj_weight: [d_model, d_model]
        mha_out_proj_bias:   [d_model]
        norm_weight: [d_model]
        norm_bias:   [d_model]
    """

    def __init__(self, d_model: int, num_heads: int, weights: dict):
        self.d_model   = d_model
        self.num_heads = num_heads
        self.head_dim  = d_model // num_heads
        self.scale     = math.sqrt(self.head_dim)

        def _w(k): return np.asarray(weights[k], dtype=np.float32)

        self.W_q   = _w("mha_q_proj_weight"); self.b_q = _w("mha_q_proj_bias")
        self.W_k   = _w("mha_k_proj_weight"); self.b_k = _w("mha_k_proj_bias")
        self.W_v   = _w("mha_v_proj_weight"); self.b_v = _w("mha_v_proj_bias")
        self.W_out = _w("mha_out_proj_weight"); self.b_out = _w("mha_out_proj_bias")
        self.norm_w = _w("norm_weight"); self.norm_b = _w("norm_bias")

    @staticmethod
    def _layer_norm(x: np.ndarray, w: np.ndarray, b: np.ndarray, eps: float = 1e-5) -> np.ndarray:
        mean = x.mean(axis=-1, keepdims=True)
        var  = x.var(axis=-1, keepdims=True)
        return w * (x - mean) / np.sqrt(var + eps) + b

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        e = np.exp(x - x.max(axis=-1, keepdims=True))
        return e / e.sum(axis=-1, keepdims=True)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """Args: x [B, T, d_model]. Returns [B, T, d_model]."""
        x    = np.asarray(x, dtype=np.float32)
        B, T, D = x.shape
        H, Hd = self.num_heads, self.head_dim

        x_norm = self._layer_norm(x, self.norm_w, self.norm_b)

        Q = (x_norm @ self.W_q.T + self.b_q).reshape(B, T, H, Hd).transpose(0, 2, 1, 3)
        K = (x_norm @ self.W_k.T + self.b_k).reshape(B, T, H, Hd).transpose(0, 2, 1, 3)
        V = (x_norm @ self.W_v.T + self.b_v).reshape(B, T, H, Hd).transpose(0, 2, 1, 3)

        attn = self._softmax(np.matmul(Q, K.transpose(0, 1, 3, 2)) / self.scale)
        out  = np.matmul(attn, V).transpose(0, 2, 1, 3).reshape(B, T, D)
        out  = out @ self.W_out.T + self.b_out
        return x + out   # residual


# ─────────────────────────────────────────────────────────────────────────────
# VersorMemMambaBlock
# ─────────────────────────────────────────────────────────────────────────────

class VersorMemMambaBlock:
    """Single Versor block: GPA → SSM → (CrossAttn) → NoteBlock → LayerNorm.

    Mirrors pytorch VersorMemMambaBlock(nn.Module).

    Args:
        d_model:      embedding dimension.
        n_heads:      GPA head count.
        mv_dim:       multivector dimension (32 for Cl(4,1)).
        layer_idx:    index in the stack.
        total_layers: stack depth (for cross_layer_interval).
        weights:      dict with all sub-module weights.
    """

    def __init__(
        self,
        d_model: int,
        n_heads: int,
        mv_dim: int,
        layer_idx: int,
        total_layers: int = 6,
        weights: dict = None,
    ):
        self.layer_idx   = layer_idx
        self.d_model     = d_model

        # Sub-modules
        gpa_w   = weights.get("gpa",   None) if weights else None
        mamba_w = weights.get("mamba", None) if weights else None
        nb_w    = weights.get("note_block", None) if weights else None
        cross_w = weights.get("cross_attn", None) if weights else None

        self.gpa        = GeometricProductAttention(d_model, n_heads, mv_dim, gpa_w)
        self.note_block = NoteBlock(d_model, weights=nb_w)

        d_state = CONFIG.get("mamba_d_state", 256)
        d_conv  = CONFIG.get("mamba_d_conv",  4)
        expand  = CONFIG.get("mamba_expand",  2)

        if mamba_w is not None:
            self.mamba = _MambaSSM(d_model, d_state, d_conv, expand, mamba_w)
        else:
            # Fallback: identity (zero output) for testing without checkpoint
            self.mamba = None

        # LayerNorms
        def _ln(key_prefix, w_dict):
            if w_dict and f"{key_prefix}_weight" in w_dict:
                return (np.asarray(w_dict[f"{key_prefix}_weight"], dtype=np.float32),
                        np.asarray(w_dict[f"{key_prefix}_bias"],   dtype=np.float32))
            return (np.ones(d_model,  dtype=np.float32),
                    np.zeros(d_model, dtype=np.float32))

        self.norm1_w, self.norm1_b = _ln("norm1", weights)
        self.norm2_w, self.norm2_b = _ln("norm2", weights)
        self.norm3_w, self.norm3_b = _ln("norm3", weights)

        # Cross-token attention (optional — Tier A)
        cross_attn_layers = set(CONFIG.get("cross_attn_layers", []))
        self.cross_attn = None
        if layer_idx in cross_attn_layers and cross_w is not None:
            self.cross_attn = _CrossTokenAttention(d_model, n_heads, cross_w)

        self.use_cross_layer = (
            layer_idx % CONFIG["cross_layer_interval"] == 0 and layer_idx > 0
        )

    @staticmethod
    def _layer_norm(x: np.ndarray, w: np.ndarray, b: np.ndarray, eps: float = 1e-5) -> np.ndarray:
        mean = x.mean(axis=-1, keepdims=True)
        var  = x.var(axis=-1, keepdims=True)
        return w * (x - mean) / np.sqrt(var + eps) + b

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """Forward pass.

        Args:
            x: [B, T, d_model] float32
        Returns:
            [B, T, d_model] float32
        """
        x = np.asarray(x, dtype=np.float32)

        # 1. GPA (spatial reasoning)
        x = x + self.gpa(self._layer_norm(x, self.norm1_w, self.norm1_b))

        # 2. SSM scan (temporal causal integration)
        if self.mamba is not None:
            x = x + self.mamba(self._layer_norm(x, self.norm2_w, self.norm2_b))

        # 3. Cross-token coupling (Tier A — optional)
        if self.cross_attn is not None:
            x = self.cross_attn(x)

        # 4. NoteBlock: score → pool → optional inject
        scores = self.note_block.score_importance(x)
        self.note_block.update_pool(x, scores)
        if self.use_cross_layer:
            x = self.note_block.inject_memory(x)

        return self._layer_norm(x, self.norm3_w, self.norm3_b)
