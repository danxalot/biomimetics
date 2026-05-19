import numpy as np
import os
from .numpy_mamba3 import Mamba3NP

def layer_norm(x, weight, bias, eps=1e-5):
    """Standard LayerNorm in NumPy."""
    mean = np.mean(x, axis=-1, keepdims=True)
    var = np.var(x, axis=-1, keepdims=True)
    return weight * (x - mean) / np.sqrt(var + eps) + bias

class VersorMemMambaStackNP:
    def __init__(self, npz_path):
        if not os.path.exists(npz_path):
            raise FileNotFoundError(f"Weights not found at {npz_path}")
        
        data = np.load(npz_path)
        keys = list(data.keys())
        consumed_keys = set()
        
        self.n_layers = 32
        self.d_model = 768
        self.residual_scale = 0.125 # 1/8
        
        self.layers = []
        for i in range(self.n_layers):
            layer_prefix = f"layers.{i}."
            mamba_prefix = f"layers.{i}.mamba."
            
            # Extract weights for this layer
            l_weights = {}
            # LayerNorm
            l_weights['norm.weight'] = data[f"{layer_prefix}norm.weight"]
            l_weights['norm.bias'] = data[f"{layer_prefix}norm.bias"]
            consumed_keys.add(f"{layer_prefix}norm.weight")
            consumed_keys.add(f"{layer_prefix}norm.bias")
            
            # Mamba3
            m_keys = [
                'in_proj.weight', 'out_proj.weight', 'dt_bias', 'D',
                'B_bias', 'C_bias', 'B_norm.weight', 'C_norm.weight'
            ]
            m_weights = {}
            for k in m_keys:
                full_k = f"{mamba_prefix}{k}"
                m_weights[f"mamba.{k}"] = data[full_k]
                consumed_keys.add(full_k)
            
            # Vestigial
            consumed_keys.add(f"{layer_prefix}A_log")
            consumed_keys.add(f"{layer_prefix}dt_bias")
            
            self.layers.append({
                'norm_w': l_weights['norm.weight'],
                'norm_b': l_weights['norm.bias'],
                'mamba': Mamba3NP(m_weights)
            })
            
        # Assert key completeness
        all_keys = set(keys)
        # Allow prediction heads keys in trainer model
        head_keys = {
            "rotor_head.weight", "rotor_head.bias",
            "phase_head.weight", "phase_head.bias",
            "smoe_gate.weight", "smoe_gate.bias"
        }
        for i in range(4):
            head_keys.update({
                f"smoe_expert.{i}.w1", f"smoe_expert.{i}.b1",
                f"smoe_expert.{i}.w2", f"smoe_expert.{i}.b2"
            })
        missing = all_keys - consumed_keys - head_keys
        extra = consumed_keys - all_keys
        
        if missing:
            raise RuntimeError(f"Keys left over in npz: {missing}")
        if extra:
            raise RuntimeError(f"Keys missing from npz: {extra}")
        if len(consumed_keys) != 384:
            raise RuntimeError(f"Expected 384 keys, consumed {len(consumed_keys)}")

    def forward(self, x):
        """x: (B, T, 768)"""
        h = x.astype(np.float32)
        for i in range(self.n_layers):
            layer = self.layers[i]
            # LayerNorm
            normed = layer_norm(h, layer['norm_w'], layer['norm_b'])
            # Mamba3
            m_out = layer['mamba'].forward(normed)
            # Residual
            h = h + self.residual_scale * m_out
        return h

    def step(self, x_t, states):
        """Streaming step for inference."""
        # Not fully implemented yet, but placeholders for the API
        pass

    def absorb_pulse(self, pulse: np.ndarray, coupling: float = 0.2):
        """Distribute resonance pulse across all Mamba-3 layers."""
        for layer in self.layers:
            mamba = layer['mamba']
            if hasattr(mamba, 'h_state') and mamba.h_state is not None:
                noise = np.random.randn(*mamba.h_state.shape).astype(np.float32) * coupling * 0.01
                mamba.h_state += noise
                mamba.h_state = np.clip(mamba.h_state, -5.0, 5.0)
