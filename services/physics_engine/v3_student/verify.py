import numpy as np
import time
from numpy_mamba3 import Mamba3NP, scan_recurrent, scan_quadratic, silu
from loader import load_v3_student

def verify_scan_equivalence():
    print("[1/5] Verifying scan equivalence (recurrent vs quadratic)...")
    np.random.seed(42)
    T = 16
    nheads = 24
    headdim = 64
    d_state = 256
    
    # Mock inputs
    z = np.random.randn(T, nheads, headdim).astype(np.float32)
    x = np.random.randn(T, nheads, headdim).astype(np.float32)
    B = np.random.randn(T, d_state).astype(np.float32)
    C = np.random.randn(T, d_state).astype(np.float32)
    dd_dt = np.random.randn(T, nheads).astype(np.float32)
    dd_A = np.random.randn(T, nheads).astype(np.float32)
    trap = np.random.randn(T, nheads).astype(np.float32)
    angles = np.random.randn(T, 128).astype(np.float32)
    
    # Mock weights
    dt_bias = np.random.randn(nheads).astype(np.float32)
    B_bias = np.random.randn(nheads, d_state).astype(np.float32)
    C_bias = np.random.randn(nheads, d_state).astype(np.float32)
    B_norm_w = np.ones(d_state, dtype=np.float32)
    C_norm_w = np.ones(d_state, dtype=np.float32)
    D = np.random.randn(nheads).astype(np.float32)
    
    # States
    h_state = np.zeros((nheads, headdim, d_state), dtype=np.float32)
    x_prev = np.zeros((nheads, headdim), dtype=np.float32)
    K_prev = np.zeros((nheads, d_state), dtype=np.float32)
    angle_state = np.zeros((nheads, 128), dtype=np.float32)
    
    y_rec = scan_recurrent(
        z, x, B, C, dd_dt, dd_A, trap, angles,
        dt_bias, B_bias, C_bias, B_norm_w, C_norm_w, D,
        h_state, x_prev, K_prev, angle_state
    )
    
    y_quad = scan_quadratic(
        z, x, B, C, dd_dt, dd_A, trap, angles,
        dt_bias, B_bias, C_bias, B_norm_w, C_norm_w, D
    )
    
    diff = np.abs(y_rec - y_quad)
    max_diff = np.max(diff)
    print(f"      Max diff: {max_diff:.2e}")
    if max_diff < 5e-4:
        print("      PASS")
    else:
        print("      FAIL")

def verify_rope_sanity():
    print("[2/5] Verifying RoPE sanity (orthogonality)...")
    from numpy_mamba3 import apply_rope_np
    v = np.random.randn(10, 256).astype(np.float32)
    theta = np.random.randn(10, 128).astype(np.float32)
    
    rotated = apply_rope_np(v, theta)
    unrotated = apply_rope_np(rotated, -theta)
    
    diff = np.abs(v - unrotated)
    max_diff = np.max(diff)
    print(f"      Round-trip max diff: {max_diff:.2e}")
    
    norm_v = np.linalg.norm(v, axis=-1)
    norm_r = np.linalg.norm(rotated, axis=-1)
    norm_diff = np.abs(norm_v - norm_r)
    print(f"      Norm preservation max diff: {np.max(norm_diff):.2e}")
    
    if max_diff < 1e-5 and np.max(norm_diff) < 1e-5:
        print("      PASS")
    else:
        print("      FAIL")

def verify_numerical_health(npz_path):
    print("[4/5] Verifying numerical health...")
    stack = load_v3_student(npz_path)
    x = np.random.randn(1, 64, 768).astype(np.float32)
    out = stack.forward(x)
    
    print(f"      Output finite: {np.all(np.isfinite(out))}")
    print(f"      Variance: {np.var(out):.4f}")
    print(f"      L2 norm: {np.linalg.norm(out):.4f}")
    
    if np.all(np.isfinite(out)) and np.var(out) > 1e-3:
        print("      PASS")
    else:
        print("      FAIL")

def verify_ground_state(npz_path):
    print("[5/5] Verifying zero-input ground state...")
    stack = load_v3_student(npz_path)
    x = np.zeros((1, 64, 768), dtype=np.float32)
    out = stack.forward(x)
    
    print(f"      Mean: {np.mean(out):.4f}")
    print(f"      Max:  {np.max(out):.4f}")
    
    if np.abs(np.mean(out)) < 1e-4:
        print("      PASS")
    else:
        print("      FAIL")

if __name__ == "__main__":
    npz_path = "/Users/danexall/biomimetics/pythia/Gold_Standard_Archive/checkpoints/c2.5_Akasha_Mamba_v3_45k.npz"
    verify_scan_equivalence()
    verify_rope_sanity()
    verify_numerical_health(npz_path)
    verify_ground_state(npz_path)
