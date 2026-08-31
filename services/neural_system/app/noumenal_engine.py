import numpy as np
import os
import logging

logger = logging.getLogger("Pythia_NumPy_Mind")

def _silu(x):
    x_clipped = np.clip(x, -88.0, 88.0)
    return x * (1.0 / (1.0 + np.exp(-x_clipped)))

def _softmax(x, axis=-1):
    e_x = np.exp(x - np.max(x, axis=axis, keepdims=True))
    return e_x / np.sum(e_x, axis=axis, keepdims=True)

class ContinuousHopfieldNetwork:
    def __init__(self, beta=4.0):
        self.patterns = [] 
        self.beta = beta
        self._num_patterns = 0

    @property
    def num_patterns(self):
        return len(self.patterns)

    def store_pattern(self, pattern):
        p = np.array(pattern, dtype=np.float32).flatten()
        norm = np.linalg.norm(p) + 1e-12
        self.patterns.append(p / norm)
        self._num_patterns += 1

    def retrieve(self, probe):
        if not self.patterns: return probe
        M = np.vstack(self.patterns)
        probe = probe / (np.linalg.norm(probe) + 1e-12)
        sims = (M @ probe) * self.beta
        attn = _softmax(sims)
        return attn @ M

class ProductionMambaBlock:
    def __init__(self, weights, d_inner):
        self.in_proj_w = weights['in_proj_w']
        self.in_proj_b = weights['in_proj_b']
        self.out_proj_w = weights['out_proj_w']
        self.out_proj_b = weights['out_proj_b']
        self.d_inner = d_inner
        self.hidden_state = np.zeros((1, d_inner), dtype=np.float32)

    def forward(self, x):
        # Task 3: Align Input Projection (Audit)
        if x.shape[-1] != self.in_proj_w.shape[1]:
            logger.warning(f"Mamba block input shape mismatch: expected {self.in_proj_w.shape[1]}, got {x.shape[-1]}")
        
        x_proj = x @ self.in_proj_w.T + self.in_proj_b
        x_proj = _silu(x_proj)
        z = x_proj[:, :, :self.d_inner]
        xBC = x_proj[:, :, self.d_inner:]
        
        decay = 0.9
        # Task 2: Stabilize Hidden State (Bounding)
        self.hidden_state = np.clip((self.hidden_state * decay) + np.mean(xBC, axis=1), -5.0, 5.0)
        h_expanded = np.repeat(self.hidden_state[:, np.newaxis, :], x.shape[1], axis=1)
        
        y = (h_expanded * _silu(z)) @ self.out_proj_w.T + self.out_proj_b
        return y

class NoumenalEngine:
    def __init__(self, npz_path):
        logger.info(f"Loading Gold Standard weights from {npz_path}...")
        
        if not os.path.exists(npz_path):
            logger.warning(f"NumPy weights missing at {npz_path}. Using identity passthrough.")
            self._passthrough = True
            self.hopfield = ContinuousHopfieldNetwork()
            self.last_predicted_rotor = np.zeros(32, dtype=np.float32)
            self.last_predicted_rotor[0] = 1.0
            return
            
        self._passthrough = False
        data = np.load(npz_path)
        self.input_proj_w = data['input_proj.weight']
        self.input_proj_b = data['input_proj.bias']
        self.rotor_head_w = data['rotor_head.weight']
        self.rotor_head_b = data['rotor_head.bias']
        
        # Count available blocks
        block_indices = set()
        for k in data.keys():
            if k.startswith('blocks.'):
                idx = int(k.split('.')[1])
                block_indices.add(idx)
        
        self.blocks = []
        for i in sorted(block_indices):
            try:
                in_proj_w = data[f'blocks.{i}.mamba.in_proj.weight']
                out_proj_w = data[f'blocks.{i}.mamba.out_proj.weight']
                
                # Dynamic d_inner detection (in_proj maps d_model -> 2*d_inner)
                # For this specific model, out_proj maps 2*d_inner -> d_model (if using gated MLP)
                # But here it seems to be d_inner = 512.
                d_inner_current = in_proj_w.shape[0] // 2
                
                in_proj_b = data[f'blocks.{i}.mamba.in_proj.bias'] if f'blocks.{i}.mamba.in_proj.bias' in data else np.zeros(in_proj_w.shape[0])
                out_proj_b = data[f'blocks.{i}.mamba.out_proj.bias'] if f'blocks.{i}.mamba.out_proj.bias' in data else np.zeros(out_proj_w.shape[0])
                w = {
                    'in_proj_w': in_proj_w,
                    'in_proj_b': in_proj_b,
                    'out_proj_w': out_proj_w,
                    'out_proj_b': out_proj_b
                }
                self.blocks.append(ProductionMambaBlock(w, d_inner_current))
                logger.info(f"  Loaded block {i} (d_inner={d_inner_current})")
            except KeyError as e:
                logger.warning(f"Block {i} weights incomplete: {e}")
                
        logger.info(f"NoumenalEngine initialized with {len(self.blocks)} blocks")
        self.hopfield = ContinuousHopfieldNetwork()
        self.last_predicted_rotor = np.zeros(32, dtype=np.float32)
        self.last_predicted_rotor[0] = 1.0
        # [ROTOR ACCUMULATION] Global rotor that evolves over time
        self.global_rotor = np.zeros(32, dtype=np.float32)
        self.global_rotor[0] = 1.0

        # Allostatic Damping Defaults
        self.decay_hypo = 0.98
        self.decay_hyper = 0.80
        self.decay_base = 0.90
        self.thermal_clamp_max = 5.0  # Hard L2 safety ceiling on hidden_state
        # Energy gain: scales the injected pulse. This is the operating-energy
        # lever (steady-state L2 ~= coupling*gain/(1-decay)), distinct from the
        # thermal_clamp_max safety ceiling. 1.0 = neutral.
        self.energy_gain = 1.0

    def _geometric_product(self, a, b):
        """Simplified geometric product for rotors in Cl(4,1) 32D.
        For rotors (even-grade multivectors), this approximates rotation composition."""
        # Ensure inputs are flat (Task 1: Robust Slicing Fix)
        a = np.squeeze(a).flatten()
        b = np.squeeze(b).flatten()
        
        # Real part (scalar) + Bivector parts
        result = np.zeros(32, dtype=np.float32)
        # Slicing explicitly on 1D arrays to avoid (0, 32) empty row bugs
        a_biv = a[1:16]
        b_biv = b[1:16]
        
        result[0] = a[0]*b[0] - np.dot(a_biv, b_biv)  # Scalar product
        result[1:16] = a[0]*b_biv + b[0]*a_biv  # Vector cross terms
        return result

    def _normalize_rotor(self, r):
        """Project onto Spin manifold."""
        r = r.flatten()
        norm = np.linalg.norm(r) + 1e-12
        return r / norm

    def forward(self, mv_input):
        if self._passthrough:
            return {"predicted_rotor": self.last_predicted_rotor, "q": np.zeros((1, 256), dtype=np.float32)}
        
        # Task 3: Align Input Projection (Audit)
        if mv_input.shape[-1] != self.input_proj_w.shape[1]:
            logger.warning(f"NoumenalEngine input dimension mismatch: {mv_input.shape[-1]}D input vs {self.input_proj_w.shape[1]}D weights")
        
        x = mv_input @ self.input_proj_w.T + self.input_proj_b
        for block in self.blocks:
            x = block.forward(x)
        
        res = x[:, -1, :] @ self.rotor_head_w.T + self.rotor_head_b
        local_rotor = self._normalize_rotor(res)
        
        # [ROTOR ACCUMULATION] Compose with global rotor
        self.global_rotor = self._normalize_rotor(self._geometric_product(self.global_rotor, local_rotor))
        self.last_predicted_rotor = self.global_rotor
        
        return {"predicted_rotor": self.last_predicted_rotor, "q": x[:, -1, :]}

    def absorb_pulse(self, vector_256: np.ndarray, coupling_strength: float = 0.15):
        """Injects DMN energy with autonomic thermal regulation (Allostasis)."""
        for i, block in enumerate(self.blocks):
            if hasattr(block, 'hidden_state') and block.hidden_state is not None:
                # 1. Calculate current metabolic state (L2 Norm)
                current_l2 = np.linalg.norm(block.hidden_state)
                
                # 2. Dynamic Allostasis: Adjust decay rate based on energy levels
                if current_l2 < 1.0:
                    decay = self.decay_hypo  # Hypometabolic: Retain energy to build baseline
                elif current_l2 > 4.0:
                    decay = self.decay_hyper  # Hypermetabolic: Aggressive cooling to prevent "fever"
                else:
                    decay = self.decay_base  # Homeostatic Baseline
                
                # 3. Apply the calculated decay
                block.hidden_state *= decay
                
                # 4. Inject the Hamiltonian pulse (scaled by operating-energy gain)
                gain = getattr(self, 'energy_gain', 1.0)
                block.hidden_state += (vector_256 * coupling_strength * gain)
                
                # 5. Thermal Clamping: Hard safety limit to prevent divergence
                new_norm = np.linalg.norm(block.hidden_state)
                if new_norm > self.thermal_clamp_max:
                    block.hidden_state = (block.hidden_state / new_norm) * self.thermal_clamp_max
                
                logger.debug(f"  [+] Block {i} - Energy: {current_l2:.2f} -> {new_norm:.2f} (Decay: {decay})")