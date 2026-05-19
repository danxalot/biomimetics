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


class NumpyPythiaManifold:
    """
    Pure-NumPy Akasha 2 Hamiltonian MoE wrapper around NoumenalEngine.
    Replaces ONNX RotorPredictor - NO torch, NO ONNX.
    
    Wraps NoumenalEngine from app.noumenal_engine for full MoE support.
    Loads model weights from /models/pythia_manifold_23k_mature.npz
    """
    
    def __init__(self, weights_path: Optional[str] = None):
        # Default to the 23k-step GOLD STANDARD manifold (verified stable)
        self.weights_path = weights_path or str(_PROJECT_ROOT / "models" / "pythia_manifold_23k_gold_standard.npz")
        
        # Redis connection for pre-calculated energy values
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
            weights = dict(np.load(self.weights_path, allow_pickle=False))
            # Model configuration matching 23k Gold Standard (128-state Mamba, 4-experts SMoE-HE)
            config = {
                'embed_dim': 256,
                'mv_dim': 32,
                'n_layers': 6,
                'n_heads': 8,
                'n_experts': 4
            }
            # Recover NoteBlock state pools from Redis
            initial_pools = {}
            if self.redis:
                try:
                    # We need a binary-capable client for the numpy arrays
                    redis_url = os.getenv("REDIS_URL", "redis://pythia_redis:6379/0")
                    r_bin = redis.from_url(redis_url, decode_responses=False)
                    for i in range(config['n_layers']):
                        raw = r_bin.get(f"noteblock:state_pool:{i}")
                        if raw:
                            # 64 pools of 256-dim embeddings (Gold Standard config)
                            arr = np.frombuffer(raw, dtype=np.float32).reshape(64, 256)
                            initial_pools[i] = arr
                except Exception as e:
                    logger.debug(f"NoteBlock pool recovery failed: {e}")

            self.engine = NumpyNoumenalEngine(weights, config, initial_pools=initial_pools)
            logger.info(f"NumPyPythiaManifold initialized with full-fidelity engine: {self.weights_path}")
            
        except Exception as e:
            logger.error(f"Failed to load full-fidelity NumPy weights: {e}")
            self.engine = None

    def _load_weights(self):
        """Deprecated: Logic moved to __init__."""
        pass
            
    @property
    def is_ready(self) -> bool:
        return hasattr(self, 'engine') and self.engine is not None
    
    def predict(self, cga_32d: np.ndarray) -> Dict[str, Any]:
        """
        Run the 32-dim CGA input through NoumenalEngine (Akasha 2 MoE).
        
        Args:
            cga_32d: shape (32,) or (1, 32)
            
        Returns:
            dict with 'predicted_rotor' (32,), 'hamiltonian' float, 'hopfield_energy' float
        """
        if not self.is_ready:
            # Identity passthrough if engine not loaded
            predicted_rotor = normalize_rotor_numpy(cga_32d.flatten().astype(np.float32))
            return {
                "predicted_rotor": predicted_rotor,
                "hamiltonian": 0.0,
                "hopfield_energy": 0.0,
            }
        
        try:
            # NoumenalEngine expects [B, T, 32] - add batch and time dims
            cga = cga_32d.flatten().astype(np.float32)
            engine_input = cga[np.newaxis, np.newaxis, :]  # [1, 1, 32]
            
            # Forward pass through NoumenalEngine (Akasha 2 MoE)
            result = self.engine.forward(engine_input)
            
            # Fetch pre-calculated Hopfield energy from Redis
            hopfield_energy = 0.0
            if self.redis:
                try:
                    val = self.redis.get("hopfield:global_energy")
                    if val is not None:
                        hopfield_energy = float(val)
                except Exception as e:
                    logger.debug(f"Redis fetch failed: {e}")

            # Persist updated NoteBlock state pools to Redis (on every prediction)
                try:
                    import redis
                    redis_url = os.getenv("REDIS_URL", "redis://pythia_redis:6379/0")
                    r_bin = redis.from_url(redis_url, decode_responses=False)
                    pools = self.engine.get_state_pools()
                    for i, pool in pools.items():
                        r_bin.set(f"noteblock:state_pool:{i}", pool.tobytes())
                except Exception as e:
                    logger.debug(f"NoteBlock pool persistence failed: {e}")

            return {
                "predicted_rotor": result["predicted_rotor"],
                "hamiltonian": result.get("hamiltonian", 0.0),
                "hopfield_energy": hopfield_energy,
            }
            
        except Exception as e:
            import traceback
            logger.warning(f"NoumenalEngine forward pass failed: {e}. Using identity passthrough.")
            logger.warning(f"  Traceback: {traceback.format_exc()}")
            predicted_rotor = normalize_rotor_numpy(cga_32d.flatten().astype(np.float32))
            return {
                "predicted_rotor": predicted_rotor,
                "hamiltonian": 0.0,
                "hopfield_energy": 0.0,
            }
    
    def get_mamba_states(self) -> Dict[int, np.ndarray]:
        """Return current Mamba hidden states for state extraction."""
        # NoumenalEngine stores states in self.engine.blocks
        if hasattr(self.engine, 'blocks'):
            return {i: block.get_state() for i, block in enumerate(self.engine.blocks)}
        return {}

    def absorb_pulse(self, pulse: np.ndarray, coupling: float = 0.2):
        """Distribute resonance pulse to the underlying engine."""
        if self.is_ready:
            self.engine.absorb_pulse(pulse, coupling)
    
    def reset_mamba_states(self):
        """Reset Mamba hidden states (useful for fresh start)."""
        if hasattr(self.engine, 'blocks'):
            for block in self.engine.blocks:
                if hasattr(block, 'reset_state'):
                    block.reset_state()


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
        # Use 23k-step GOLD STANDARD manifold (verified stable)
        gold_path = str(_PROJECT_ROOT / "models" / "pythia_manifold_23k_gold_standard.npz")
        self.rotor_predictor = NumpyPythiaManifold(weights_path=gold_path)

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

    def tick(self):
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
        predicted_rotor = engine_result["predicted_rotor"]  # (32,)

        # [COGNITIVE SUTURE]: Apply the Geometric Rotor to the Poincaré Attention Manifold
        if self.focus_monads:
            focus_target = self.focus_monads[0]  # List[str], first element
            # Amplitudes boosted to 0.65 to overcome 6-block signal attenuation
            if hasattr(self.poincare, 'apply_rotor_modulation'):
                self.poincare.apply_rotor_modulation(
                    rotor=predicted_rotor,
                    source_monad="ARCA",
                    target_monad=focus_target,
                    strength=0.65
                )
                logger.info(f"[*] Rotor Modulation Applied: {focus_target} (Strength: 0.65)")

        # ── TRACK B: Apply rotor to concept HDC signatures (memory payload) ──
        # ── TRACK B: Apply rotor to monads → capture transformed concept ──
        transformed_cga = self._recalculate_ephemeral_couplings(predicted_rotor)

        # FIRE TRANSFORMED MONAD TO DAEMON (every 5 ticks for testing)
        # if self.tick_count % 5 == 0 and transformed_cga:
        #     try:
        #         self._fire_transformed_monad_to_daemon(transformed_cga)
        #     except Exception as e:
        #         logger.warning(f"Daemon injection failed: {e}")

        # 3. Compute Energy (Feeling)
        base_energy = self.energy_service.compute_system_energy(
            list(self.field.monads.values())
        )
        total_energy = base_energy + rot_energy

        energy_state = {
            "total": total_energy,
            "potential_sync": 0,
            "rotational": rot_energy,
            "hamiltonian": engine_result["hamiltonian"],
            "hopfield_energy": engine_result.get("hopfield_energy", 0.0),
        }

        # 4. Check for Spontaneous Transitions (Phase Change)
        if energy_state["potential_sync"] > 50.0:
            self._cognitive_breath()

        # 5. Dream Check (idle processing)
        #    If energy is low (boredom) and coherence is high (stagnation), Dream.
        if energy_state["total"] < 1.0 and coherence > 0.9:
            self._enter_dream_state()

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
            "energy": energy_state["total"],
            "hamiltonian": energy_state["hamiltonian"],
"hopfield_energy": energy_state.get("hopfield_energy", 0.0),
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

    def extract_focus_gestalt(self) -> Dict[str, Any]:
        """
        Aggregate phase-locked and focused monads into a single 10,000D super-vector.
        
        Logic:
        1. Select monads with phase-lock coherence R > 0.8 (resonant with BG3)
        2. Select monads with Poincare center-proximity r < 0.5 (focused attention)
        3. Superimpose their 10,000D HDC signatures
        4. Normalize the resulting gestalt vector
        """
        gestalt_sum = np.zeros(10000, dtype=np.float32)
        included_monads = []
        
        # Target phase for BG3 resonance (Golden Angle)
        # Using self.field.PHI if available, else standard Golden Ratio
        phi = getattr(self.field, 'PHI', (1 + np.sqrt(5)) / 2)
        target_phase = (2 * np.pi / phi) % (2 * np.pi)
        
        # Iterate through known monad objects
        for name, monad in self.field.monads.items():
            # Get phase from field dynamics
            idx = getattr(self.field, 'name_to_idx', {}).get(name)
            if idx is None:
                continue
            
            phase = self.field.phases[idx]
            
            # 1. Check Coherence (R > 0.8)
            # R = exp(-|phase - target|) where target is BG3
            deviation = abs(phase - target_phase)
            deviation = min(deviation, 2 * np.pi - deviation)
            coherence = float(np.exp(-deviation))
            
            # 2. Check Attention (r < 0.5)
            # Use the "outer" Poincare kernel for system attention (Working Memory focus)
            structure = self.poincare.structures.get(name)
            if not structure:
                # Fallback to field's internal poincare if outer doesn't have it
                if hasattr(self.field, 'poincare'):
                    structure = self.field.poincare.structures.get(name)
            
            if not structure:
                continue
            
            radius = float(np.linalg.norm(structure.position))
            
            # Thresholding for Gestalt Inclusion
            if coherence > 0.8 and radius < 0.5:
                # Check for HDC signature
                hv = getattr(monad, 'hv_signature', None)
                if hv is not None:
                    # Ensure it's numpy and float for sum
                    hv_array = np.array(hv, dtype=np.float32)
                    
                    # Weight by combination of resonance and focus
                    weight = coherence * (1.0 - radius)
                    gestalt_sum += hv_array * weight
                    
                    included_monads.append({
                        "id": name,
                        "coherence": round(coherence, 4),
                        "radius": round(radius, 4),
                        "weight": round(weight, 4)
                    })
        
        # Final Normalization of the super-vector
        gestalt_norm = np.linalg.norm(gestalt_sum)
        if gestalt_norm > 1e-9:
            gestalt_sum /= gestalt_norm
            
        return {
            "gestalt": gestalt_sum.tolist(),
            "monads": included_monads,
            "metrics": {
                "count": len(included_monads),
                "total_energy": self.energy_service.compute_total_energy() if self.energy_service else 0.0,
                "global_coherence": self.field.compute_global_coherence() if hasattr(self.field, 'compute_global_coherence') else 0.0,
                "timestamp": time.time()
            }
        }
