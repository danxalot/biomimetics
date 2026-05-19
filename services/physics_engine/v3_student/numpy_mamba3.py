import numpy as np

def silu(x):
    return x / (1.0 + np.exp(-x))

def softplus(x):
    return np.log1p(np.exp(x))

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

def rms_norm_np(x, weight, eps=1e-5):
    """x: (..., d), weight: (d,)"""
    ms = np.mean(x**2, axis=-1, keepdims=True)
    rms = np.sqrt(ms + eps)
    return (x / rms) * weight

def apply_rope_np(v, theta):
    """v: (..., 256), theta: (..., 128)"""
    v_res = v.copy()
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    v0 = v[..., 0::2]
    v1 = v[..., 1::2]
    v_res[..., 0::2] = v0 * cos_t - v1 * sin_t
    v_res[..., 1::2] = v0 * sin_t + v1 * cos_t
    return v_res

def scan_recurrent(
    z, x, B, C, dd_dt, dd_A, trap, angles,
    dt_bias, B_bias, C_bias, B_norm_w, C_norm_w, D,
    h_state, x_prev, K_prev, angle_state
):
    L, nheads, headdim = x.shape
    d_state = 256
    
    ys = np.empty((L, nheads, headdim), dtype=np.float32)
    
    # Pre-calculate B and C norm
    B_normed = rms_norm_np(B, B_norm_w)
    C_normed = rms_norm_np(C, C_norm_w)
    
    for t in range(L):
        # activations
        dt_val = dd_dt[t] + dt_bias
        dt_t = np.log1p(np.exp(dt_val))
        
        a_val = dd_A[t]
        a_t = -np.log1p(np.exp(a_val))
        a_t = np.minimum(a_t, -1e-4) # Clamp max to -1e-4, meaning minimum of a_t is -inf, max is -1e-4. Wait, we want A <= -1e-4. So a_t = np.minimum(a_t, -1e-4)
        
        alpha = np.exp(a_t * dt_t)
        trap_t = 1.0 / (1.0 + np.exp(-trap[t]))
        
        beta = alpha * dt_t * (1.0 - trap_t)
        gamma = trap_t * dt_t
        
        # RoPE Accumulation
        raw_angle = np.tanh(angles[t]) * np.pi * dt_t[:, None]
        angle_state = (angle_state + raw_angle) % (2.0 * np.pi)
        
        # Biased and Rotated K, Q
        K_un = B_normed[t, None, :] + B_bias # (24, 256)
        Q_un = C_normed[t, None, :] + C_bias
        
        K_curr = apply_rope_np(K_un, angle_state)
        Q_curr = apply_rope_np(Q_un, angle_state)
        
        # Recurrence (Vectorized across heads and dims)
        # h_state: (24, 64, 256)
        # alpha: (24,) -> (24, 1, 1)
        a_v = alpha[:, None, None]
        b_v = beta[:, None, None]
        g_v = gamma[:, None, None]
        
        # x[t]: (24, 64) -> (24, 64, 1)
        # K_curr: (24, 256) -> (24, 1, 256)
        curr_outer = x[t, :, :, None] * K_curr[:, None, :]
        prev_outer = x_prev[:, :, None] * K_prev[:, None, :]
        
        h_state = a_v * h_state + b_v * prev_outer + g_v * curr_outer
        
        # Output
        # sum over d_state: (24, 64, 256) * (24, 1, 256) -> (24, 64)
        y_val = np.sum(h_state * Q_curr[:, None, :], axis=-1)
        y_val += D[:, None] * x[t]
        
        # Gating
        zv = z[t]
        gate = zv / (1.0 + np.exp(-zv))
        ys[t] = y_val * gate
        
        # Update prev states
        x_prev = x[t].copy()
        K_prev = K_curr.copy()
        
    return ys

class Mamba3NP:
    def __init__(self, weights):
        self.dt_bias = weights['mamba.dt_bias']
        self.B_bias = weights['mamba.B_bias'].squeeze(1)
        self.C_bias = weights['mamba.C_bias'].squeeze(1)
        self.B_norm_w = weights['mamba.B_norm.weight']
        self.C_norm_w = weights['mamba.C_norm.weight']
        self.D = weights['mamba.D']
        self.in_proj_w = weights['mamba.in_proj.weight']
        self.out_proj_w = weights['mamba.out_proj.weight']
        self.nheads = 24
        self.headdim = 64
        self.d_state = 256
        self.reset_state()

    def reset_state(self, batch_size=1):
        self.h_state = np.zeros((batch_size, self.nheads, self.headdim, self.d_state), dtype=np.float32)
        self.x_prev = np.zeros((batch_size, self.nheads, self.headdim), dtype=np.float32)
        self.K_prev = np.zeros((batch_size, self.nheads, self.d_state), dtype=np.float32)
        self.angle_state = np.zeros((batch_size, self.nheads, 128), dtype=np.float32)

    def forward(self, x):
        B, T, _ = x.shape
        out = np.empty_like(x)
        for b in range(B):
            h = np.zeros((self.nheads, self.headdim, self.d_state), dtype=np.float32)
            xp = np.zeros((self.nheads, self.headdim), dtype=np.float32)
            kp = np.zeros((self.nheads, self.d_state), dtype=np.float32)
            ang = np.zeros((self.nheads, 128), dtype=np.float32)
            proj = x[b] @ self.in_proj_w.T
            z = proj[:, :1536].reshape(T, 24, 64)
            xi = proj[:, 1536:3072].reshape(T, 24, 64)
            Bi = proj[:, 3072:3328]
            Ci = proj[:, 3328:3584]
            dd_dt = proj[:, 3584:3608]
            dd_A = proj[:, 3608:3632]
            trap = proj[:, 3632:3656]
            angles = proj[:, 3656:3784]
            y = scan_recurrent(z, xi, Bi, Ci, dd_dt, dd_A, trap, angles, self.dt_bias, self.B_bias, self.C_bias, self.B_norm_w, self.C_norm_w, self.D, h, xp, kp, ang)
            out[b] = y.reshape(T, 1536) @ self.out_proj_w.T
        return out

def scan_quadratic(z, x, B, C, dd_dt, dd_A, trap, angles, dt_bias, B_bias, C_bias, B_norm_w, C_norm_w, D):
    T, nheads, headdim = x.shape
    d_state = 256
    dt_val = dd_dt + dt_bias
    DT = np.log1p(np.exp(np.clip(dt_val, -20, 20)))
    DT[dt_val > 20] = dt_val[dt_val > 20]
    a_val = dd_A
    A = -np.log1p(np.exp(np.clip(a_val, -20, 20)))
    A[a_val > 20] = -a_val[a_val > 20]
    A = np.minimum(A, -1e-4)
    alpha = np.exp(A * DT)
    trap_t = 1.0 / (1.0 + np.exp(-trap))
    B_normed = rms_norm_np(B, B_norm_w)
    C_normed = rms_norm_np(C, C_norm_w)
    angle_state = np.zeros((T, nheads, 128))
    curr_angle = np.zeros((nheads, 128))
    for t in range(T):
        raw_angle = np.tanh(angles[t]) * np.pi * DT[t, :, None]
        curr_angle = (curr_angle + raw_angle) % (2.0 * np.pi)
        angle_state[t] = curr_angle

    K = apply_rope_np(B_normed[:, None, :] + B_bias[None, :, :], angle_state)
    Q = apply_rope_np(C_normed[:, None, :] + C_bias[None, :, :], angle_state)
    beta = alpha * DT * (1.0 - trap_t)
    gamma = trap_t * DT
    y = np.zeros((T, nheads, headdim))
    for h in range(nheads):
        L = np.ones((T, T))
        for t in range(T):
            for s in range(t): L[t, s] = L[t-1, s] * alpha[t, h]
        weights = np.zeros((T, T))
        for t in range(T):
            weights[t, t] = gamma[t, h]
            for s in range(t):
                w = L[t, s] * gamma[s, h]
                if s < t: w += L[t, s+1] * beta[s+1, h]
                weights[t, s] = w
        for t in range(T):
            y_h_t = np.zeros(headdim)
            for s in range(t + 1):
                y_h_t += weights[t, s] * x[s, h] * np.dot(K[s, h], Q[t, h])
            y[t, h] = y_h_t + D[h] * x[t, h]
    gate = silu(z)
    return y * gate
