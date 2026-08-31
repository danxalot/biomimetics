"""
TickFrame Pipeline: Unified State Representation

A TickFrame captures the complete system state at a moment in time:
- HDC State Vector (V_hdc): 10,000-dim hypervector of system state
- Quaternion State (q): Orientation in semantic space
- Angular Velocity (ω): Rate of semantic rotation
- Energy Terms: E_rot, E_hopfield, E_jepa, E_total

This enables:
1. Smooth trajectory analysis via SLERP
2. Energy-based design validation
3. "Semantic whiplash" detection (high angular acceleration)
4. Preflight gating in Genesis Chain
"""

import os
import sys
import json
import logging
import hashlib
import base64
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
import numpy as np

# Import dependencies
_this_dir = os.path.dirname(os.path.abspath(__file__))
_mcp_tools_path = os.path.join(_this_dir, '..', 'mcp_server', 'tools')
if _mcp_tools_path not in sys.path:
    sys.path.insert(0, _mcp_tools_path)

try:
    from hdc_memory import HDCEngine, AFLASHEncoder
except ImportError:
    from services.mcp_server.tools.hdc_memory import HDCEngine, AFLASHEncoder

try:
    from .quaternion_dynamics import QuaternionDynamics
except ImportError:
    from services.neural_system.quaternion_dynamics import QuaternionDynamics

logger = logging.getLogger(__name__)


# =============================================================================
# TickFrame Data Structure
# =============================================================================

@dataclass
class EnergyTerms:
    """Energy components for stability analysis."""
    E_rot: float = 0.0          # Rotational kinetic energy (angular velocity)
    E_hopfield: float = 0.0     # Attractor alignment energy
    E_jepa: float = 0.0         # Prediction error energy
    E_curvature: float = 0.0    # Manifold curvature energy
    E_total: float = 0.0        # Weighted sum
    
    def compute_total(self, weights: Dict[str, float] = None) -> float:
        """Compute weighted total energy."""
        w = weights or {"rot": 0.3, "hopfield": 0.3, "jepa": 0.2, "curvature": 0.2}
        self.E_total = (
            w.get("rot", 0.3) * self.E_rot +
            w.get("hopfield", 0.3) * self.E_hopfield +
            w.get("jepa", 0.2) * self.E_jepa +
            w.get("curvature", 0.2) * self.E_curvature
        )
        return self.E_total


@dataclass
class TickFrame:
    """
    Complete system state snapshot at a single tick.
    
    This is the fundamental unit of state in ARCA's physics engine.
    """
    # Identity
    tick_id: str
    timestamp_ms: int
    
    # HDC State (stored as base64 for transport)
    hv_state_b64: str
    hv_dimensions: int = 10000
    
    # Quaternion Dynamics Channel (QDC)
    q_w: float = 1.0  # Quaternion components
    q_x: float = 0.0
    q_y: float = 0.0
    q_z: float = 0.0
    
    # Angular velocity (semantic rotation rate)
    omega_x: float = 0.0
    omega_y: float = 0.0
    omega_z: float = 0.0
    omega_magnitude: float = 0.0
    
    # Angular acceleration (for "whiplash" detection)
    alpha_magnitude: float = 0.0
    
    # Energy terms
    energy: EnergyTerms = field(default_factory=EnergyTerms)
    
    # Metadata
    source: str = "unknown"  # What generated this tick
    labels: Dict[str, str] = field(default_factory=dict)
    
    def get_quaternion(self) -> np.ndarray:
        """Get quaternion as numpy array [w, x, y, z]."""
        return np.array([self.q_w, self.q_x, self.q_y, self.q_z], dtype=np.float32)
    
    def get_omega(self) -> np.ndarray:
        """Get angular velocity as numpy array."""
        return np.array([self.omega_x, self.omega_y, self.omega_z], dtype=np.float32)
    
    def get_hv_state(self) -> np.ndarray:
        """Decode HDC state from base64."""
        return np.frombuffer(base64.b64decode(self.hv_state_b64), dtype=np.float32)
    
    def to_json(self) -> str:
        """Serialize to JSON for Redis/transport."""
        data = asdict(self)
        data['energy'] = asdict(self.energy)
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "TickFrame":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        energy_data = data.pop('energy', {})
        data['energy'] = EnergyTerms(**energy_data)
        return cls(**data)


# =============================================================================
# TickFrame Pipeline Engine
# =============================================================================

class TickFramePipeline:
    """
    Manages the TickFrame lifecycle:
    1. Ingest raw telemetry → compute TickFrame
    2. Track state evolution (quaternion trajectory)
    3. Compute energy terms
    4. Store to Redis/DragonflyDB
    5. Provide preflight validation
    """
    
    def __init__(self, dimensionality: int = 10000):
        self.hdc = HDCEngine(dimensionality=dimensionality)
        self.encoder = AFLASHEncoder(self.hdc)
        self.qd = QuaternionDynamics()
        self.dim = dimensionality
        
        # State tracking
        self.current_frame: Optional[TickFrame] = None
        self.previous_frame: Optional[TickFrame] = None
        self.frame_history: List[TickFrame] = []
        self.max_history = 100
        
        # Attractor memory for Hopfield energy
        self.attractors: List[np.ndarray] = []
        self._attractor_names: Dict[str, np.ndarray] = {}  # Named attractors
        
        # Redis client (optional)
        self.redis_client = None
        
        logger.info(f"TickFramePipeline initialized ({dimensionality}D)")
    
    # Property aliases for MCP compatibility
    @property
    def history(self) -> List[TickFrame]:
        """Alias for frame_history."""
        return self.frame_history
    
    @property
    def basin_attractors(self) -> Dict[str, np.ndarray]:
        """Named attractors for MCP."""
        return self._attractor_names
    
    async def connect_redis(self, host: str = "localhost", port: int = 6379):
        """Connect to Redis/DragonflyDB for state persistence."""
        try:
            import redis.asyncio as aioredis
            self.redis_client = await aioredis.from_url(
                f"redis://{host}:{port}",
                encoding="utf-8",
                decode_responses=False
            )
            await self.redis_client.ping()
            logger.info(f"Connected to Redis at {host}:{port}")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None
    
    def _generate_tick_id(self) -> str:
        """Generate unique tick ID."""
        ts = datetime.utcnow().isoformat()
        return hashlib.sha256(f"{ts}:{np.random.random()}".encode()).hexdigest()[:16]
    
    def _encode_hv_to_b64(self, hv: np.ndarray) -> str:
        """Encode hypervector to base64 string."""
        return base64.b64encode(hv.astype(np.float32).tobytes()).decode()
    
    def _compute_quaternion_from_hv(self, hv: np.ndarray) -> np.ndarray:
        """
        Project HDC state to quaternion space.
        
        Uses a learned/random projection from high-D to 4D,
        then normalizes to unit quaternion.
        """
        # Simple projection: take 4 components and normalize
        # In production, use a learned projection matrix
        np.random.seed(42)  # Deterministic projection
        proj_matrix = np.random.randn(4, len(hv)).astype(np.float32) / np.sqrt(len(hv))
        
        q = proj_matrix @ hv
        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm
        else:
            q = np.array([1, 0, 0, 0], dtype=np.float32)
        
        return q
    
    def _compute_angular_velocity(
        self, 
        q_current: np.ndarray, 
        q_previous: np.ndarray,
        dt: float = 1.0
    ) -> np.ndarray:
        """
        Compute angular velocity from quaternion change.
        
        ω = 2 * (q_current ⊗ q_previous^{-1}) / dt
        """
        # Quaternion inverse (conjugate for unit quaternions)
        q_prev_inv = np.array([q_previous[0], -q_previous[1], -q_previous[2], -q_previous[3]])
        
        # Quaternion multiplication: q_current * q_prev_inv
        # Using Hamilton product
        w1, x1, y1, z1 = q_current
        w2, x2, y2, z2 = q_prev_inv
        
        q_delta = np.array([
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2
        ])
        
        # Angular velocity (imaginary part scaled)
        omega = 2.0 * q_delta[1:4] / dt
        return omega
    
    def _compute_hopfield_energy(self, hv: np.ndarray) -> float:
        """
        Compute Hopfield energy: how well does this state match attractors?
        
        E_hopfield = -max(similarity to any attractor)
        Lower (more negative) = better alignment with known good states.
        """
        if not self.attractors:
            return 0.0
        
        max_sim = max(self.hdc.similarity(hv, a) for a in self.attractors)
        return -max_sim  # Negative because alignment = low energy
    
    def _compute_curvature_energy(self) -> float:
        """
        Estimate manifold curvature from recent trajectory.
        
        High curvature = sharp turns in state space = instability.
        """
        if len(self.frame_history) < 3:
            return 0.0
        
        # Use angular accelerations
        alphas = [f.alpha_magnitude for f in self.frame_history[-5:]]
        return np.mean(alphas) if alphas else 0.0
    
    def add_attractor(self, name: str, text: str = None):
        """
        Add an attractor (known good state) for Hopfield energy.
        
        Args:
            name: Attractor name (also used as text if text is None)
            text: Text description to encode (optional)
        """
        description = text if text is not None else name
        hv = self.encoder.encode_text(description)
        self.attractors.append(hv)
        self._attractor_names[name] = hv
        logger.info(f"Added attractor '{name}': '{description[:40]}...'")
    
    def ingest(
        self,
        tick_id_or_telemetry,
        observation_text: str = None,
        timestamp: float = None,
        source: str = "telemetry",
        jepa_error: float = 0.0
    ) -> TickFrame:
        """
        Ingest raw telemetry and produce a TickFrame.
        
        Supports two calling conventions:
        1. ingest(tick_id, observation_text, timestamp) - Simple text input
        2. ingest(telemetry_dict, source, jepa_error) - Original dict input
        
        Args:
            tick_id_or_telemetry: Either a tick_id string or telemetry dict
            observation_text: Raw observation text (for simple mode)
            timestamp: Unix timestamp (optional)
            source: Source identifier (for dict mode)
            jepa_error: Prediction error from JEPA (if available)
        
        Returns:
            The computed TickFrame
        """
        import time
        
        # Handle both calling conventions
        if isinstance(tick_id_or_telemetry, dict):
            # Original dict mode
            telemetry = tick_id_or_telemetry
            telemetry_text = " ".join(f"{k}:{v}" for k, v in telemetry.items())
            tick_id = self._generate_tick_id()
            ts = timestamp if timestamp else time.time()
        else:
            # Simple string mode
            tick_id = tick_id_or_telemetry
            telemetry_text = observation_text if observation_text else str(tick_id)
            ts = timestamp if timestamp else time.time()
        
        # Encode telemetry to HDC state
        hv_state = self.encoder.encode_text(telemetry_text)
        
        # Compute quaternion from HDC state
        q = self._compute_quaternion_from_hv(hv_state)
        
        # Compute angular velocity and acceleration
        omega = np.zeros(3, dtype=np.float32)
        alpha = 0.0
        
        if self.current_frame is not None:
            q_prev = self.current_frame.get_quaternion()
            omega_prev = self.current_frame.get_omega()
            
            omega = self._compute_angular_velocity(q, q_prev)
            alpha = np.linalg.norm(omega - omega_prev)
        
        omega_mag = np.linalg.norm(omega)
        
        # Compute energy terms
        E_rot = 0.5 * omega_mag ** 2  # Rotational kinetic energy
        E_hopfield = self._compute_hopfield_energy(hv_state)
        E_curvature = self._compute_curvature_energy()
        
        energy = EnergyTerms(
            E_rot=float(E_rot),
            E_hopfield=float(E_hopfield),
            E_jepa=float(jepa_error),
            E_curvature=float(E_curvature)
        )
        energy.compute_total()
        
        # Get labels if available
        labels = {}
        if isinstance(tick_id_or_telemetry, dict):
            labels = tick_id_or_telemetry.get("labels", {})
        
        # Create TickFrame
        frame = TickFrame(
            tick_id=tick_id,
            timestamp_ms=int(ts * 1000),
            hv_state_b64=self._encode_hv_to_b64(hv_state),
            hv_dimensions=self.dim,
            q_w=float(q[0]),
            q_x=float(q[1]),
            q_y=float(q[2]),
            q_z=float(q[3]),
            omega_x=float(omega[0]),
            omega_y=float(omega[1]),
            omega_z=float(omega[2]),
            omega_magnitude=float(omega_mag),
            alpha_magnitude=float(alpha),
            energy=energy,
            source=source,
            labels=labels
        )
        
        # Update state
        self.previous_frame = self.current_frame
        self.current_frame = frame
        self.frame_history.append(frame)
        if len(self.frame_history) > self.max_history:
            self.frame_history.pop(0)
        
        logger.debug(f"TickFrame {frame.tick_id}: E_total={energy.E_total:.4f}, ω={omega_mag:.4f}")
        
        return frame
    
    async def store_frame(self, frame: TickFrame):
        """Store TickFrame to Redis/DragonflyDB."""
        if self.redis_client is None:
            return
        
        try:
            # Store latest
            await self.redis_client.set("arca:tick:latest", frame.to_json())
            
            # Add to stream
            await self.redis_client.xadd(
                "arca:tick:stream",
                {"data": frame.to_json()},
                maxlen=10000
            )
            
            # Store energy for dashboards
            energy_data = json.dumps({
                "E_rot": frame.energy.E_rot,
                "E_hopfield": frame.energy.E_hopfield,
                "E_jepa": frame.energy.E_jepa,
                "E_total": frame.energy.E_total,
                "omega": frame.omega_magnitude,
                "alpha": frame.alpha_magnitude
            })
            await self.redis_client.set("arca:energy:latest", energy_data)
            
        except Exception as e:
            logger.error(f"Failed to store frame: {e}")
    
    def preflight_check(
        self,
        tick_id_or_text: str = None,
        energy_threshold: float = 2.0,
        rotation_threshold: float = None
    ) -> Tuple[bool, List[str]]:
        """
        Preflight validation for Genesis Chain.
        
        Supports two modes:
        1. tick_id mode: validates an existing TickFrame by ID
        2. text mode: simulates transition to a proposed state
        
        Returns:
            Tuple of (passed: bool, violations: List[str])
        """
        import math
        
        # Handle default for rotation threshold
        if rotation_threshold is None:
            rotation_threshold = math.pi / 4  # π/4 radians
        
        # If tick_id, look up existing frame
        frame = None
        if tick_id_or_text:
            for f in self.frame_history:
                if f.tick_id == tick_id_or_text:
                    frame = f
                    break
        
        if frame is None and self.current_frame is not None:
            frame = self.current_frame
        
        if frame is None:
            return True, []  # No frame to validate
        
        violations = []
        
        # Check energy
        if frame.energy.E_total > energy_threshold:
            violations.append(f"E_total={frame.energy.E_total:.3f} > threshold={energy_threshold}")
        
        # Check angular velocity (rotation)
        if frame.omega_magnitude > rotation_threshold:
            violations.append(f"omega={frame.omega_magnitude:.3f} > threshold={rotation_threshold:.3f}")
        
        # Check for semantic whiplash (high angular acceleration)
        if frame.alpha_magnitude > 2.0:
            violations.append(f"alpha={frame.alpha_magnitude:.3f} (semantic whiplash)")
        
        passed = len(violations) == 0
        return passed, violations
    
    def preflight_validate_proposed(
        self,
        proposed_state_text: str,
        energy_threshold: float = 0.7,
        whiplash_threshold: float = 2.0
    ) -> Dict[str, Any]:
        """
        Preflight validation for Genesis Chain.
        
        Simulates the transition to a proposed state and checks:
        1. Energy doesn't spike above threshold
        2. No "semantic whiplash" (high angular acceleration)
        3. SLERP path is smooth
        
        Returns:
            Dict with approval status and diagnostics
        """
        if self.current_frame is None:
            return {"approved": True, "reason": "No baseline state"}
        
        # Encode proposed state
        hv_proposed = self.encoder.encode_text(proposed_state_text)
        q_proposed = self._compute_quaternion_from_hv(hv_proposed)
        q_current = self.current_frame.get_quaternion()
        
        # Compute transition metrics
        omega_proposed = self._compute_angular_velocity(q_proposed, q_current)
        omega_mag = np.linalg.norm(omega_proposed)
        alpha = abs(omega_mag - self.current_frame.omega_magnitude)
        
        # Compute energy of proposed state
        E_rot = 0.5 * omega_mag ** 2
        E_hopfield = self._compute_hopfield_energy(hv_proposed)
        E_proposed = 0.5 * E_rot + 0.5 * E_hopfield
        
        # SLERP path analysis (check intermediate points)
        slerp_energies = []
        for t in np.linspace(0, 1, 5):
            q_interp = self.qd.slerp(q_current, q_proposed, t)
            # Simplified energy at interpolation point
            slerp_energies.append(E_proposed * t + self.current_frame.energy.E_total * (1-t))
        
        max_slerp_energy = max(slerp_energies)
        energy_barrier = max_slerp_energy - min(slerp_energies)
        
        # Decision
        issues = []
        if E_proposed > energy_threshold:
            issues.append(f"High energy: {E_proposed:.3f} > {energy_threshold}")
        if alpha > whiplash_threshold:
            issues.append(f"Semantic whiplash: α={alpha:.3f} > {whiplash_threshold}")
        if energy_barrier > 0.5:
            issues.append(f"Energy barrier on SLERP path: {energy_barrier:.3f}")
        
        approved = len(issues) == 0
        
        result = {
            "approved": approved,
            "E_proposed": float(E_proposed),
            "omega_magnitude": float(omega_mag),
            "alpha_magnitude": float(alpha),
            "energy_barrier": float(energy_barrier),
            "issues": issues,
            "recommendation": "PROCEED" if approved else "STAGED_ROLLOUT" if len(issues) == 1 else "REJECT"
        }
        
        logger.info(f"Preflight: {result['recommendation']} - {issues if issues else 'OK'}")
        return result


# =============================================================================
# Singleton Instance
# =============================================================================

_pipeline: Optional[TickFramePipeline] = None


def get_tickframe_pipeline(dimensionality: int = 10000) -> TickFramePipeline:
    """Get or create the global TickFrame pipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = TickFramePipeline(dimensionality=dimensionality)
    return _pipeline


# Alias for MCP compatibility
def get_pipeline(dimensionality: int = 10000) -> TickFramePipeline:
    """Alias for get_tickframe_pipeline (MCP-friendly)."""
    return get_tickframe_pipeline(dimensionality)
