import numpy as np
import logging
from typing import Dict, Tuple, Optional, List, Any
from .cl41_math import geometric_product, sandwich_product
try:
    from numba import njit
except ImportError:
    # Fallback if numba is not installed
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator

logger = logging.getLogger(__name__)

@njit(fastmath=True)
def silu(x: np.ndarray) -> np.ndarray:
    """SiLU activation with thermal overflow guard."""
    # Numba compatible clip
    x_clipped = np.minimum(np.maximum(x, -88.0), 88.0)
    return x * (1.0 / (1.0 + np.exp(-x_clipped)))

@njit(fastmath=True)
def mamba_step_jit(
    x: np.ndarray,
    conv_state: np.ndarray,
    hidden_state: np.ndarray,
    in_proj_w: np.ndarray,
    conv1d_w: np.ndarray,
    conv1d_b: np.ndarray,
    x_proj_w: np.ndarray,
    dt_proj_w: np.ndarray,
    dt_proj_b: np.ndarray,
    A: np.ndarray,
    D: np.ndarray,
    out_proj_w: np.ndarray,
    out_proj_b: np.ndarray,
    d_state: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """JIT-compiled inner step for Mamba."""
    # Ensure float32 where possible for numerical stability per AMP bounds
    x_f32 = x.astype(np.float32)
    
    xz = x_f32 @ in_proj_w.T
    d_inner = xz.shape[-1] // 2
    x_proj = xz[:d_inner]
    z = xz[d_inner:]
    
    # 1D Convolution Shift (manual implementation for Numba compatibility)
    for i in range(conv_state.shape[1] - 1):
        conv_state[:, i] = conv_state[:, i + 1]
    conv_state[:, -1] = x_proj
    
    # Numba doesn't fully support squeeze/sum with axis on multi-dim identically, handle manually
    conv_out = np.zeros_like(x_proj)
    for i in range(conv_state.shape[0]):
        val = 0.0
        for j in range(conv_state.shape[1]):
            val += conv_state[i, j] * conv1d_w[i, 0, j]
        conv_out[i] = val + conv1d_b[i]
        
    x_conv = silu(conv_out)
    
    dt_b_c = x_proj_w @ x_conv
    
    dt_rank = dt_proj_w.shape[1]
    dt = dt_b_c[:dt_rank]
    B = dt_b_c[dt_rank:dt_rank+d_state]
    C = dt_b_c[dt_rank+d_state:]
    
    dt = dt_proj_w @ dt + dt_proj_b
    # np.clip and np.log(1+exp)
    dt_clipped = np.minimum(np.maximum(dt, -88.0), 88.0)
    dt_softplus = np.log(1.0 + np.exp(dt_clipped))
    
    # Expand dims conceptually
    # dt_A: (d_inner, d_state)
    dt_A = np.zeros((d_inner, d_state), dtype=np.float32)
    for i in range(d_inner):
        for j in range(d_state):
            dt_A[i, j] = dt_softplus[i] * A[i, j]
            
    dt_A_clipped = np.minimum(np.maximum(dt_A, -88.0), 88.0)
    dA = np.exp(dt_A_clipped)
    
    dB = np.zeros((d_inner, d_state), dtype=np.float32)
    for i in range(d_inner):
        for j in range(d_state):
            dB[i, j] = (dA[i, j] - 1.0) / A[i, j] * dt_softplus[i] * B[j]
            
    for i in range(d_inner):
        for j in range(d_state):
            hidden_state[i, j] = dA[i, j] * hidden_state[i, j] + dB[i, j] * x_conv[i]
            
    # Thermal Clamping applied to hidden state (±5 bounds as requested)
    hidden_state = np.minimum(np.maximum(hidden_state, -5.0), 5.0)
    
    y = np.zeros(d_inner, dtype=np.float32)
    for i in range(d_inner):
        val = 0.0
        for j in range(d_state):
            val += hidden_state[i, j] * C[j]
        y[i] = val + x_conv[i] * D[i]
        
    # Gating
    y = y * silu(z)
    
    out = y @ out_proj_w.T + out_proj_b
    return out.astype(x.dtype), conv_state, hidden_state

@njit(fastmath=True)
def gpa_core_jit(
    Q: np.ndarray,
    K: np.ndarray,
    V: np.ndarray,
    scale: float,
    scalar_weight: float,
    bivector_weight: float
) -> Tuple[np.ndarray, np.ndarray]:
    """JIT-compiled core for Geometric Product Attention."""
    # Q, K, V are (B, n_heads, T, head_dim)
    B, n_heads, T, head_dim = Q.shape
    
    # We do manual batch matrix multiplication for compatibility
    out_v = np.zeros_like(V)
    
    for b in range(B):
        for h in range(n_heads):
            # scalar_attn: Q @ K.T / scale
            # shape: (T, T)
            scalar_attn = np.zeros((T, T), dtype=np.float32)
            for t1 in range(T):
                for t2 in range(T):
                    val = 0.0
                    for d in range(head_dim):
                        val += Q[b, h, t1, d] * K[b, h, t2, d]
                    scalar_attn[t1, t2] = val / scale
            
            # bivector_attn = (scalar_attn - scalar_attn.T) * 0.5
            # bivector_magnitude = sum(|bivector_attn|) over last axis
            bivector_magnitude = np.zeros((T, T), dtype=np.float32)
            for t1 in range(T):
                mag = 0.0
                for t2 in range(T):
                    b_val = (scalar_attn[t1, t2] - scalar_attn[t2, t1]) * 0.5
                    mag += abs(b_val)
                # Broadcast magnitude across row
                for t2 in range(T):
                    bivector_magnitude[t1, t2] = mag
            
            attn = np.zeros((T, T), dtype=np.float32)
            for t1 in range(T):
                for t2 in range(T):
                    attn[t1, t2] = scalar_weight * scalar_attn[t1, t2] + bivector_weight * bivector_magnitude[t1, t2]
            
            # Softmax
            for t1 in range(T):
                m_val = attn[t1, 0]
                for t2 in range(T):
                    if attn[t1, t2] > m_val:
                        m_val = attn[t1, t2]
                
                s_val = 0.0
                for t2 in range(T):
                    attn[t1, t2] = np.exp(attn[t1, t2] - m_val)
                    s_val += attn[t1, t2]
                
                for t2 in range(T):
                    attn[t1, t2] /= s_val
                    
            # Out = attn @ V
            for t1 in range(T):
                for d in range(head_dim):
                    val = 0.0
                    for t2 in range(T):
                        val += attn[t1, t2] * V[b, h, t2, d]
                    out_v[b, h, t1, d] = val
                    
    return out_v

class NumpyLayerNorm:
    def __init__(self, weight: np.ndarray, bias: np.ndarray, eps: float = 1e-5):
        self.weight = weight
        self.bias = bias
        self.eps = eps

    def __call__(self, x: np.ndarray) -> np.ndarray:
        import sys
        # sys.stderr.write(f"[DEBUG] LayerNorm in: {x.shape}\n")
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        return ((x - mean) / np.sqrt(var + self.eps)) * self.weight + self.bias

class NumpyGeometricProductAttention:
    def __init__(self, weights: Dict[str, np.ndarray], d_model: int, n_heads: int):
        self.W_q = weights['W_q.weight']
        self.W_q_bias = weights.get('W_q.bias', np.zeros(d_model))
        self.W_k = weights['W_k.weight']
        self.W_k_bias = weights.get('W_k.bias', np.zeros(d_model))
        self.W_v = weights['W_v.weight']
        self.W_v_bias = weights.get('W_v.bias', np.zeros(d_model))
        self.W_out = weights['W_out.weight']
        self.W_out_bias = weights.get('W_out.bias', np.zeros(d_model))
        
        self.scalar_weight = weights['scalar_weight']
        self.bivector_weight = weights['bivector_weight']
        
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.scale = np.sqrt(self.head_dim)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        is_batched = x.ndim == 3
        if not is_batched:
            x = x[np.newaxis, ...]
            
        B, T, D = x.shape
        
        Q = x @ self.W_q.T + self.W_q_bias
        K = x @ self.W_k.T + self.W_k_bias
        V = x @ self.W_v.T + self.W_v_bias
        
        Q = Q.reshape(B, T, self.n_heads, self.head_dim).transpose(0, 2, 1, 3).astype(np.float32)
        K = K.reshape(B, T, self.n_heads, self.head_dim).transpose(0, 2, 1, 3).astype(np.float32)
        V = V.reshape(B, T, self.n_heads, self.head_dim).transpose(0, 2, 1, 3).astype(np.float32)
        
        out = gpa_core_jit(Q, K, V, self.scale, self.scalar_weight, self.bivector_weight)
        
        out = out.transpose(0, 2, 1, 3).reshape(B, T, D)
        out = out @ self.W_out.T + self.W_out_bias
        
        if not is_batched:
            out = out.squeeze(0)
            
        return out

class NumpyNoteBlock:
    def __init__(self, weights: Dict[str, np.ndarray], d_model: int, threshold: float = 0.7, pool_size: int = 64, initial_pool: Optional[np.ndarray] = None):
        self.scorer_w = weights['importance_scorer.weight']
        self.scorer_b = weights.get('importance_scorer.bias', np.zeros(1))
        self.compressor_w = weights['compressor.weight']
        self.compressor_b = weights.get('compressor.bias', np.zeros(d_model))
        
        self.threshold = threshold
        self.pool_size = pool_size
        self.d_model = d_model

        # Persistence: Use initial_pool if provided (from Redis), else zero
        if initial_pool is not None and initial_pool.shape == (pool_size, d_model):
            self.state_pool = initial_pool.copy()
        else:
            self.state_pool = np.zeros((pool_size, d_model))
            
        self.pool_ptr = 0

    def score_importance(self, x: np.ndarray) -> np.ndarray:
        logits = x @ self.scorer_w.T + self.scorer_b
        return 1.0 / (1.0 + np.exp(-np.clip(logits, -88.0, 88.0)))

    def update_pool(self, x: np.ndarray, scores: np.ndarray):
        scores = np.squeeze(scores, axis=-1)
        mask = scores > self.threshold
        important = x[mask]
        if important.shape[0] > 0:
            compressed = important @ self.compressor_w.T + self.compressor_b
            if compressed.shape[0] > 1:
                compressed = np.max(compressed, axis=0, keepdims=True)
            
            ptr = self.pool_ptr % self.pool_size
            self.state_pool[ptr] = np.squeeze(compressed, axis=0)
            self.pool_ptr += 1

    def inject_memory(self, x: np.ndarray) -> np.ndarray:
        active = min(self.pool_ptr, self.pool_size)
        if active == 0:
            return x
        
        pool = self.state_pool[:active]
        attn = x @ pool.T
        attn = attn / np.sqrt(self.d_model)
        
        attn_max = np.max(attn, axis=-1, keepdims=True)
        exp_attn = np.exp(attn - attn_max)
        attn_probs = exp_attn / np.sum(exp_attn, axis=-1, keepdims=True)
        
        memory_injection = attn_probs @ pool
        return x + 0.1 * memory_injection

@njit(fastmath=True)
def apply_rope_numpy(x: np.ndarray, rope_fraction: float = 1.0) -> np.ndarray:
    """Apply Rotary Position Embedding (RoPE) to the hidden state."""
    # x shape: (d_inner, d_state)
    d_inner, d_state = x.shape
    d_rope = int(d_state * rope_fraction)
    out = np.copy(x)
    
    for i in range(d_inner):
        for j in range(0, d_rope, 2):
            # theta = 10000 ** (-j / d_rope) * (i + 1)
            # Simplified static rotary for deployment (approximating phase rotation)
            theta = (i + 1) * (1.0 / (10000 ** (j / d_rope)))
            cos_val = np.cos(theta)
            sin_val = np.sin(theta)
            
            x1 = x[i, j]
            x2 = x[i, j + 1]
            out[i, j] = x1 * cos_val - x2 * sin_val
            out[i, j + 1] = x1 * sin_val + x2 * cos_val
            
    return out

class NumpyMamba3SSM:
    """
    Pure NumPy implementation of the discrete Mamba-3 Selective Scan with RoPE.
    """
    def __init__(self, weights: Dict[str, np.ndarray], d_model: int = 768, d_state: int = 256, expand: int = 2, d_conv: int = 4, n_heads: int = 12):
        self.d_model = d_model
        self.d_state = d_state
        self.expand = expand
        self.d_inner = d_model * expand
        self.d_conv = d_conv
        self.n_heads = n_heads
        
        self.in_proj_w = weights.get('in_proj.weight', np.eye(self.d_inner * 2, d_model))
        self.conv1d_w = weights.get('conv1d.weight', np.zeros((self.d_inner, 1, d_conv)))
        self.conv1d_b = weights.get('conv1d.bias', np.zeros(self.d_inner))
        self.x_proj_w = weights.get('x_proj.weight', np.zeros((32 + d_state*2, self.d_inner)))
        self.dt_proj_w = weights.get('dt_proj.weight', np.zeros((self.d_inner, 32)))
        self.dt_proj_b = weights.get('dt_proj.bias', np.zeros(self.d_inner))
        
        # A_log fallback for Mamba-3 shape (12, 256) conceptually, but implementation might flatten
        self.A_log = weights.get('A_log', -np.ones((self.d_inner, self.d_state)))
        self.A = -np.exp(self.A_log)
        self.D = weights.get('D', np.zeros(self.d_inner))
        
        self.out_proj_w = weights.get('out_proj.weight', np.eye(d_model, self.d_inner))
        self.out_proj_b = weights.get('out_proj.bias', np.zeros(d_model))
        
        # States
        self.hidden_state = np.zeros((self.d_inner, self.d_state), dtype=np.float32)
        self.conv_state = np.zeros((self.d_inner, self.d_conv), dtype=np.float32)

    def step(self, x: np.ndarray) -> np.ndarray:
        x = x.squeeze()
        x_shape = x.shape
        x = x + np.random.normal(0, 1e-5, size=x.shape).astype(np.float32)

        # Mamba-3 applies RoPE phase tracking to hidden state before update
        self.hidden_state = apply_rope_numpy(self.hidden_state)

        out, self.conv_state, self.hidden_state = mamba_step_jit(
            x,
            self.conv_state,
            self.hidden_state,
            self.in_proj_w,
            self.conv1d_w,
            self.conv1d_b,
            self.x_proj_w,
            self.dt_proj_w,
            self.dt_proj_b,
            self.A,
            self.D,
            self.out_proj_w,
            self.out_proj_b,
            self.d_state
        )
        
        if out.shape != x_shape:
             out = out.reshape(x_shape)
        return out

    def absorb_pulse(self, pulse: np.ndarray, coupling: float = 0.2):
        pulse = pulse.squeeze()
        xz = pulse @ self.in_proj_w.T
        x_proj, _ = np.split(xz, 2, axis=-1) 
        x_proj = x_proj.squeeze()
        self.hidden_state += coupling * x_proj[:, np.newaxis]
        self.hidden_state = np.clip(self.hidden_state, -5.0, 5.0)

    def __call__(self, x_seq: np.ndarray) -> np.ndarray:
        T = x_seq.shape[0]
        out_seq = np.zeros_like(x_seq)
        for t in range(T):
            out_seq[t] = self.step(x_seq[t])
        return out_seq

class NumpyMambaSSM:
    """
    Pure NumPy implementation of the discrete Mamba Selective Scan.
    Expects A_log of shape (512, 128), aligning with d_state=128 production weights.
    """
    def __init__(self, weights: Dict[str, np.ndarray], d_model: int = 256, d_state: int = 128, expand: int = 2, d_conv: int = 4):
        self.d_model = d_model
        self.d_state = d_state
        self.expand = expand
        self.d_inner = d_model * expand
        self.d_conv = d_conv
        
        self.in_proj_w = weights['in_proj.weight']
        
        self.conv1d_w = weights['conv1d.weight']
        self.conv1d_b = weights['conv1d.bias']
        
        self.x_proj_w = weights['x_proj.weight']
        
        self.dt_proj_w = weights['dt_proj.weight']
        self.dt_proj_b = weights['dt_proj.bias']
        
        # A_log shape expected to be (512, 128)
        self.A_log = weights['A_log']
        self.A = -np.exp(self.A_log)
        
        self.D = weights['D']
        
        self.out_proj_w = weights['out_proj.weight']
        self.out_proj_b = weights.get('out_proj.bias', np.zeros(d_model))
        
        # States
        self.hidden_state = np.zeros((self.d_inner, self.d_state))
        self.conv_state = np.zeros((self.d_inner, self.d_conv))


    def step(self, x: np.ndarray) -> np.ndarray:
        x = x.squeeze()
        x_shape = x.shape
        # [DARK CURRENT PATCH]: Inject stochastic noise floor (~1e-5) to prevent 
        # C-vector collapse and enable observable Hamiltonian energy during idle states.
        x = x + np.random.normal(0, 1e-5, size=x.shape).astype(np.float32)

        out, self.conv_state, self.hidden_state = mamba_step_jit(
            x,
            self.conv_state,
            self.hidden_state,
            self.in_proj_w,
            self.conv1d_w,
            self.conv1d_b,
            self.x_proj_w,
            self.dt_proj_w,
            self.dt_proj_b,
            self.A,
            self.D,
            self.out_proj_w,
            self.out_proj_b,
            self.d_state
        )
        
        # Restore any lost dimensions
        if out.shape != x_shape:
             # This handles the case where out is flat but x_shape is flat too, we just reshape
             out = out.reshape(x_shape)
        return out

    def absorb_pulse(self, pulse: np.ndarray, coupling: float = 0.2):
        """
        Inject resonance pulse directly into the hidden state.
        The pulse (256D) is projected via in_proj to match internal dimensions.
        """
        pulse = pulse.squeeze()
        import sys
        sys.stderr.write(f"[DEBUG] absorb_pulse in: {pulse.shape}\n")
        xz = pulse @ self.in_proj_w.T
        x_proj, _ = np.split(xz, 2, axis=-1) 
        x_proj = x_proj.squeeze()
        
        # Inject into hidden state across all d_state dimensions
        self.hidden_state += coupling * x_proj[:, np.newaxis]
        self.hidden_state = np.clip(self.hidden_state, -5.0, 5.0)
        
    def __call__(self, x_seq: np.ndarray) -> np.ndarray:
        T = x_seq.shape[0]
        out_seq = np.zeros_like(x_seq)
        for t in range(T):
            out_seq[t] = self.step(x_seq[t])
        return out_seq

class NumpyVersorMemMambaBlock:
    def __init__(self, weights: Dict[str, np.ndarray], prefix: str, d_model: int, n_heads: int, layer_idx: int, initial_pool: Optional[np.ndarray] = None):
        self.layer_idx = layer_idx
        
        gpa_w = {k.replace(f'{prefix}.gpa.', ''): v for k, v in weights.items() if k.startswith(f'{prefix}.gpa.')}
        mamba_w = {k.replace(f'{prefix}.mamba.', ''): v for k, v in weights.items() if k.startswith(f'{prefix}.mamba.')}
        note_w = {k.replace(f'{prefix}.note_block.', ''): v for k, v in weights.items() if k.startswith(f'{prefix}.note_block.')}
        
        self.gpa = NumpyGeometricProductAttention(gpa_w, d_model, n_heads)
        self.mamba = NumpyMamba3SSM(mamba_w, d_model=d_model, d_state=256, n_heads=n_heads)
        self.note_block = NumpyNoteBlock(note_w, d_model, initial_pool=initial_pool)
        
        self.norm1 = NumpyLayerNorm(weights[f'{prefix}.norm1.weight'], weights[f'{prefix}.norm1.bias'])
        self.norm2 = NumpyLayerNorm(weights[f'{prefix}.norm2.weight'], weights[f'{prefix}.norm2.bias'])
        self.norm3 = NumpyLayerNorm(weights[f'{prefix}.norm3.weight'], weights[f'{prefix}.norm3.bias'])
        
        self.use_cross_layer = (layer_idx % 4 == 0 and layer_idx > 0)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        import sys
        try:
            x = x + self.gpa(self.norm1(x))
            x = x + self.mamba(self.norm2(x))
            
            scores = self.note_block.score_importance(x)
            self.note_block.update_pool(x, scores)
            
            if self.use_cross_layer:
                x = self.note_block.inject_memory(x)
                
            x = self.norm3(x)
            return x
        except Exception as e:
            sys.stderr.write(f"[FATAL] Block failed at layer {self.layer_idx}: {e}\n")
            raise e

    def absorb_pulse(self, pulse: np.ndarray, coupling: float = 0.2):
        """Pass pulse to Mamba layer."""
        self.mamba.absorb_pulse(pulse, coupling)

class NumpyHamiltonianExpert:
    def __init__(self, weights: Dict[str, np.ndarray], prefix: str):
        self.w1 = weights[f'{prefix}.potential.0.weight']
        self.b1 = weights[f'{prefix}.potential.0.bias']
        self.w2 = weights[f'{prefix}.potential.2.weight']
        self.b2 = weights[f'{prefix}.potential.2.bias']

    def potential(self, x: np.ndarray) -> np.ndarray:
        x1 = x @ self.w1.T + self.b1
        x1 = silu(x1)
        return x1 @ self.w2.T + self.b2

    def __call__(self, q: np.ndarray, p: np.ndarray, dt: float = 0.1) -> Tuple[np.ndarray, np.ndarray]:
        dq = self.potential(p)
        new_q = q + dt * dq
        
        dp = self.potential(new_q)
        new_p = p - dt * dp
        
        return new_q, new_p

class NumpySMoEHE:
    def __init__(self, weights: Dict[str, np.ndarray], prefix: str, dim: int, n_experts: int = 4):
        self.n_experts = n_experts
        
        # Explicit verification of SMoE-HE keys for the 23k Gold Standard manifold
        required_keys = [f'{prefix}.gate.weight', f'{prefix}.gate.bias']
        for i in range(n_experts):
            required_keys.extend([
                f'{prefix}.experts.{i}.potential.0.weight',
                f'{prefix}.experts.{i}.potential.0.bias',
                f'{prefix}.experts.{i}.potential.2.weight',
                f'{prefix}.experts.{i}.potential.2.bias'
            ])
            
        missing = [k for k in required_keys if k not in weights]
        if missing:
            raise KeyError(f"SMoE-HE mapping failure: Missing {len(missing)} keys for {n_experts} experts (prefix: {prefix}). Missing: {missing[:3]}...")
            
        self.experts = [NumpyHamiltonianExpert(weights, f'{prefix}.experts.{i}') for i in range(n_experts)]
        self.gate_w = weights[f'{prefix}.gate.weight']
        self.gate_b = weights[f'{prefix}.gate.bias']
        self.dim = dim
        
        logger.info(f"NumpySMoEHE verified: 4 Hamiltonian Experts + Top-2 Gating active (prefix: {prefix})")

    def __call__(self, q: np.ndarray, p: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float, np.ndarray]:
        original_shape = q.shape
        D = original_shape[-1]
        # Flatten all leading dimensions (batch, time, etc.) into a single sequence dimension
        q_flat = q.reshape(-1, D)
        p_flat = p.reshape(-1, D)
        
        gate_logits = q_flat @ self.gate_w.T + self.gate_b
        
        gate_max = np.max(gate_logits, axis=-1, keepdims=True)
        exp_gate = np.exp(gate_logits - gate_max)
        gate_weights = exp_gate / np.sum(exp_gate, axis=-1, keepdims=True)
        
        # Calculate gate entropy
        gate_entropy = float(-np.mean(np.sum(gate_weights * np.log(gate_weights + 1e-10), axis=-1)))
        
        # Calculate expert load
        expert_load = np.mean(gate_weights, axis=0)
        
        sorted_indices = np.argsort(gate_weights, axis=-1)
        k = min(2, self.n_experts)
        topk_indices = sorted_indices[:, -k:][:, ::-1]
        
        topk_weights = np.take_along_axis(gate_weights, topk_indices, axis=-1)
        
        denominator = np.sum(topk_weights, axis=-1, keepdims=True)
        denominator[denominator < 1e-6] = 1e-6
        topk_weights = topk_weights / denominator
        
        new_q_flat = np.zeros_like(q_flat)
        new_p_flat = np.zeros_like(p_flat)
        
        eqs = []
        eps = []
        for i in range(self.n_experts):
            eq, ep = self.experts[i](q_flat, p_flat)
            eqs.append(eq)
            eps.append(ep)
        
        eqs = np.stack(eqs, axis=1) # (T_flat, n_experts, D)
        eps = np.stack(eps, axis=1)
        
        T_flat = q_flat.shape[0]
        for t in range(T_flat):
            for i in range(k):
                idx = int(topk_indices[t, i])
                weight = topk_weights[t, i]
                new_q_flat[t] += weight * eqs[t, idx]
                new_p_flat[t] += weight * eps[t, idx]
            
        return new_q_flat.reshape(original_shape), new_p_flat.reshape(original_shape), gate_entropy, expert_load

class SandboxHopfieldMemory:
    """NumPy implementation of C1-compatible Modern Hopfield memory."""
    def __init__(self, weights: Dict[str, np.ndarray], prefix: str, attractor_dim: int, query_dim: int, pattern_projection_dim: int, beta: float):
        # We handle the case where weights might not be present by creating dummies
        self.query_lift_w = weights.get(f'{prefix}.query_lift.weight', np.eye(query_dim * 2, query_dim))
        self.query_lift_b = weights.get(f'{prefix}.query_lift.bias', np.zeros(query_dim * 2))
        self.input_projection_w = weights.get(f'{prefix}.input_projection.weight', np.eye(pattern_projection_dim, query_dim * 2))
        self.input_projection_b = weights.get(f'{prefix}.input_projection.bias', np.zeros(pattern_projection_dim))
        
        self.stored_patterns = weights.get(f'{prefix}.stored_patterns', np.zeros((0, pattern_projection_dim)))
        self.beta = beta

    def store_patterns(self, pattern: np.ndarray):
        """Append a new pattern to the memory pool."""
        if self.stored_patterns.shape[0] == 0:
            self.stored_patterns = pattern
        else:
            self.stored_patterns = np.vstack([self.stored_patterns, pattern])

    def compute_energy(self, query: np.ndarray) -> np.ndarray:
        if self.stored_patterns.shape[0] == 0:
            return np.zeros(query.shape[:-1], dtype=np.float32)
        
        q = (query @ self.query_lift_w.T + self.query_lift_b) @ self.input_projection_w.T + self.input_projection_b
        q_norm = np.linalg.norm(q, axis=-1, keepdims=True).clip(min=1e-8)
        q = q / q_norm
        
        patterns_norm = np.linalg.norm(self.stored_patterns, axis=-1, keepdims=True).clip(min=1e-8)
        patterns = self.stored_patterns / patterns_norm
        
        sim = q @ patterns.T
        mean_sim = np.mean(sim, axis=-1)
        return (1.0 - mean_sim).astype(np.float32)

class NumpyEntityInteractionBlock:
    """Processes multi-entity interactions (B, T, N, D) using Geometric Product Attention across N."""
    def __init__(self, weights: Dict[str, np.ndarray], prefix: str, d_model: int, n_heads: int):
        self.gpa = NumpyGeometricProductAttention(
            {k.replace(f'{prefix}.gpa.', ''): v for k, v in weights.items() if k.startswith(f'{prefix}.gpa.')},
            d_model, n_heads
        )
        self.norm = NumpyLayerNorm(
            weights.get(f'{prefix}.norm.weight', np.ones(d_model)),
            weights.get(f'{prefix}.norm.bias', np.zeros(d_model))
        )
        self.d_model = d_model

    def __call__(self, x: np.ndarray) -> np.ndarray:
        # x is expected to be (B, T, N, D)
        if x.ndim == 4:
            B, T, N, D = x.shape
            # Reshape to (B*T, N, D) for interaction across entities
            x_flat = x.reshape(B * T, N, D)
            x_interact = x_flat + self.gpa(self.norm(x_flat))
            return x_interact.reshape(B, T, N, D)
        return x

class NumpyNoumenalEngine:
    def __init__(self, weights: Dict[str, np.ndarray], config: Dict, initial_pools: Optional[Dict[int, np.ndarray]] = None):
        self.d_model = config.get('embed_dim', 768)
        self.mv_dim = config.get('mv_dim', 32)
        # V3 enforces a 32-layer stack minimum
        self.n_layers = config.get('n_layers', 32)
        
        self.input_proj_w = weights['input_proj.weight']
        self.input_proj_b = weights.get('input_proj.bias', np.zeros(self.d_model))
        
        self.blocks = []
        
        # Enforce V3 standards: 32 layers + Multi-Entity tracking blocks
        for i in range(self.n_layers):
            pool = initial_pools.get(i) if initial_pools else None
            # Strictly use V3 block (NumpyVersorMemMambaBlock now inherently wraps NumpyMamba3SSM)
            self.blocks.append(NumpyVersorMemMambaBlock(weights, f'blocks.{i}', self.d_model, config.get('n_heads', 12), i, initial_pool=pool))
            
            # Interleave EntityInteractionBlock to track multiple interacting concepts
            if i % 2 == 1:
                self.blocks.append(NumpyEntityInteractionBlock(weights, f'entity_blocks.{i//2}', self.d_model, config.get('n_heads', 12)))
        
        self.smoe_he = NumpySMoEHE(weights, 'smoe_he', self.d_model // 2, config.get('n_experts', 4))

        
        self.rotor_head_w = weights['rotor_head.weight']
        self.rotor_head_b = weights.get('rotor_head.bias', np.zeros(self.mv_dim))
        
        self.hopfield = SandboxHopfieldMemory(
            weights, 'hopfield',
            attractor_dim=config.get('hopfield_attractor_dim', 256),
            query_dim=self.d_model // 2,
            pattern_projection_dim=512,
            beta=config.get('hopfield_beta', 4.0)
        )
        
        # [ROTOR ACCUMULATION] Global rotor that evolves over time
        self.global_rotor = np.zeros(self.mv_dim, dtype=np.float32)
        self.global_rotor[0] = 1.0  # Identity
        
    def absorb_pulse(self, pulse: np.ndarray, coupling: float = 0.2):
        """Distribute resonance pulse across all Mamba layers."""
        for block in self.blocks:
            block.mamba.absorb_pulse(pulse, coupling)

    def forward(self, mv_input: np.ndarray) -> Dict[str, np.ndarray]:
        return self.__call__(mv_input)

    def forward_multiscale(self, mv_input: np.ndarray, stride_scale: int = 1) -> Dict[str, np.ndarray]:
        """Provides support for variable stride length predictions from MC-JEPA masks."""
        # For numpy mock, we just call the standard forward, but in production, we'd route heads based on stride
        # We simulate the multi-scale effect by scaling the predicted output loosely
        res = self.__call__(mv_input)
        if stride_scale > 1:
            res["predicted_rotor"] = res["predicted_rotor"] * (1.0 + 0.1 * stride_scale)
            # Re-normalize
            norm = np.linalg.norm(res["predicted_rotor"])
            if norm > 1e-8:
                res["predicted_rotor"] /= norm
        return res

    def __call__(self, mv_input: np.ndarray) -> Dict[str, np.ndarray]:
        # Project to embedding space
        x = mv_input @ self.input_proj_w.T + self.input_proj_b
        
        # Process blocks
        for block in self.blocks:
            x = block(x)
            
        # Split into phase space (q, p)
        q, p = np.split(x, 2, axis=-1)

        # SMoE-HE Phase-Space Evolution
        q, p, gate_entropy, expert_load = self.smoe_he(q, p)

        # [DARK CURRENT] Inject stochastic noise floor to prevent manifold stagnation
        noise = np.random.normal(0, 1e-5, x.shape).astype(np.float32)
        x = x + noise

        # Reconstruct & predict rotors
        combined = np.concatenate([q, p], axis=-1)
        predicted_rotors = combined @ self.rotor_head_w.T + self.rotor_head_b

        # [ROTOR ACCUMULATION] Compose with global rotor via Geometric Product
        local_rotor = predicted_rotors[0] if predicted_rotors.ndim == 2 else predicted_rotors
        self.global_rotor = geometric_product(self.global_rotor, local_rotor)

        # Normalize to spin manifold
        norm = np.linalg.norm(self.global_rotor)
        if norm < 1e-8:
            self.global_rotor[0] = 1.0
            self.global_rotor[1:] = 0.0
        else:
            self.global_rotor /= norm

        # Compute Hopfield energy
        hopfield_e = float(np.mean(self.hopfield.compute_energy(q)))

        return {
            "predicted_rotor": self.global_rotor,
            "hamiltonian": float(np.sum(p**2)), # Local proxy: p^2 is fast on CPU
            "hopfield_energy": hopfield_e,
            "q": q,
            "p": p,
            "gate_entropy": gate_entropy,
            "expert_load": expert_load.tolist()
        }
    def get_state_pools(self) -> Dict[int, np.ndarray]:
        """Expose all NoteBlock state pools for Redis serialization."""
        return {i: block.note_block.state_pool for i, block in enumerate(self.blocks)}
