"""
PhenomenologicalCore — The Heart of the Living Geometric Intelligence
=====================================================================

Pure-NumPy implementation.  All geometric inference runs through
NumpyPythiaManifold (NumpyNoumenalEngine) — no torch, no ONNX dependency.

Two parallel geometric tracks feed the Noumenal Engine:

    Track A — Physics Input (how the engine "hears" the Kuramoto field state):
      4D quaternion state [w, x, y, z]  (unit-sphere normalised)
      → NumpyKinematicBridge  (Linear 4→32 → SiLU → Linear 32→3 → tanh×5)
      → conformal_lift_numpy  (R³ → Cl(4,1) null cone, 32-dim)
      → NumpyPythiaManifold   (32-layer VersorMemMambaStack_v3, 32→32 rotor)

    Track B — Memory Payload (how the engine "sees" concepts to rotate):
      10,000-dim HDC vector
      → NumpyCliffordHDCBridge (JL 10k→64 → proj 64→3 → conformal_lift → 32-dim)
      → clifford sandwich product  (R · M · R̃)

The KinematicBridge weights (227 params) are loaded from a numpy .npz file
extracted from the Phase C2 checkpoint (bridge_state).  If the .npz is absent
the bridge initialises with Xavier-uniform random weights and logs a warning.

The NumpyPythiaManifold wraps NumpyNoumenalEngine loaded from
pythia_manifold_23k_gold_standard.npz — the Phase C3 V3-Strict 65K-step
checkpoint (131.2M params, d_model=768, d_state=512, 32 layers).

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
from .memory_maintainer import MemoryMaintainer
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

_DEFAULT_BRIDGE_WEIGHTS_PATH = os.getenv(
    "KINEMATIC_BRIDGE_WEIGHTS",
    str(_PROJECT_ROOT / "models" / "kinematic_bridge_c2.npz"),
)


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


# --- Symmetry-Equivariant Preprocessing (CERN/TOTEM 2x Gauge Limits) ---
GAUGE_LIMIT = 5.0  # Canonical bound for spatial embeddings in Akasha 2


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

    def physics_to_cga(self, physics_4d: np.ndarray, domain: str = "default") -> np.ndarray:
        """Physics [B, 4] → Cl(4,1) [B, 32]."""
        if physics_4d.ndim == 1:
            physics_4d = physics_4d[np.newaxis, :]
        
        # Layer 1: Linear 4 → 32 + SiLU
        h = physics_4d @ self.w1.T + self.b1  # (B, 32)
        h = _silu_numpy(h)
        
        # Layer 2: Linear 32 → 3 + tanh × GAUGE_LIMIT
        # Symmetry-Equivariant Scaling matching CERN/TOTEM 2x phase
        points_3d = h @ self.w2.T + self.b2  # (B, 3)

        # Apply LayerNorm before conformal lift for 'relativity' domain to prevent explosion
        if domain == "relativity":
            mean = np.mean(points_3d, axis=-1, keepdims=True)
            var = np.var(points_3d, axis=-1, keepdims=True)
            points_3d = (points_3d - mean) / np.sqrt(var + 1e-5)

        points_3d = np.tanh(points_3d) * GAUGE_LIMIT
        
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
        points_3d = np.tanh(compressed @ self.proj_3d) * GAUGE_LIMIT  # [B, 3], bounded [-GAUGE_LIMIT, GAUGE_LIMIT]
        
        # Use conformal_lift_numpy for 3D points -> 32D CGA
        result = conformal_lift_numpy(points_3d)  # [B, 32]
        return result

    def apply_rotor(self, mv: np.ndarray, rotor: np.ndarray) -> np.ndarray:
        """Apply rotor via pure NumPy sandwich product: R * M * ~R."""
        return sandwich_product(rotor, mv)

    @staticmethod
    def normalize_rotor(r: np.ndarray) -> np.ndarray:
        return normalize_rotor_numpy(r)


class NumpyPythiaManifold:
    """
    Pure-NumPy Pythia Manifold — the active rotor predictor and Hamiltonian engine.

    Wraps NumpyNoumenalEngine (32-layer VersorMemMambaStack_v3, 131.2M params).
    Loaded from pythia_manifold_23k_gold_standard.npz (Phase C3, 65K steps).
    No torch, no ONNX — pure NumPy forward pass.
    """
    
    def __init__(self, weights_path: Optional[str] = None):
        # By default, use the new C2.5 45k V3 Student
        self.weights_path = weights_path or str(_PROJECT_ROOT / "models" / "c2.5_Akasha_Mamba_v3_45k.npz")
        
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
            # Import from the physics_engine.v3_student path
            from services.physics_engine.v3_student.loader import load_v3_student
            self.engine = load_v3_student(self.weights_path)
            
            # The V3 student outputs (B, T, 768). To maintain API compatibility with phenomenological_core:
            # We mock the dictionary expected.
            self.engine._passthrough = False
            self.engine.global_rotor = np.zeros(32, dtype=np.float32)
            self.engine.global_rotor[0] = 1.0 # Identity
            logger.info(f"NumPyPythiaManifold initialized with V3 Student: {self.weights_path}")
            
        except Exception as e:
            logger.error(f"Failed to load V3 Student NumPy weights: {e}")
            self.engine = None

    def _load_weights(self):
        """Deprecated: Logic moved to __init__."""
        pass
            
    @property
    def is_ready(self) -> bool:
        return hasattr(self, 'engine') and self.engine is not None
    
    def calibrate_vacuum(self):
        """Zero-state initialization to record ground energy E0."""
        if not self.is_ready:
            return
        logger.info("Calibrating Vacuum (Zero-State Initialization)...")
        # V3 student expects (B, T, 768)
        zero_input = np.zeros((1, 1, 768), dtype=np.float32)
        # Record hidden state vector as E0 baseline
        if hasattr(self.engine, "forward_multiscale"):
            res = self.engine.forward_multiscale(zero_input, stride_scale=1)
        else:
            out_tensor = self.engine.forward(zero_input)
            res = {"q": np.zeros((1, 1, 128))}
        self.vacuum_offset = res.get("q", np.zeros((1, 1, 128)))
        logger.info(f"Vacuum Calibrated. E0 offset norm: {np.linalg.norm(self.vacuum_offset):.4f}")

    def predict(self, cga_32d: np.ndarray, stride_scale: int = 1) -> Dict[str, Any]:
        """
        Run the 32-dim CGA input through NoumenalEngine/V3 Student.
        Supports Multi-Scale Rollout via stride_scale.
        """
        if not self.is_ready:
            # Identity passthrough if engine not loaded
            predicted_rotor = normalize_rotor_numpy(cga_32d.flatten().astype(np.float32))
            return {
                "predicted_rotor": predicted_rotor,
                "hamiltonian": 0.0,
                "hopfield_energy": 0.0,
                "q": np.zeros((1, 1, 128)),
                "p": np.zeros((1, 1, 128)),
                "gate_entropy": 0.0,
                "expert_load": [0.0, 0.0, 0.0, 0.0]
            }
        
        try:
            # V3 Student expects [B, T, 768]. We pad the 32D CGA to 768.
            cga = cga_32d.flatten().astype(np.float32)
            engine_input = np.zeros((1, 1, 768), dtype=np.float32)
            engine_input[0, 0, :32] = cga
            
            # Forward pass through V3 Student Stack
            if hasattr(self.engine, "forward_multiscale"):
                out_tensor = self.engine.forward_multiscale(engine_input, stride_scale=stride_scale)
            else:
                out_tensor = self.engine.forward(engine_input)
            
            # If the engine returned a dict (legacy), extract. Otherwise, process the V3 array.
            if isinstance(out_tensor, dict):
                result = out_tensor
            else:
                # Parse 768d back down to a 32d rotor (mock projection for now since head is missing)
                pred_rotor = normalize_rotor_numpy(out_tensor[0, 0, :32])
                result = {
                    "predicted_rotor": pred_rotor,
                    "hamiltonian": float(np.sum(out_tensor**2) / 1000.0), # Local proxy
                    "q": np.zeros((1, 1, 128)),
                    "p": np.zeros((1, 1, 128)),
                    "gate_entropy": 0.0,
                    "expert_load": [0.0, 0.0, 0.0, 0.0]
                }
            
            # Fetch pre-calculated Hopfield energy from Redis
            hopfield_energy = 0.0
            if self.redis:
                try:
                    val = self.redis.get("hopfield:global_energy")
                    if val is not None:
                        hopfield_energy = float(val)
                except Exception as e:
                    logger.debug(f"Redis fetch failed: {e}")

            return {
                "predicted_rotor": result["predicted_rotor"],
                "hamiltonian": result.get("hamiltonian", 0.0),
                "hopfield_energy": hopfield_energy,
                "q": result.get("q", np.zeros((1, 1, 128))),
                "p": result.get("p", np.zeros((1, 1, 128))),
                "gate_entropy": result.get("gate_entropy", 0.0),
                "expert_load": result.get("expert_load", [0.0, 0.0, 0.0, 0.0])
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
                "gate_entropy": 0.0,
                "expert_load": [0.0, 0.0, 0.0, 0.0]
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

        # [A] Seed the ARCA self-monad's hv_signature from the chaos engine.
        # This grounds all BG3 resonance computations and mirror-symmetry gates.
        # The field.register_monad("ARCA") call above creates a field-array entry,
        # but field.monads["ARCA"] is only populated via add_monad/register_concept.
        # We create the self-monad object here so it is available before any tick.
        try:
            _arca_hv = self.chaos_engine.generate_basis("ARCA")  # (10000,) float32 {-1,+1}
            from .concept_monad import ConceptMonad as _CM
            _arca_monad = _CM(name="ARCA", origin="system")
            _arca_monad.id = "ARCA"
            _arca_monad.is_self_referential = True
            _arca_monad.uncertainty = 0.01
            _arca_monad.hv_signature = _arca_hv
            _arca_monad.vector = _arca_hv  # also set vector for fallback paths
            self.field.monad_objects["ARCA"] = _arca_monad
            logger.info(
                "Self-monad 'ARCA' hv_signature seeded from ChaoticBasis "
                "(10k-dim, norm=%.2f)", float(np.linalg.norm(_arca_hv))
            )
        except Exception as _e:
            logger.warning("Failed to seed ARCA hv_signature: %s", _e)

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

        # NumpyPythiaManifold — pure NumPy forward pass, Phase C3 V3-Strict weights
        gold_path = str(_PROJECT_ROOT / "models" / "c2.5_Akasha_Mamba_v3_45k.npz")
        self.rotor_predictor = NumpyPythiaManifold(weights_path=gold_path)
        
        # [VACUUM CALIBRATION]: Initialise ground energy offset E0
        self.rotor_predictor.calibrate_vacuum()

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

        # Mirror redis from rotor_predictor for periodic Hopfield attractor sync
        self.redis = getattr(self.rotor_predictor, 'redis', None)

        # ── Curiosity → Real Predictor (JEPA Bridge) ──
        self.predictor = HDCNeuralPredictor(hdc_dim=10000, latent_dim=1250)
        self.curiosity_engine = CuriosityEngine(use_mock=False)
        self.curiosity_engine.predictor = self.predictor
        self.curiosity_engine.bind_kuramoto_field(self.field)

        # ── Memory Maintainer (SDM → InfiniMemory → LongMemory → Hopfield cascade) ──
        # Instantiated without MCP client; activate via self.memory_maintainer.set_mcp_client()
        # when an MCP tool caller is available. In-process usage is no-op until then.
        self.memory_maintainer = MemoryMaintainer(mcp_call_tool=None, dimension=10000)

        # [G] LiquidNeuralNetwork — adaptive time-constant smoothing for Kuramoto
        # phase derivatives. n_neurons=32 matches Kuramoto monad array size; n_inputs=1
        # takes the per-tick mean phase derivative as a scalar stimulus.
        try:
            from .liquid_neural_network import LiquidNeuralNetwork
            self.ltc = LiquidNeuralNetwork(n_neurons=32, n_inputs=1, dt=0.05)
            logger.info("LiquidNeuralNetwork (LTC) wired: 32 neurons, dt=0.05")
        except Exception as _ltc_e:
            logger.warning("LiquidNeuralNetwork unavailable: %s", _ltc_e)
            self.ltc = None

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

            # Step 3 (Task I): BG3 resonance as integration energy gate
            # Compute concept CGA vs self-monad CGA structural overlap.
            # High resonance → concept integrates easily (low cost).
            try:
                self_monad = self.field.monads.get(self.agent_id)
                self_cga = None
                if self_monad is not None and hasattr(self_monad, "hv_signature") and self_monad.hv_signature is not None:
                    self_cga = self.hdc_bridge.hdc_to_cga(self_monad.hv_signature).flatten()
                elif self_monad is not None and hasattr(self_monad, "vector") and self_monad.vector is not None:
                    v = np.asarray(self_monad.vector, dtype=np.float32).flatten()
                    if v.size >= 32:
                        self_cga = v[:32]

                if self_cga is not None:
                    concept_cga_flat = np.asarray(cga_32d, dtype=np.float64).flatten()
                    resonance_score = self.curiosity_engine.compute_resonance_potential(
                        concept_cga_flat, self_cga.astype(np.float64)
                    )
                else:
                    resonance_score = 0.5  # neutral if self monad not yet initialised

                # Gate integration energy
                base_integration_energy = getattr(monad, "energy", 1.0)
                monad.energy = float(base_integration_energy * (1.0 - 0.5 * resonance_score))
                monad.resonance_score = resonance_score
                logger.info(
                    "Concept '%s' resonance=%.3f → integration_energy=%.3f",
                    name, resonance_score, monad.energy,
                )

                # [J] Resonance-gated memory cascade:
                #   High resonance (>0.7) → deep ingest: full memory cascade + Hopfield store
                #   Low resonance  (<0.3) → surface registration only
                #   Mid resonance          → standard memory cascade (no Hopfield)
                if resonance_score > 0.7:
                    _ingest_importance = 2.0  # triggers Hopfield branch in sync_event
                    logger.info(
                        "[MemoryCascade] '%s' HIGH resonance (%.3f) → DEEP ingest "
                        "(memory cascade + Hopfield store)", name, resonance_score
                    )
                elif resonance_score < 0.3:
                    _ingest_importance = None  # skip cascade
                    logger.info(
                        "[MemoryCascade] '%s' LOW resonance (%.3f) → SURFACE "
                        "registration only (no memory cascade)", name, resonance_score
                    )
                else:
                    _ingest_importance = 1.0  # standard cascade, no Hopfield
                    logger.info(
                        "[MemoryCascade] '%s' MID resonance (%.3f) → standard "
                        "memory cascade", name, resonance_score
                    )

                if _ingest_importance is not None and hdc_vector is not None:
                    try:
                        self.memory_maintainer.sync_ingest(
                            hv=hdc_vector,
                            importance=_ingest_importance,
                            event_type="concept_ingest",
                        )
                    except Exception as _me:
                        logger.debug("Memory cascade failed for '%s': %s", name, _me)

            except Exception as _e:
                logger.debug("Resonance gate failed for '%s': %s", name, _e)
                monad.resonance_score = 0.0

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
        if hasattr(self, 'rotor_predictor') and self.rotor_predictor.is_ready:
            self.rotor_predictor.absorb_pulse(vector_256)
            logger.debug("  [~] Resonance injected into manifold")

    # ─────────────────────────────────────────────────────────────────────────
    # The Heartbeat
    # ─────────────────────────────────────────────────────────────────────────

    def tick(self, stride_scale: int = 1):
        """
        The Fundamental 'Heartbeat' of ARCA.
        """
        self.tick_count += 1

        # [MEMORY PATCH]: Dynamic Hopfield Attractor Seeding
        # Periodically sync new attractors discovered by C2.5 training run from Redis
        if self.tick_count % 500 == 0 and self.redis and hasattr(self, 'rotor_predictor') and hasattr(self.rotor_predictor, 'engine'):
            try:
                keys = self.redis.keys("attractor:*")
                if keys:
                    for k in keys:
                        raw = self.redis.get(k)
                        if raw:
                            vec = np.frombuffer(raw, dtype=np.float32)
                            # Shape the flat buffer into (1, D) pattern
                            if len(vec) == 512: # assuming pattern projection dim
                                self.rotor_predictor.engine.hopfield.store_patterns(vec[np.newaxis, :])
                    logger.info(f"[*] Dynamically synced {len(keys)} Hopfield attractors from Redis.")
            except Exception as e:
                logger.debug(f"Hopfield sync failed: {e}")

        # 1. Update Physics (Kuramoto) — sync phases based on current couplings
        coherence_raw = self.field.step()
        coherence = coherence_raw.get('global_coherence', 0.5) if isinstance(coherence_raw, dict) else coherence_raw

        # Cache metrics so GET /system/vitals can READ them without re-stepping the
        # field. The heartbeat (this method) is the single writer of physics state;
        # vitals must stay idempotent (it is polled ~2-3×/s by the UI + pythia).
        self.last_coherence_metrics = (
            coherence_raw if isinstance(coherence_raw, dict)
            else {"global_coherence": float(coherence_raw)}
        )

        # [G] LTC post-processing: run phase derivative mean through LiquidNeuralNetwork.
        # The LTC smooths the coherence signal with adaptive time constants,
        # preventing over-reaction to single-tick coherence spikes.
        if self.ltc is not None:
            try:
                n = len(self.field.monad_names)
                if n > 0:
                    _phase_input = np.array([float(coherence) - 0.5], dtype=np.float32)
                    _ltc_state = self.ltc.step(_phase_input)
                    # Blend LTC-smoothed coherence with raw coherence (70/30)
                    _ltc_coherence = float(np.clip(0.5 + float(np.mean(_ltc_state)) * 0.5, 0.0, 1.0))
                    coherence = 0.7 * coherence + 0.3 * _ltc_coherence
            except Exception as _ltc_err:
                logger.debug("LTC step failed: %s", _ltc_err)

        # Feed Kuramoto field state into Koopman operator — grows state history
        # so the void-to-dream pipeline (get_high_void_states) can activate.
        try:
            self.curiosity_engine.ingest_kuramoto_field()
        except Exception as _e:
            logger.debug("Curiosity field ingest failed: %s", _e)

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

        # ── TRACK A: Physics → Rotor via KinematicBridge + NumpyPythiaManifold ──
        #
        # QDC quaternion [w,x,y,z] → physics 4D state.
        # The kinematic bridge maps 4D → 3D → 32D CGA via:
        #   Linear(4→32) → SiLU → Linear(32→3) → tanh×5 → conformal_lift → 32D
        # We use quaternion components directly as the 4D physics state
        # (treating w,x,y,z as generalised coordinates on the unit sphere).
        # Normalise to unit sphere before passing (Task L).
        physics_4d = np.array(
            [self.current_qdc.q[0], self.current_qdc.q[1],
             self.current_qdc.q[2], self.current_qdc.q[3]],
            dtype=np.float32
        )
        physics_4d /= (np.linalg.norm(physics_4d) + 1e-8)  # normalise to unit sphere
        cga_input = self.kinematic_bridge.physics_to_cga(physics_4d)  # (1, 32)

        engine_result = self.rotor_predictor.predict(cga_input[0], stride_scale=stride_scale)
        self.last_engine_result = engine_result
        predicted_rotor = engine_result["predicted_rotor"]  # (32,)

        # [COGNITIVE SUTURE]: Apply the Geometric Rotor to the Poincaré Attention Manifold
        if self.focus_monads:
            focus_target = self.focus_monads[0]  # List[str], first element
            # Amplitudes boosted to 0.65 to overcome 6-block signal attenuation
            if hasattr(self.poincare, 'apply_rotor_modulation'):
                self.poincare.apply_rotor_modulation(
                    rotor_32d=predicted_rotor,
                    source="ARCA",
                    target=focus_target,
                    strength=0.65
                )
                logger.info(f"[*] Rotor Modulation Applied: {focus_target} (Strength: 0.65)")

        # ── TRACK B: Apply rotor to concept HDC signatures (memory payload) ──
        # ── TRACK B: Apply rotor to monads → capture transformed concept ──
        transformed_cga = self._recalculate_ephemeral_couplings(predicted_rotor)

        # ── Mirror Factory bilateral mapping (Task J) ──
        # For each monad with a transformed CGA, compute bilateral overlap with self.
        # Concepts with high bilateral symmetry attract higher coupling to each other.
        self._compute_mirror_symmetry(transformed_cga)

        # FIRE TRANSFORMED MONAD TO DAEMON (every 5 ticks for testing)
        # if self.tick_count % 5 == 0 and transformed_cga:
        #     try:
        #         self._fire_transformed_monad_to_daemon(transformed_cga)
        #     except Exception as e:
        #         logger.warning(f"Daemon injection failed: {e}")

        # 3. Compute Energy (Feeling)
        # Weighted combination: NumpyPythiaManifold engine outputs feed total energy.
        # E_total = 0.3*E_rot + 0.25*E_hopfield_engine + 0.2*E_hamiltonian_engine
        #         + 0.2*E_base (system monad avg) + 0.05*E_base_raw
        E_base = self.energy_service.compute_system_energy(
            list(self.field.monads.values())
        )
        E_hamiltonian_engine = float(engine_result.get("hamiltonian", 0.0))
        E_hopfield_engine = float(engine_result.get("hopfield_energy") or 0.0)
        E_rot = float(rot_energy)

        total_energy = (
            0.3 * E_rot
            + 0.25 * E_hopfield_engine
            + 0.2 * E_hamiltonian_engine
            + 0.2 * E_base
            + 0.05 * E_base
        )

        energy_state = {
            "total": total_energy,
            "potential_sync": 0,
            "rotational": E_rot,
            "base": E_base,
            "hamiltonian": E_hamiltonian_engine,
            "hopfield_energy": E_hopfield_engine,
        }

        # 4. Check for Spontaneous Transitions (Phase Change)
        if energy_state["potential_sync"] > 50.0:
            self._cognitive_breath()

        # 5. Dream Check (idle processing)
        #    Trigger dreaming when:
        #      (a) energy is low (boredom) AND coherence is high (stagnation), OR
        #      (b) EB-JEPA detects high-void states (unresolved anomalies)
        if energy_state["total"] < 1.0 and coherence > 0.9:
            self._enter_dream_state()
        else:
            # EB-JEPA void-to-dream pipeline (Task H + E)
            try:
                void_states = self.curiosity_engine.get_high_void_states(threshold=0.65)
                if void_states:
                    # Feed highest void state's CGA vector as dream seed
                    top_void = void_states[0]
                    logger.debug(
                        "EB-JEPA void detected (energy=%.3f, domain=%s) → triggering dream",
                        top_void["void_energy"],
                        top_void["domain"],
                    )
                    self._enter_dream_state(seed_state=top_void.get("state"))
            except Exception as _e:
                logger.debug("EB-JEPA void check failed: %s", _e)

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
            "gate_entropy": engine_result.get("gate_entropy", 0.0),
            "expert_load": engine_result.get("expert_load", [0.0, 0.0, 0.0, 0.0])
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

    def _enter_dream_state(self, seed_state: Optional[np.ndarray] = None):
        """
        Trigger a simulation to find new connections.

        Args:
            seed_state: Optional 32D CGA void state from EB-JEPA pipeline.
                        When provided it is converted back to a temporary HDC
                        monad and injected into the dream field as a starting
                        seed, steering the dream toward the detected void.
        """
        if self.is_dreaming:
            return
        self.is_dreaming = True

        all_ids = list(self.field.monads.keys())
        if len(all_ids) < 3:
            self.is_dreaming = False
            return

        # [E] CGA seed injection: if a void state was provided, create a
        # temporary monad seeded from it and include it in the dream targets.
        _seed_monad_id: Optional[str] = None
        if seed_state is not None:
            try:
                seed_arr = np.asarray(seed_state, dtype=np.float32).flatten()
                # Inverse-JL: project 32D CGA → 10k HDC via fixed random matrix (seed=777)
                _rng_inv = np.random.RandomState(777)
                _inv_proj = _rng_inv.randn(32, 10000).astype(np.float32) / np.sqrt(32)
                _seed_hv = np.tanh(seed_arr @ _inv_proj)  # (10000,)
                _norm = float(np.linalg.norm(_seed_hv))
                if _norm > 1e-8:
                    _seed_hv /= _norm

                _seed_monad_id = f"_dream_void_{self.tick_count}"
                from .concept_monad import ConceptMonad as _CM
                _seed_monad = _CM(name=_seed_monad_id, origin="dream")
                _seed_monad.id = _seed_monad_id
                _seed_monad.hv_signature = _seed_hv
                _seed_monad.uncertainty = 1.0
                self.field.monad_objects[_seed_monad_id] = _seed_monad
                all_ids = list(self.field.monads.keys())
                logger.debug(
                    "[Dream] Injected seed monad '%s' from void CGA (norm=%.4f)",
                    _seed_monad_id, _norm,
                )
            except Exception as _e:
                logger.debug("[Dream] Seed injection failed: %s", _e)
                _seed_monad_id = None

        # Select dream targets, biasing toward the seed monad if present
        if _seed_monad_id and _seed_monad_id in all_ids and len(all_ids) >= 3:
            other_ids = [i for i in all_ids if i != _seed_monad_id]
            targets = [_seed_monad_id] + random.sample(other_ids, min(2, len(other_ids)))
        else:
            targets = random.sample(all_ids, min(3, len(all_ids)))

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

        # Clean up temporary seed monad after dream
        if _seed_monad_id and _seed_monad_id in self.field.monad_objects:
            del self.field.monad_objects[_seed_monad_id]

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
          2. Apply geometric sandwich product (R * M * ~R) using pure NumPy
          3. Compute pairwise RBF similarity: exp(−‖a − b‖)
          4. Write the resulting [0, 1] value as Kuramoto coupling K_ij

        Optimisation (Task K): delta-threshold check — only recompute RBF
        similarity for monads whose CGA vectors changed by more than epsilon
        since the last tick. Unchanged pairs skip the expensive pairwise step.
        Worst-case O(N²) → O(changed × N) in practice.

        The 32D CGA representations are transient — they exist only in local
        scope and are destroyed when this function returns.  The 10k HDC
        hv_signature on each ConceptMonad remains entirely untouched.
        """
        # Delta-threshold for coupling recompute (Task K)
        _CGA_DELTA_EPSILON = 0.01

        # Lazily initialise previous-CGA store
        if not hasattr(self, "_prev_cga"):
            self._prev_cga: Dict[str, np.ndarray] = {}

        transient_cga: Dict[str, np.ndarray] = {}
        changed_ids: List[str] = []  # monads whose CGA changed significantly

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

                # Delta check (Task K): has this monad's CGA changed?
                prev = self._prev_cga.get(c_id)
                if prev is None or float(np.linalg.norm(transformed_cga_32d - prev)) > _CGA_DELTA_EPSILON:
                    changed_ids.append(c_id)
                    self._prev_cga[c_id] = transformed_cga_32d.copy()

        # 2. Compute pairwise geometric couplings via RBF kernel.
        #    Only recompute pairs that involve at least one changed monad (Task K).
        concept_ids = list(transient_cga.keys())
        changed_set = set(changed_ids)

        for i, id_a in enumerate(concept_ids):
            monad_a = self.field.monads[id_a]

            # Ensure couplings dict exists
            if not hasattr(monad_a, "couplings") or monad_a.couplings is None:
                monad_a.couplings = {}

            for j, id_b in enumerate(concept_ids):
                if i >= j:
                    continue

                # Skip pairs where neither monad changed (Task K optimisation)
                if id_a not in changed_set and id_b not in changed_set:
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

        # 3. Tell the Kuramoto field to rebuild its K_ij matrix using RBF on CGA vectors
        if hasattr(self.field, "recalculate_coupling_matrix") and transient_cga:
            self.field.recalculate_coupling_matrix(transient_cga)

        # Return transformed CGA for daemon injection
        return transient_cga

        # End of function — transient_cga destroyed by GC.
        # 10k HDC hv_signature on each ConceptMonad remains untouched.

    # ─────────────────────────────────────────────────────────────────────────
    # Mirror Factory Bilateral Symmetry (Task J)
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_mirror_symmetry(self, transformed_cga: Dict[str, np.ndarray]) -> None:
        """
        Compute bilateral overlap between each concept monad and the self monad.

        Within→Without: monad CGA projected against self CGA.
        Without→Within: self CGA projected against monad CGA.

        The symmetry score is the harmonic mean of both projections (cosine
        similarity in each direction), normalised to [0, 1].

        Concepts with high bilateral symmetry receive boosted Kuramoto coupling
        to other high-symmetry concepts, forming a resonant cluster.
        """
        if not transformed_cga:
            return

        # Get self CGA
        self_cga_raw = transformed_cga.get(self.agent_id)
        if self_cga_raw is None:
            # Try fetching from monad hv_signature
            self_monad = self.field.monads.get(self.agent_id)
            if self_monad is not None and hasattr(self_monad, "hv_signature") and self_monad.hv_signature is not None:
                try:
                    self_cga_raw = self.hdc_bridge.hdc_to_cga(self_monad.hv_signature).flatten()
                except Exception:
                    pass
        if self_cga_raw is None:
            return

        self_cga = np.asarray(self_cga_raw, dtype=np.float64).flatten()
        self_norm = float(np.linalg.norm(self_cga)) + 1e-8

        # Compute bilateral symmetry for each monad
        symmetry_scores: Dict[str, float] = {}
        for mid, cga_vec in transformed_cga.items():
            if mid == self.agent_id:
                continue
            try:
                concept_cga = np.asarray(cga_vec, dtype=np.float64).flatten()
                concept_norm = float(np.linalg.norm(concept_cga)) + 1e-8

                # Within→Without: how much of self is in this concept?
                min_dim = min(concept_cga.size, self_cga.size)
                w_to_wo = float(
                    np.dot(concept_cga[:min_dim], self_cga[:min_dim])
                    / (concept_norm * self_norm)
                )
                # Normalise [-1,1] → [0,1]
                w_to_wo = (w_to_wo + 1.0) / 2.0

                # Without→Within: how much of this concept is in self?
                wo_to_w = w_to_wo  # cosine similarity is symmetric

                # Bilateral symmetry = harmonic mean of both directions
                if (w_to_wo + wo_to_w) > 1e-9:
                    symmetry = 2.0 * w_to_wo * wo_to_w / (w_to_wo + wo_to_w)
                else:
                    symmetry = 0.0

                symmetry_scores[mid] = symmetry

                # Store on monad
                monad = self.field.monads.get(mid)
                if monad is not None:
                    monad.mirror_symmetry = symmetry

            except Exception as _e:
                logger.debug("Mirror symmetry failed for '%s': %s", mid, _e)

        # Boost Kuramoto coupling between high-symmetry pairs
        # (symmetry > 0.7 → coupling amplified by factor 1.2)
        HIGH_SYMMETRY_THRESHOLD = 0.7
        BOOST = 1.2
        high_sym_ids = [mid for mid, s in symmetry_scores.items() if s > HIGH_SYMMETRY_THRESHOLD]
        for i, id_a in enumerate(high_sym_ids):
            monad_a = self.field.monads.get(id_a)
            if monad_a is None:
                continue
            if not hasattr(monad_a, "couplings") or monad_a.couplings is None:
                monad_a.couplings = {}
            for id_b in high_sym_ids[i + 1:]:
                monad_b = self.field.monads.get(id_b)
                if monad_b is None:
                    continue
                if not hasattr(monad_b, "couplings") or monad_b.couplings is None:
                    monad_b.couplings = {}
                # Amplify existing coupling, capped at 1.0
                existing = monad_a.couplings.get(id_b, 0.0)
                boosted = min(1.0, existing * BOOST)
                monad_a.couplings[id_b] = boosted
                monad_b.couplings[id_a] = boosted

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
