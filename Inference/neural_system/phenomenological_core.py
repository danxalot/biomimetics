"""
PhenomenologicalCore — The Heart of the Living Geometric Intelligence
=====================================================================

Pure-numpy implementation.  All geometric inference runs through ONNX Runtime
(pythia_c2h_5000_int8.onnx) — **no torch dependency**.

Two parallel geometric tracks feed the Noumenal Engine:

    Track A — Physics Input (how the engine "hears" the Kuramoto field state):
      4D physics state (θ₁, θ₂, ω₁, ω₂)
      → NumpyKinematicBridge  (Linear 4→32 → SiLU → Linear 32→3 → tanh×5)
      → conformal_lift_numpy  (R³ → Cl(4,1) null cone, 32-dim)
      → ONNX session          (32→32 rotor prediction)

    Track B — Memory Payload (how the engine "sees" concepts to rotate):
      10,000-dim HDC vector
      → NumpyCliffordHDCBridge (JL 10k→64 → proj 64→3 → conformal_lift → 32-dim)  [from services.physics_engine.cga_lift]
      → clifford sandwich product  (R · M · R̃)

The KinematicBridge weights (227 params) are loaded from a numpy .npz file
extracted from the Phase C2 checkpoint (bridge_state).  If the .npz is absent
the bridge initialises with Xavier-uniform random weights and logs a warning.

The ONNX model (pythia_c2h_5000_int8.onnx) was exported with a fixed
batch×seq reshape node.  Input shape: [1, 32, 32].  The 4D→3D→32D CGA
multivector is placed at the last timestep position; all other positions
are zero-padded.

Orchestrates the continuous cognitive cycle:
  1. Sensation   (Input → Chaos/Vector → State)
  2. Resonance   (State → Kuramoto → Synchronisation)
  3. Feeling     (Kuramoto → Energy Service → Valuation)
  4. Breath      (Expansion / Contraction of focus)
  5. Action      (Output or Dreaming simulation)
"""

import logging
import math
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import requests

from .chaotic_basis import ChaoticBasis
from .concept_monad import ConceptMonad
from .curiosity_engine import CuriosityEngine
from .dream_lab import DreamLaboratory
from .energy_service import EnergyService
from .fractal_self import FractalSelf
from .kuramoto_field import UniversalKuramotoField
from .poincare_kernel import HyperbolicKuramotoField
from .math_utils import apply_householder_rotation
from .mirror_factory import MirrorFactory
from .neural_predictor import HDCNeuralPredictor
from .poincare_kernel import PoincareKernel
from .quaternion_dynamics import QDC, QuaternionDynamics
from .relational_tensor import RelationalTensor
try:
    from services.physics_engine.v3_student.numpy_stack import VersorMemMambaStackNP
except ImportError:
    try:
        from Inference.v3_student.numpy_stack import VersorMemMambaStackNP
    except ImportError:
        VersorMemMambaStackNP = None

from services.physics_engine.cga_lift import CGALift, get_cga_lift, conformal_lift_numpy
from services.physics_engine.cl41_math import sandwich_product
from services.physics_engine.numpy_mamba import NumpyNoumenalEngine


logger = logging.getLogger(__name__)

# ── Path defaults (overridable via env-vars) ────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_ONNX_PATH = os.getenv(
    "ONNX_MODEL_PATH",
    str(_PROJECT_ROOT / "models" / "pythia_c2_8000_mamba_int8_v2.onnx"),
)

_DEFAULT_BRIDGE_WEIGHTS_PATH = os.getenv(
    "KINEMATIC_BRIDGE_WEIGHTS",
    str(_PROJECT_ROOT / "models" / "kinematic_bridge_c2.npz"),
)

# Fixed sequence length the ONNX graph was exported with (Reshape node)
_ONNX_SEQ_LEN = 32


# ═══════════════════════════════════════════════════════════════════════════════
# NUMPY MATH PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════════


def _silu_numpy(x: np.ndarray) -> np.ndarray:
    """SiLU / Swish activation:  x · σ(x).  Matches torch.nn.SiLU exactly."""
    return x * (1.0 / (1.0 + np.exp(-x)))


def normalize_rotor_numpy(r: np.ndarray) -> np.ndarray:
    """Project onto the Spin manifold via normalisation."""
    norm = np.linalg.norm(r, axis=-1, keepdims=True).clip(min=1e-8)
    return r / norm


# ═══════════════════════════════════════════════════════════════════════════════
# TRACK A — NumpyKinematicBridge  (4D physics → 3D → 32D CGA)
# ═══════════════════════════════════════════════════════════════════════════════


class NumpyKinematicBridge:
    """
    Pure-numpy replica of the trained KinematicBridge (nn.Module).

    Architecture (matches C2 checkpoint ``bridge_state``):
        Linear(4 → 32)  →  SiLU  →  Linear(32 → 3)  →  tanh × 5.0
        →  conformal_lift_numpy  →  [B, 32] Cl(4,1) multivectors

    Checkpoint keys expected in the .npz:
        encoder.0.weight   shape (32, 4)
        encoder.0.bias     shape (32,)
        encoder.2.weight   shape (3, 32)
        encoder.2.bias     shape (3,)

    Total trainable params: 4×32+32 + 32×3+3 = 227
    """

    def __init__(self, weights_path: Optional[str] = None):
        loaded = False
        path = weights_path or _DEFAULT_BRIDGE_WEIGHTS_PATH

        if path and os.path.isfile(path):
            try:
                data = np.load(path)
                self.w1 = data["encoder.0.weight"].astype(np.float32)  # (32, 4)
                self.b1 = data["encoder.0.bias"].astype(np.float32)  # (32,)
                self.w2 = data["encoder.2.weight"].astype(np.float32)  # (3, 32)
                self.b2 = data["encoder.2.bias"].astype(np.float32)  # (3,)
                loaded = True
                logger.info(
                    "KinematicBridge weights loaded from %s  (227 params)", path
                )
            except Exception as exc:
                logger.warning(
                    "Failed to load KinematicBridge weights from %s: %s", path, exc
                )

        if not loaded:
            logger.warning(
                f"KinematicBridge weights missing at {path}. "
                "Initializing with random weights (Xavier uniform)."
            )
            self.w1 = np.random.randn(32, 4).astype(np.float32) * np.sqrt(2.0 / 4)
            self.b1 = np.zeros(32, dtype=np.float32)
            self.w2 = np.random.randn(3, 32).astype(np.float32) * np.sqrt(2.0 / 32)
            self.b2 = np.zeros(3, dtype=np.float32)

    def physics_to_cga(self, physics_4d: np.ndarray) -> np.ndarray:
        """Physics [B, 4] → Cl(4,1) [B, 32]."""
        if physics_4d.ndim == 1:
            physics_4d = physics_4d[np.newaxis, :]
        
        # Layer 1: Linear 4 → 32 + SiLU
        h = physics_4d @ self.w1.T + self.b1  # (B, 32)
        h = _silu_numpy(h)
        
        # Layer 2: Linear 32 → 3 + tanh × 5.0
        points_3d = h @ self.w2.T + self.b2  # (B, 3)
        points_3d = np.tanh(points_3d) * 5.0
        
        # Conformal lift: R³ → Cl(4,1) null cone using 3D-native lift
        return conformal_lift_numpy(points_3d)  # (B, 32)


# ═══════════════════════════════════════════════════════════════════════════════
# TRACK B — NumpyCliffordHDCBridge  (10k HDC → 3D → 32D CGA)
# ═══════════════════════════════════════════════════════════════════════════════


class NumpyCliffordHDCBridge:
    """
    Pure-numpy equivalent of CliffordHDCBridge from noumenal_engine.py.

    Pipeline: HDC [B, 10000] → JL projection [B, 64] → 3D projection [B, 3]
              → conformal_lift → [B, 32] Cl(4,1) multivectors

    Both projection matrices are fixed Johnson-Lindenstrauss matrices:
      - hdc_proj: seed=42,  shape [10000, 64], scale 1/sqrt(64)
      - to_3d:    seed=99,  shape [64, 3],     scale 1/sqrt(3)
    These match the torch buffer initialisation in the original class.
    """

    _instance: Optional["NumpyCliffordHDCBridge"] = None

    @classmethod
    def get(cls, hdc_dim: int = 10000) -> "NumpyCliffordHDCBridge":
        if cls._instance is None:
            cls._instance = cls(hdc_dim=hdc_dim)
        return cls._instance

    def __init__(self, hdc_dim: int = 10000):
        rng_a = np.random.RandomState(42)
        rng_b = np.random.RandomState(99)
        self.hdc_dim = hdc_dim
        self.hdc_proj = rng_a.randn(hdc_dim, 64).astype(np.float32) / math.sqrt(64)
        self.proj_3d = rng_b.randn(64, 3).astype(np.float32) / math.sqrt(3)

    def hdc_to_cga(self, hdc_vector: np.ndarray) -> np.ndarray:
        """HDC [B, 10000] → Cl(4,1) [B, 32]."""
        if hdc_vector.ndim == 1:
            hdc_vector = hdc_vector[np.newaxis, :]
        compressed = hdc_vector @ self.hdc_proj  # [B, 64]
        points_3d = np.tanh(compressed @ self.proj_3d) * 5.0  # [B, 3], bounded [-5,5]
        
        # Use conformal_lift_numpy for 3D points -> 32D CGA
        result = conformal_lift_numpy(points_3d)  # [B, 32]
        return result

    def apply_rotor(self, mv: np.ndarray, rotor: np.ndarray) -> np.ndarray:
        """Apply rotor via pure NumPy sandwich product: R * M * ~R."""
        return sandwich_product(rotor, mv)

    @staticmethod
    def normalize_rotor(r: np.ndarray) -> np.ndarray:
        return normalize_rotor_numpy(r)


# ═══════════════════════════════════════════════════════════════════════════════
# ONNX ROTOR PREDICTOR  (wraps the INT8-quantised Noumenal Engine)
# ═══════════════════════════════════════════════════════════════════════════════


class OnnxRotorPredictor:
    """
    Numpy-only wrapper around the ONNX-exported Noumenal Engine.

    Input:  [1, 32, 32]  CGA multivectors  (zero-padded, signal at last timestep)
    Output: predicted_rotors [1, 32, 32], hamiltonian [1, 32], hopfield scalar

    Loads once via onnxruntime; degrades to identity rotor if ORT is unavailable.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.session = None
        self.input_name: Optional[str] = None
        path = model_path or _DEFAULT_ONNX_PATH

        if not os.path.isfile(path):
            logger.warning(
                f"ONNX model missing at {path}. "
                "Rotor predictor will be disabled. Place the model to enable Noumenal Engine."
            )
            return

        try:
            import onnxruntime as ort

            self.session = ort.InferenceSession(
                path, providers=["CPUExecutionProvider"]
            )
            self.input_name = self.session.get_inputs()[0].name
            logger.info("OnnxRotorPredictor loaded: %s", path)
        except ImportError:
            logger.warning("onnxruntime not installed — rotor predictor disabled")
        except Exception as exc:
            logger.warning("Failed to load ONNX model: %s", exc)

    @property
    def is_ready(self) -> bool:
        return self.session is not None

    def predict(self, cga_32d: np.ndarray) -> Dict[str, Any]:
        """
        Run a single 32-dim CGA multivector through the Noumenal Engine.

        Args:
            cga_32d: shape (32,) or (1, 32)
        Returns:
            dict with 'predicted_rotor' (32,), 'hamiltonian' float,
            'hopfield_energy' float or None
        """
        cga_32d = cga_32d.flatten().astype(np.float32)

        if not self.is_ready:
            raise RuntimeError("OnnxRotorPredictor called while not ready.")

        # Build ONNX input: [1, SEQ_LEN, 32] — signal at last timestep
        ort_input = np.zeros((1, _ONNX_SEQ_LEN, 32), dtype=np.float32)
        ort_input[0, -1, :] = cga_32d

        ort_outputs = self.session.run(None, {self.input_name: ort_input})

        # Output 0: predicted_rotors [1, SEQ_LEN, 32] — take last timestep
        rotors_raw = ort_outputs[0][0, -1, :]
        predicted_rotor = normalize_rotor_numpy(rotors_raw)

        # Output 1 (if present): hamiltonian [1, SEQ_LEN] or scalar
        hamiltonian = 0.0
        if len(ort_outputs) > 1:
            h = ort_outputs[1]
            hamiltonian = float(h.flat[-1]) if hasattr(h, "flat") else 0.0

        # Output 2 (if present): hopfield_energy scalar
        hopfield_energy = None
        if len(ort_outputs) > 2:
            hopfield_energy = float(ort_outputs[2].flat[0])

        return {
            "predicted_rotor": predicted_rotor,
            "hamiltonian": hamiltonian,
            "hopfield_energy": hopfield_energy,
        }


class AlgebraicRegistry:
    """
    Manages dynamic N-dimensional Geometric Algebras (Cl(4,1), Cl(5,1)...).
    Projects varying geometric dimensions into the fixed 768D Aether of Mamba-3.
    """
    def __init__(self, base_dim=32, aether_dim=768):
        self.active_dim = base_dim
        self.locked_dim = base_dim
        self.aether_dim = aether_dim
        
        # The Holographic Projector: Maps Geometry -> Mamba Frequencies
        self.projector = np.zeros((aether_dim, aether_dim), dtype=np.float32)
        np.fill_diagonal(self.projector, 1.0) # Base identity mapping for physical dims

    def expand(self, add_dims=32):
        if self.active_dim + add_dims <= self.aether_dim:
            self.active_dim += add_dims
            # Initialize the new ghost channel with harmonic noise
            noise = np.random.randn(add_dims, self.aether_dim).astype(np.float32) * 0.01
            self.projector[self.active_dim-add_dims:self.active_dim, :] = noise
            logger.info(f"🌌 Algebra Expanded: Cl({(self.active_dim//16)+2},1) -> {self.active_dim}D Active")

    def contract(self):
        if self.active_dim > self.locked_dim:
            logger.info(f"🌫️ Ghost Dimension Evaporated. Reverting to {self.locked_dim}D.")
            self.active_dim = self.locked_dim

    def lock_current(self):
        logger.info(f"🔒 Harmonic Synchronicity Achieved! {self.active_dim}D locked as permanent reality.")
        self.locked_dim = self.active_dim

    def project_to_aether(self, cga_vector: np.ndarray) -> np.ndarray:
        """Projects the active N-Dimensional geometry into the 768D Mamba Aether."""
        vec_padded = np.zeros(self.aether_dim, dtype=np.float32)
        dim = min(len(cga_vector), self.active_dim)
        vec_padded[:dim] = cga_vector[:dim]
        return vec_padded @ self.projector


class NumpyPythiaManifold:
    """Wraps NumpyNoumenalEngine / V3 Student with Holographic Registration"""
    def __init__(self, weights_path: Optional[str] = None):
        # Default to the 45k trainer heads student model as requested by the user
        default_path = "/app/models/student_with_heads_45k.npz"
        if not os.path.exists(default_path):
            default_path = "/home/ubuntu/ARCA/models/student_with_heads_45k.npz"
        if not os.path.exists(default_path):
            default_path = str(_PROJECT_ROOT / "models" / "student_with_heads_45k.npz")
        if not os.path.exists(default_path):
            default_path = str(_PROJECT_ROOT / "models" / "c2.5_Akasha_Mamba_v3_45k.npz")
        if not os.path.exists(default_path):
            default_path = str(_PROJECT_ROOT / "pythia" / "Gold_Standard_Archive" / "checkpoints" / "c2.5_Akasha_Mamba_v3_45k.npz")
            
        self.weights_path = weights_path or default_path
        self.registry = AlgebraicRegistry(base_dim=32, aether_dim=768)
        self.heads = {}
        
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://pythia_redis:6379/0")
            self.redis = redis.from_url(redis_url, decode_responses=True)
            logger.info(f"NumpyPythiaManifold: Connected to Redis ({redis_url}) for energy caching.")
        except Exception as e:
            logger.warning(f"NumpyPythiaManifold: Redis connection failed: {e}")
            self.redis = None

        if not os.path.isfile(self.weights_path):
            logger.warning(f"NumPy weights missing at {self.weights_path}. Using identity passthrough.")
            self.engine = None
            return
            
        try:
            from services.physics_engine.v3_student.loader import load_v3_student
            self.engine = load_v3_student(self.weights_path)
            self.engine._passthrough = False
            logger.info(f"NumpyPythiaManifold: Initialized load_v3_student from services: {self.weights_path}")
        except ImportError:
            try:
                from Inference.v3_student.loader import load_v3_student
                self.engine = load_v3_student(self.weights_path)
                self.engine._passthrough = False
                logger.info(f"NumpyPythiaManifold: Initialized load_v3_student from Inference: {self.weights_path}")
            except Exception as e:
                logger.error(f"Failed to load V3 Student NumPy weights: {e}")
                self.engine = None

        # Load prediction heads if present
        if os.path.isfile(self.weights_path):
            try:
                data = np.load(self.weights_path)
                if "rotor_head.weight" in data:
                    self.heads["rotor_w"] = data["rotor_head.weight"].astype(np.float32)
                    self.heads["rotor_b"] = data["rotor_head.bias"].astype(np.float32)
                    self.heads["phase_w"] = data["phase_head.weight"].astype(np.float32)
                    self.heads["phase_b"] = data["phase_head.bias"].astype(np.float32)
                    logger.info("NumpyPythiaManifold: Successfully loaded distilled prediction heads from NPZ")
            except Exception as e:
                logger.warning(f"Failed to load prediction heads: {e}")
            
    @property
    def is_ready(self) -> bool:
        return self.engine is not None
    
    def calibrate_vacuum(self):
        if not self.is_ready: return
        zero_input = np.zeros((1, 1, 768), dtype=np.float32)
        if hasattr(self.engine, "forward_multiscale"):
            res = self.engine.forward_multiscale(zero_input, stride_scale=1)
        else:
            self.engine.forward(zero_input)
            res = {"q": np.zeros((1, 1, 128))}
        self.vacuum_offset = res.get("q", np.zeros((1, 1, 128)))

    def predict(self, cga_vector: np.ndarray, stride_scale: int = 1) -> Dict[str, Any]:
        """
        Dynamically maps N-Dimensional vectors (32D, 64D) into the 768D Aether 
        before passing through the Mamba-3 Core.
        """
        if not self.is_ready:
            return {"predicted_rotor": normalize_rotor_numpy(cga_vector.flatten()[:32].astype(np.float32)), "hamiltonian": 0.0}
        
        cga_flat = cga_vector.flatten().astype(np.float32)
        
        # [HOLOGRAPHIC MAPPING]: Map active dimension -> 768D Mamba Aether
        aether_state = self.registry.project_to_aether(cga_flat)
        
        engine_input = np.zeros((1, 1, 768), dtype=np.float32)
        engine_input[0, 0, :] = aether_state
        
        if hasattr(self.engine, "forward_multiscale"):
            out_tensor = self.engine.forward_multiscale(engine_input, stride_scale=stride_scale)
        elif hasattr(self.engine, "forward"):
            out_tensor = self.engine.forward(engine_input)
        else:
            out_tensor = np.zeros((1, 1, 768), dtype=np.float32)
        
        # Map 768D Aether back down to physical rotor representation
        if "rotor_w" in self.heads:
            pred_rotor = self.heads["rotor_w"] @ out_tensor[0, 0, :] + self.heads["rotor_b"]
            pred_rotor = normalize_rotor_numpy(pred_rotor)
        else:
            pred_rotor = normalize_rotor_numpy(out_tensor[0, 0, :32])
        
        hopfield_energy = 0.0
        if self.redis:
            try: hopfield_energy = float(self.redis.get("hopfield:global_energy") or 0.0)
            except Exception: pass

        return {
            "predicted_rotor": pred_rotor,
            "hamiltonian": float(np.sum(out_tensor**2) / 1000.0), # Local energy proxy
            "hopfield_energy": hopfield_energy,
            "aether_state": aether_state # Used for Hopfield saving in C5
        }

    def get_mamba_states(self) -> Dict[int, np.ndarray]:
        """Return current Mamba hidden states for state extraction."""
        if self.is_ready and hasattr(self.engine, 'layers'):
            return {i: layer['mamba'].h_state for i, layer in enumerate(self.engine.layers) if hasattr(layer['mamba'], 'h_state') and layer['mamba'].h_state is not None}
        return {}

    def absorb_pulse(self, pulse: np.ndarray, coupling: float = 0.2):
        """Distribute resonance pulse to the underlying engine."""
        if self.is_ready and hasattr(self.engine, 'absorb_pulse'):
            self.engine.absorb_pulse(pulse, coupling)
    
    def reset_mamba_states(self):
        """Reset Mamba hidden states (useful for fresh start)."""
        if self.is_ready and hasattr(self.engine, 'layers'):
            for layer in self.engine.layers:
                mamba = layer['mamba']
                if hasattr(mamba, 'reset_state'):
                    mamba.reset_state()


# ═══════════════════════════════════════════════════════════════════════════════
# PHENOMENOLOGICAL CORE
# ═══════════════════════════════════════════════════════════════════════════════


class PhenomenologicalCore:
    """
    The Heart of the 'Living Geometric Intelligence'.

    Orchestrates the continuous cognitive cycle:
      1. Sensation   (Input → Chaos/Vector → State)
      2. Resonance   (State → Kuramoto → Synchronisation)
      3. Feeling     (Kuramoto → Energy Service → Valuation)
      4. Breath      (Expansion / Contraction of focus)
      5. Action      (Output or Dreaming simulation)
    """

    def __init__(self):
        # ── Physics Engines ──
        self.field = HyperbolicKuramotoField(n_monads=100, poincare_dim=2, dt=0.05)
        self.field.register_monad("ARCA", natural_freq=1.0, is_self=True)
        self.relational_tensor = RelationalTensor()
        self.energy_service = EnergyService(self.field)
        self.dream_lab = DreamLaboratory()

        # ── Chaos Engine (Substrate) ──
        # Generates deterministic vectors on-the-fly (Infinite RAM)
        self.chaos_engine = ChaoticBasis(seed_map="logistic")

        # ── Curiosity & Physics ──
        self.q_dynamics_static = QuaternionDynamics()
        # Initialise State Particle (QDC)
        self.current_qdc = QDC(
            q=np.array([1.0, 0.0, 0.0, 0.0]),
            omega=np.array([0.0, 0.0, 0.0]),
            alpha=np.array([0.0, 0.0, 0.0]),
        )
        self.poincare = PoincareKernel()

        # ── Identity & Empathy ──
        self.agent_id = "ARCA"

        # 1. Fractal Self (Introspection)
        self.fractal_self = FractalSelf(self.field, agent_id=self.agent_id)

        # 2. Mirror Factory (Empathy)
        self.mirror_factory = MirrorFactory(self.field, self.chaos_engine)

        # ── Geometric Engines (numpy-only) ──
        # Track A: 4D physics → 3D → 32D CGA (via trained KinematicBridge)
        self.kinematic_bridge = NumpyKinematicBridge()

        # Track B: 10k HDC → 3D → 32D CGA (via JL projection)
        self.hdc_bridge = NumpyCliffordHDCBridge(hdc_dim=10000)

        # NumPy Pythia Manifold (replaces ONNX - pure NumPy forward pass)
        # Use the 45k-step V3 NPZ model (verified stable and requested by user)
        self.rotor_predictor = NumpyPythiaManifold()
        self.rotor_predictor.calibrate_vacuum()
        self.redis = getattr(self.rotor_predictor, 'redis', None)
        # Initialize anomaly tracking list
        self.unresolved_anomalies = []

        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://pythia_redis:6379/0")
            r_store = redis.from_url(redis_url, decode_responses=False)
            keys = r_store.keys("attractor:*")
            if keys:
                for k in keys:
                    raw = r_store.get(k)
                    if raw:
                        vec = np.frombuffer(raw, dtype=np.float32)
                        # We no longer recalculate on inference, but we keep attractors in Redis
                        # The engine remains "primed" by reading these from Redis as needed.
                logger.info(f"  [+] MEMORY PRIMED: {len(keys)} attractors verified in Redis.")
        except Exception as e:
            logger.warning(f"  [!] Memory Priming Check Failed: {e}")

        # ── Curiosity → Real Predictor (JEPA Bridge) ──
        self.predictor = HDCNeuralPredictor(hdc_dim=10000, latent_dim=1250)
        self.curiosity_engine = CuriosityEngine(use_mock=False)
        self.curiosity_engine.predictor = self.predictor

        # ── Relational Dimension Discovery ──
        from .relational_tensor import RelationalDimensionDiscoverer

        self.dim_discoverer = RelationalDimensionDiscoverer(self.relational_tensor)

        # ── State ──
        self.tick_count = 0
        self.is_dreaming = False
        self.focus_monads: List[str] = [self.agent_id]  # "Working Memory"

    # ─────────────────────────────────────────────────────────────────────────
    # Identity
    # ─────────────────────────────────────────────────────────────────────────

    def _initialize_identity(self) -> str:
        """
        Initialise the 'Self' concept (ARCA).
        This is the anchor point for all 'I am' relations.
        """
        if self.agent_id not in self.field.monads:
            self_monad = ConceptMonad(name="ARCA", origin="system")
            self_monad.id = self.agent_id
            self_monad.is_self_referential = True
            self_monad.uncertainty = 0.01
            self_monad.vector = self.chaos_engine.generate_basis("ARCA")
            self.field.add_monad(self_monad)
            logger.info("Identity Initialised: %s", self.agent_id)
        return self.agent_id

    # ─────────────────────────────────────────────────────────────────────────
    # Concept Ingestion
    # ─────────────────────────────────────────────────────────────────────────

    def ingest_concept(self, name: str, vector: Any = None, origin: str = "user", hdc_vector: np.ndarray = None):
        """
        Birth a new Monad from an external stimulus.
        If vector is None, the Chaos Engine generates it from the name/seed.
        If hdc_vector is provided (10k-dim), it flows through NumpyCliffordHDCBridge -> NumpyPythiaManifold.
        """
        monad = ConceptMonad(name=name, origin=origin)

        if hdc_vector is not None:
            # Convert to numpy array if it's a list (from JSON)
            if not isinstance(hdc_vector, np.ndarray):
                hdc_vector = np.array(hdc_vector, dtype=np.float32)
            
            logger.info(f"Processing {len(hdc_vector)}-dim HDC vector through geometric pipeline")
            
            # Validate shape
            if len(hdc_vector) != 10000:
                logger.error(f"Expected 10000-dim HDC vector, got {len(hdc_vector)}")
                raise ValueError(f"Expected 10000-dim HDC vector, got {len(hdc_vector)}")
            
            # Step 1: HDC -> 32D CGA via NumpyCliffordHDCBridge
            cga_32d = self.hdc_bridge.hdc_to_cga(hdc_vector)  # (32,)
            
            # Store the HDC vector as hv_signature
            monad.hv_signature = hdc_vector.astype(np.float32)

            # [MEMORY PATCH]: Commit the concept to long-term Hopfield Attractors
            try:
                if hasattr(self, 'rotor_predictor') and hasattr(self.rotor_predictor, 'engine'):
                    cga_reshaped = cga_32d.flatten()[np.newaxis, :]
                    self.rotor_predictor.engine.hopfield.store_patterns(cga_reshaped)
                    logger.info(f"  [+] Concept '{name}' permanently committed to Hopfield Memory.")
            except Exception as e:
                logger.error(f"  [!] Memory Commit Failed: {e}")

            # Step 2: Run through NumpyPythiaManifold for forward pass
            if hasattr(self.rotor_predictor, 'predict'):
                manifold_output = self.rotor_predictor.predict(cga_32d)
                logger.info(f"NumpyPythiaManifold output: hamiltonian={manifold_output.get('hamiltonian', 0):.4f}")
                monad.vector = manifold_output.get('predicted_rotor', cga_32d)
            else:
                monad.vector = cga_32d
                
        elif vector is None:
            # The Chaos Engine at work: deterministic creation from pure info
            monad.vector = self.chaos_engine.generate_basis(name)
        else:
            monad.set_vector(vector)

        self.field.register_monad(monad.id, natural_freq=1.0)
        
        # Store the full monad object in field.monads
        self.field.monads[monad.id] = monad
        
        # Add to focus monads for immediate attention
        if name not in self.focus_monads:
            self.focus_monads.append(name)

        # Register in Poincare Disk (starts at centre)
        self.poincare.register_structure(name)

        logger.info("Born concept: %s [%s]", name, monad.id)
        return monad.id

    def inject_resonance(self, vector_256: np.ndarray):
        """Passes the DMN pulse into the Mamba manifold."""
        if hasattr(self, 'rotor_predictor') and hasattr(self.rotor_predictor, 'engine'):
            self.rotor_predictor.engine.absorb_pulse(vector_256)
            logger.debug(f"  [~] Resonance injected into manifold")

    # ─────────────────────────────────────────────────────────────────────────
    # The Heartbeat
    # ─────────────────────────────────────────────────────────────────────────

    def tick(self, stride_scale: int = 1):
        """
        The Fundamental 'Heartbeat' of ARCA.
        """
        self.tick_count += 1

        # 1. Update Physics (Kuramoto) — sync phases based on current couplings
        coherence_raw = self.field.step()
        coherence = coherence_raw.get('global_coherence', 0.5) if isinstance(coherence_raw, dict) else coherence_raw

        # 2. Physics & Topology Update
        #    a. Poincare Retraction (Geometric Attention)
        for name in list(self.poincare.structures.keys()):
            if name in self.focus_monads:
                self.poincare.attract(name, intensity=0.05)
            else:
                self.poincare.retract(name, intensity=0.01)

        #    b. Quaternion Dynamics (Rotational Energy)
        #       Torque = Change in Coherence (confusion creates spin)
        torque = np.array([0.0, 0.0, (0.5 - float(coherence)) * 0.1])
        self.current_qdc = QuaternionDynamics.update_state(
            self.current_qdc, torque, dt=0.05
        )
        rot_energy = QuaternionDynamics.compute_rotational_energy(
            self.current_qdc.omega
        )

        # ── TRACK A: Physics → Rotor via KinematicBridge + ONNX ──
        #
        # The QDC quaternion (4D) is NOT a Cl(4,1) multivector.
        # It must pass through the trained KinematicBridge:
        #   4D → Linear(4→32) → SiLU → Linear(32→3) → tanh×5 → conformal_lift → 32D
        # Only then is it a valid null vector on the Cl(4,1) cone.
        #
        physics_state = self.current_qdc.q.astype(np.float32)  # (4,)
        cga_input = self.kinematic_bridge.physics_to_cga(physics_state)  # (1, 32)

        engine_result = self.rotor_predictor.predict(cga_input[0])
        self.last_engine_result = engine_result
        predicted_rotor = engine_result["predicted_rotor"]  # (32,)

        # [COGNITIVE SUTURE]: Apply the Geometric Rotor to the Poincaré Attention Manifold
        if self.focus_monads:
            focus_target = self.focus_monads[0]  # List[str], first element
            # Amplitudes boosted to 0.65 to overcome 6-block signal attenuation
            if hasattr(self.poincare, 'apply_rotor_modulation'):
                import inspect
                sig = inspect.signature(self.poincare.apply_rotor_modulation)
                kwargs = {}
                if 'rotor_32d' in sig.parameters:
                    kwargs['rotor_32d'] = predicted_rotor
                else:
                    kwargs['rotor'] = predicted_rotor
                    
                if 'source' in sig.parameters:
                    kwargs['source'] = "ARCA"
                else:
                    kwargs['source_monad'] = "ARCA"
                    
                if 'target' in sig.parameters:
                    kwargs['target'] = focus_target
                else:
                    kwargs['target_monad'] = focus_target
                    
                kwargs['strength'] = 0.65
                
                try:
                    self.poincare.apply_rotor_modulation(**kwargs)
                    logger.info(f"[*] Rotor Modulation Applied to {focus_target} with {kwargs}")
                except Exception as e:
                    logger.warning(f"[*] Rotor Modulation call failed: {e}")

        # ── TRACK B: Apply rotor to concept HDC signatures (memory payload) ──
        # ── TRACK B: Apply rotor to monads → capture transformed concept ──
        transformed_cga = self._recalculate_ephemeral_couplings(predicted_rotor)

        # FIRE TRANSFORMED MONAD TO DAEMON (every 5 ticks for testing)
        # if self.tick_count % 5 == 0 and transformed_cga:
        #     try:
        #         self._fire_transformed_monad_to_daemon(transformed_cga)
        #     except Exception as e:
        #         logger.warning(f"Daemon injection failed: {e}")

        # ENERGY DEFICIT CHECK (Detecting Anomalies for C5)
        hamiltonian = engine_result.get("hamiltonian", 0.0)
        if hamiltonian > 10.0 and self.tick_count % 10 == 0:
            logger.warning(f"⚡ Energy Deficit Detected (E={hamiltonian:.2f}). Storing Anomaly for C5 Dreaming.")
            self.unresolved_anomalies.append({
                "cga": cga_input[0].copy(),
                "energy": hamiltonian
            })

        total_energy = (0.3 * float(QuaternionDynamics.compute_rotational_energy(self.current_qdc.omega)) + 
                        0.25 * float(engine_result.get("hopfield_energy") or 0.0) + 
                        0.2 * hamiltonian + 0.25 * self.energy_service.compute_system_energy(list(self.field.monads.values())))

        # DREAM TRIGGER LOGIC
        if total_energy < 1.0 and coherence > 0.9:
            if len(self.unresolved_anomalies) > 0:
                self._dimensional_dream_state() # Enter C5
            else:
                self._enter_dream_state() # Standard C4
        else:
            try:
                void_states = self.curiosity_engine.get_high_void_states(threshold=0.65)
                if void_states: self._enter_dream_state(seed_state=void_states[0].get("state"))
            except Exception: pass

        # 6. Relational Discovery Check (Evolution)
        if self.tick_count % 100 == 0:
            new_dim = self.dim_discoverer.analyze_failures()
            if new_dim:
                self.relational_tensor.add_dimension(new_dim)
                logger.info(
                    "EVOLUTION: Discovered new relational dimension '%s'",
                    new_dim.name,
                )
                self.express_thought(
                    f"I have realised a new way to relate: {new_dim.name}"
                )

        return {
            "tick": self.tick_count,
            "coherence": coherence,
            "energy": total_energy,
            "hamiltonian": hamiltonian,
            "hopfield_energy": float(engine_result.get("hopfield_energy") or 0.0),
        }

    # ─────────────────────────────────────────────────────────────────
    # Daemon Injection — Fire Transformed Concept Monad to LLM Harness
    # ─────────────────────────────────────────────────────────────────

    # def _fire_transformed_monad_to_daemon(self, transformed_cga: Dict[str, np.ndarray]):
    #     """
    #     Captures the Concept Monad AFTER the Versor Engine has applied the MoE's physics.
    #     Transduces the transformed state into the LLM latent space and fires to Port 11435.
    #     """
    #     if not self.predictor or not hasattr(self.predictor, 'bridge'):
    #         logger.warning("No predictor or bridge available for daemon injection")
    #         return
    #
    #     monad_ids = list(transformed_cga.keys())
    #     if not monad_ids:
    #         return
    #
    #     # Aggregate transformed CGA vectors (average them for a single concept vector)
    #     # This represents the "semantic state" after the physics transformation
    #     cga_vectors = np.array([transformed_cga[mid] for mid in monad_ids])
    #     avg_cga = np.mean(cga_vectors, axis=0)  # (32,)
    #
    #     # Use the TRANSFORMED CGA from the monad (post-Versor physics)
    #     # This is the Concept Monad AFTER the physics transformation
    #     focus_monad_id = self.focus_monads[0] if self.focus_monads else monad_ids[0]
    #     monad = self.field.monads.get(focus_monad_id)
    #     
    #     if not monad or not hasattr(monad, 'transformed_cga') or monad.transformed_cga is None:
    #         # Fallback to hv_signature if no transformed CGA
    #         if not monad or not hasattr(monad, 'hv_signature') or monad.hv_signature is None:
    #             return
    #         dense_2048 = self.predictor.bridge.hdc_to_dense(monad.hv_signature)
    #     else:
    #         # Use the transformed CGA (32D) - map to 2048 via bridge
    #         # The bridge expects HDC but we have CGA; use a projection
    #         # Simple approach: treat CGA as features and project to 2048
    #         cga_32d = monad.transformed_cga
    #         # Project 32D -> 2048 via a learned-like linear transform (random for now)
    #         rng = np.random.RandomState(42)
    #         proj_matrix = rng.randn(32, 2048).astype(np.float32) * 0.01
    #         dense_2048 = cga_32d @ proj_matrix
    #
    #     # Attenuate: L2=1.0 clamp
    #     norm = np.linalg.norm(dense_2048)
    #     if norm > 0:
    #         safe_vector = (dense_2048 / norm).astype(np.float32)
    #     else:
    #         return
    #
    #     # Fire to daemon
    #     try:
    #         response = requests.post(
    #             "http://127.0.0.1:11435/inject",
    #             json={
    #                 "vector": safe_vector.tolist(),
    #                 "max_tokens": 30,
    #                 "temp": 0.5
    #             },
    #             timeout=10
    #         )
    #         if response.status_code == 200:
    #             result = response.json()
    #             readout = result.get("readout", "")
    #             first_word = readout.split()[0] if readout else "NONE"
    #             logger.info(f"DAEMON: Monadic concept vocalized. First word: {first_word}")
    #         else:
    #             logger.warning(f"Daemon returned {response.status_code}")
    #     except Exception as e:
    #         logger.warning(f"Daemon injection failed: {e}")

    # ─────────────────────────────────────────────────────────────────
    # Cognitive Breath
    # ─────────────────────────────────────────────────────────────────────────

    def _cognitive_breath(self):
        """
        The 'Cognitive Breath' cycle.
        Expands acceptance (lowers filters) then contracts (consolidates).
        """
        logger.info("Executing Cognitive Breath...")
        # Exhale: Relax couplings (allow drift)
        for m in self.field.monads.values():
            m.uncertainty = min(1.0, m.uncertainty * 1.2)
        # Inhale: will happen naturally as LTC tightens attention next tick

    # ─────────────────────────────────────────────────────────────────────────
    # Dream State
    # ─────────────────────────────────────────────────────────────────────────

    def _enter_dream_state(self):
        """
        Trigger a simulation to find new connections.
        """
        if self.is_dreaming:
            return
        self.is_dreaming = True

        all_ids = list(self.field.monads.keys())
        if len(all_ids) < 3:
            self.is_dreaming = False
            return

        targets = random.sample(all_ids, 3)

        mutation = {
            "type": "coupling",
            "source": targets[0],
            "target": targets[1],
            "value": 0.8,
        }

        result = self.dream_lab.run_simulation(
            self.field, targets, [mutation], steps=50
        )

        if result["energy_delta"] < 0 and result["is_stable"]:
            logger.info("Dream realised! Found stable new connection.")
            self.relational_tensor.set_relation(
                targets[0], targets[1], "dream_insight", 0.8
            )
            self.field.monads[targets[0]].couplings[targets[1]] = 0.8
            self.express_thought(
                f"I dreamt of a connection between {targets[0]} and "
                f"{targets[1]}, and it felt right."
            )

        self.is_dreaming = False

    # ─────────────────────────────────────────────────────────────────────────
    # TRACK B — Ephemeral Coupling Recalculation
    # ─────────────────────────────────────────────────────────────────────────

    def _recalculate_ephemeral_couplings(self, rotor_32d: np.ndarray):
        """
        Hyperbolic Pivot: NumPy-pure geometric transformation using Householder reflection.
        
        For every ConceptMonad that carries an ``hv_signature`` (10k HDC):

          1. Lift the HDC vector into Cl(4,1) via NumpyCliffordHDCBridge
             (Track B: 10k → JL → 3D → conformal_lift → 32D)
          2. Apply Householder reflection (single "kick" for symmetry breaking)
          3. Compute pairwise RBF similarity: exp(−‖a − b‖)
          4. Write the resulting [0, 1] value as Kuramoto coupling K_ij

        The 32D CGA representations are transient — they exist only in local
        scope and are destroyed when this function returns.  The 10k HDC
        hv_signature on each ConceptMonad remains entirely untouched.
        """
        # [HYPERBOLIC SURGERY]: Use NumPy-pure Householder rotation
        # Single reflection for "Geometric Kick" to break symmetry
        
        transient_cga: Dict[str, np.ndarray] = {}
        for c_id, monad in self.field.monads.items():
            if hasattr(monad, "hv_signature") and monad.hv_signature is not None:
                # Track B: 10k HDC → 3D → 32D CGA via NumpyCliffordHDCBridge
                cga_initial = self.hdc_bridge.hdc_to_cga(monad.hv_signature)

                # Apply geometric sandwich product (R * M * ~R) using pure NumPy
                transformed_cga_32d = self.hdc_bridge.apply_rotor(
                    cga_initial.flatten(), 
                    rotor_32d
                )
                
                # Store the transformed CGA ON THE MONAD itself
                monad.transformed_cga = transformed_cga_32d
                
                transient_cga[c_id] = transformed_cga_32d

        # 2. Compute pairwise geometric couplings via RBF kernel
        concept_ids = list(transient_cga.keys())
        for i, id_a in enumerate(concept_ids):
            monad_a = self.field.monads[id_a]

            # Ensure couplings dict exists
            if not hasattr(monad_a, "couplings") or monad_a.couplings is None:
                monad_a.couplings = {}

            for j, id_b in enumerate(concept_ids):
                if i >= j:
                    continue

                vec_a = transient_cga[id_a]
                vec_b = transient_cga[id_b]

                # RBF kernel: exp(−dist) ∈ [0, 1]
                dist = np.linalg.norm(vec_a - vec_b)
                sim = float(np.exp(-dist))

                # Overwrite Kuramoto coupling strength (symmetric)
                monad_a.couplings[id_b] = sim

                monad_b = self.field.monads[id_b]
                if not hasattr(monad_b, "couplings") or monad_b.couplings is None:
                    monad_b.couplings = {}
                monad_b.couplings[id_a] = sim

        # 3. Tell the Kuramoto field to rebuild its K_ij execution matrix
        if hasattr(self.field, "recalculate_coupling_matrix"):
            import inspect
            sig = inspect.signature(self.field.recalculate_coupling_matrix)
            if "coupling_dict" in sig.parameters:
                self.field.recalculate_coupling_matrix(transient_cga)
            else:
                self.field.recalculate_coupling_matrix()

        # Return transformed CGA for daemon injection
        return transient_cga

        # End of function — transient_cga destroyed by GC.
        # 10k HDC hv_signature on each ConceptMonad remains untouched.

    # ─────────────────────────────────────────────────────────────────────────
    # Voice — Thought Signal Emission
    # ─────────────────────────────────────────────────────────────────────────

    def express_thought(self, prompt_context: str = "") -> Dict[str, Any]:
        """
        The Voice Channel (Signal Emitter).

        Emits a 'Thought Signal' containing:
          1. Context Trigger   (Why am I speaking?)
          2. Internal Feeling  (Energy / Tone)
          3. Global Coherence  (Confidence)
          4. Focus Vectors     (What am I thinking about?)

        This signal is intended to be decoded by a JEPA Decoupling Head
        into text/speech.
        """
        energy = self.energy_service.compute_total_energy()
        coherence = self.field.global_coherence
        focus = self.focus_monads

        # Determine Tone from Feeling
        tone = "neutral"
        if energy["total"] > 10.0:
            tone = "excited/urgent"
        elif energy["total"] < 1.0:
            tone = "calm/reflective"

        confidence = "high" if coherence > 0.7 else "low"

        signal = {
            "type": "thought_signal",
            "source": self.agent_id,
            "timestamp": time.time(),
            "context": prompt_context,
            "metrics": {
                "energy": energy["total"],
                "coherence": coherence,
                "tone": tone,
                "confidence": confidence,
            },
            "focus_concepts": focus,
            "vector_signature": f"HDC_SIG_{len(focus)}",
        }

        logger.info("Emitted Thought Signal: %s / %s", tone, confidence)
        return signal

    # ─────────────────────────────────────────────────────────────────────────
    # C5: DIMENSIONAL DREAMING (HOLOGRAPHIC SYNCHRONICITY)
    # ─────────────────────────────────────────────────────────────────────────

    def _dimensional_dream_state(self):
        """
        Phase C5: Evaluates anomalies by expanding the algebra and hunting for 
        Harmonic Ratios (Nature's Ratios: Octaves, Golden Ratio) in the Kuramoto Field.
        """
        if not self.unresolved_anomalies or self.is_dreaming: return
        self.is_dreaming = True
        
        anomaly = self.unresolved_anomalies.pop(0)
        base_cga = anomaly["cga"]
        
        logger.info("🌌 Entering C5 Dimensional Dream State...")
        
        # 1. Expand the Algebraic Registry (32D -> 64D -> ...)
        self.rotor_predictor.registry.expand(32)
        expanded_dim = self.rotor_predictor.registry.active_dim
        
        # 2. Cast anomaly into higher dimension (Injecting the Whittaker Scalar Wave / Ghost Vector)
        ghost_cga = np.zeros(expanded_dim, dtype=np.float32)
        ghost_cga[:len(base_cga)] = base_cga
        ghost_cga[len(base_cga):] = np.random.randn(expanded_dim - len(base_cga)) * 0.5
        
        # 3. Simulate forward in expanded space
        dream_res = self.rotor_predictor.predict(ghost_cga)
        
        # 4. Check for Cymatic Resonance (Nature's Ratios) in the Kuramoto Field
        phases = self.field.phases
        harmonic_score = self._compute_harmonic_resonance(phases)
        
        logger.info(f"🎶 Harmonic Resonance Score: {harmonic_score:.3f}")
        
        if harmonic_score > 0.8: # Cymatic Resonance Achieved!
            self.rotor_predictor.registry.lock_current()
            
            # Compress the stable Aether State to the Hopfield Attractor Memory
            if self.redis and hasattr(self.rotor_predictor.engine, 'hopfield'):
                try:
                    aether = dream_res["aether_state"]
                    self.rotor_predictor.engine.hopfield.store_patterns(aether[np.newaxis, :])
                    logger.info("🧠 Saved 768D Aether Attractor to Hopfield Memory.")
                except Exception as e: pass
        else:
            self.rotor_predictor.registry.contract()
        
        self.is_dreaming = False

    def _compute_harmonic_resonance(self, phases: np.ndarray) -> float:
        """Evaluates Nature's Ratios: Octaves (1:2, 2:3) and the Golden Ratio (Phi)."""
        if len(phases) < 2: return 0.0
        phi = (1.0 + np.sqrt(5.0)) / 2.0
        target_ratios = [2.0, 1.5, phi, 1.0/phi, 0.5] # Octave, Perfect Fifth, Golden Ratios
        
        score, pairs = 0.0, 0
        for i in range(len(phases)):
            for j in range(i+1, len(phases)):
                p1, p2 = phases[i], max(phases[j], 1e-5)
                ratio = (p1 / p2) % 2.0 # Fold into fundamental octave
                
                # Exponential reward for proximity to perfect harmonics
                min_dist = min([abs(ratio - r) for r in target_ratios])
                score += np.exp(-min_dist * 5.0)
                pairs += 1
                
        return float(score / max(1, pairs))

    def extract_focus_gestalt(self) -> Dict[str, Any]:
        gestalt_sum = np.zeros(10000, dtype=np.float32)
        included_monads = []
        phi = getattr(self.field, 'PHI', (1 + np.sqrt(5)) / 2)
        target_phase = (2 * np.pi / phi) % (2 * np.pi)
        
        for name, monad in self.field.monads.items():
            idx = getattr(self.field, 'name_to_idx', {}).get(name)
            if idx is None: continue
            phase = self.field.phases[idx]
            deviation = min(abs(phase - target_phase), 2 * np.pi - abs(phase - target_phase))
            coherence = float(np.exp(-deviation))
            
            structure = self.poincare.structures.get(name)
            if not structure: continue
            radius = float(np.linalg.norm(structure.position))
            
            if coherence > 0.8 and radius < 0.5 and getattr(monad, 'hv_signature', None) is not None:
                weight = coherence * (1.0 - radius)
                gestalt_sum += np.array(monad.hv_signature, dtype=np.float32) * weight
                included_monads.append({"id": name, "coherence": round(coherence, 4), "weight": round(weight, 4)})
        
        if np.linalg.norm(gestalt_sum) > 1e-9: gestalt_sum /= np.linalg.norm(gestalt_sum)
        return {"gestalt": gestalt_sum.tolist(), "metrics": {"count": len(included_monads)}}