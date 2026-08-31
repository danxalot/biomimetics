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
        missing = all_keys - consumed_keys
        extra = consumed_keys - all_keys

        # Delegate distilled head keys that live beyond the 384 core Mamba keys.
        # student_with_heads_45k.npz contains smoe_*, rotor_head.*, phase_head.*
        # keys that the downstream head modules consume; they must not fail here.
        self.extra_head_keys = {}
        _head_prefixes = ("smoe_", "rotor_head", "phase_head")
        _remaining_missing = set()
        for k in missing:
            if any(k.startswith(p) for p in _head_prefixes):
                self.extra_head_keys[k] = data[k]
            else:
                _remaining_missing.add(k)
        missing = _remaining_missing

        if missing:
            raise RuntimeError(f"Keys left over in npz: {missing}")
        if extra:
            raise RuntimeError(f"Keys missing from npz: {extra}")
        if len(consumed_keys) != 384:
            raise RuntimeError(f"Expected 384 keys, consumed {len(consumed_keys)}")

        # Allostatic gate parameters — writable at runtime via /system/config
        self.thermal_clamp_max = 5.0   # per-element clip bound (safety ceiling), NOT the level control
        self.decay_hypo = 0.98         # retain energy when starved (<1) to wake
        self.decay_hyper = 0.95        # cool aggressively when hot (>4)
        self.decay_base = 0.97         # homeostatic baseline damping (1-4)
        # Operating-energy lever: scales the injected pulse. Equilibrium energy ≈
        # gain*injection/(1-decay), so this (and the decay sliders) set where energy
        # SETTLES below the clamp. 1.0 = neutral. This is the real "pulse energy" knob.
        self.energy_gain = 1.0

        # Global rotor: 32-element vector of per-layer L2 norms.
        # np.linalg.norm(global_rotor) → scalar total energy (reported as mamba_pulse_l2).
        self.global_rotor = np.zeros(self.n_layers, dtype=np.float32)
        self.global_rotor[0] = 1.0  # Identity until first pulse

        # Per-layer forward-pass activity: residual-stream mean|h| at each depth,
        # refreshed on every forward(). Unlike h_state (which absorb_pulse overwrites
        # with an identical broadcast across ALL layers), this is genuinely
        # differentiated across the 32 layers and moves with the live input — it is
        # the telemetry the manifold visualisation reads as layer_energies.
        self.layer_activity = np.zeros(self.n_layers, dtype=np.float32)

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
            # Record per-layer activity (read-only telemetry; does not affect dynamics)
            self.layer_activity[i] = float(np.mean(np.abs(h)))
        return h

    def step(self, x_t, states):
        """Streaming step for inference."""
        # Not fully implemented yet, but placeholders for the API
        pass

    def absorb_pulse(self, pulse: np.ndarray, coupling: float = 0.2):
        """Distribute a resonance pulse across all Mamba-3 layers as a damped leaky integrator.

        Per layer:  h <- decay*h + (energy_gain * coupling * pulse), then clip to ±thermal_clamp_max.

        The decay term is the damping that was previously missing — without it h could only
        grow and saturated against the clip ceiling (energy permanently pinned). With it, energy
        settles at equilibrium ≈ gain*injection/(1-decay), BELOW the ceiling, giving real dynamic
        range. The decay rate is gated allostatically on the current metabolic energy (mean|h|,
        the same [0, clamp] scale reported as hamiltonian_energy and targeted by pythia_pulse):
        retain when starved (<1), cool hard when hot (>4), homeostatic in-band. energy_gain is the
        user-facing operating-energy lever; thermal_clamp_max is only a hard safety ceiling.
        """
        clamp = getattr(self, 'thermal_clamp_max', 5.0)
        gain = getattr(self, 'energy_gain', 1.0)
        # PULSE_BASE_SCALE calibrates the (small, unit-ish) Redis pulse so that the
        # leaky-integrator equilibrium at neutral gain (energy_gain=1.0) settles in the
        # middle of the healthy 1-4 band. Empirically gain=1 w/o scale → E≈0.12; the
        # in-band damping regime multiplies injection by ~33, so ~30× lands E≈2.4.
        # The energy_gain slider then spans roughly E∈[0,4.7] over gain∈[0,2].
        injection = pulse.astype(np.float32) * coupling * gain * 30.0  # (256,) broadcasts over (1, 24, 64, 256)

        for i, layer in enumerate(self.layers):
            mamba = layer['mamba']
            if hasattr(mamba, 'h_state') and mamba.h_state is not None:
                # Allostatic damping selection on the mean|h| (reported) energy scale
                current_energy = float(np.mean(np.abs(mamba.h_state)))
                if current_energy < 1.0:
                    decay = getattr(self, 'decay_hypo', 0.98)
                elif current_energy > 4.0:
                    decay = getattr(self, 'decay_hyper', 0.95)
                else:
                    decay = getattr(self, 'decay_base', 0.97)
                mamba.h_state = mamba.h_state * decay + injection
                mamba.h_state = np.clip(mamba.h_state, -clamp, clamp)

        # Update global_rotor with per-layer L2 norms so the vitals endpoint
        # reports np.linalg.norm(global_rotor) as the true total-energy scalar.
        for i, layer in enumerate(self.layers):
            mamba = layer['mamba']
            if hasattr(mamba, 'h_state') and mamba.h_state is not None and i < len(self.global_rotor):
                self.global_rotor[i] = float(np.linalg.norm(mamba.h_state))
