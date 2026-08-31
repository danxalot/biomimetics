"""
Geometry Kernel Core — Physics Engine for Epistemic Space

This module implements the deterministic, replayable core of the temporal
3D geometry system. It is NOT an LLM. It is a physics engine for belief.

Key principles:
- Time is explicit and monotonic
- All updates are replayable and reversible
- No text generation, no goal reasoning
- Invariants are enforced by design
- State is atomically versioned

The kernel is the sole authority on how truth can move.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime
import uuid
import json
import math
import numpy as np
from enum import Enum


class Mode(Enum):
    """Kernel operating modes."""
    WAKE = "wake"
    DREAM = "dream"


class ForceSource(Enum):
    """Where a force originates."""
    EVIDENCE = "evidence"
    CONTRADICTION = "contradiction"
    DECAY = "decay"
    DREAM = "dream"
    OTEL = "otel"


class EvaluationOutcome(Enum):
    """Possible outcomes from geometry evaluation."""
    ACCEPTED = "accepted"
    SOFTENED = "softened"
    REJECTED = "rejected"


# ============================================================================
# Core Data Structures
# ============================================================================

@dataclass
class Vector3D:
    """3D vector for positions, velocities, forces."""
    x: float
    y: float
    z: float

    def magnitude(self) -> float:
        """L2 norm."""
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def normalize(self) -> 'Vector3D':
        """Return unit vector."""
        mag = self.magnitude()
        if mag == 0:
            return Vector3D(0, 0, 0)
        return Vector3D(self.x / mag, self.y / mag, self.z / mag)

    def dot(self, other: 'Vector3D') -> float:
        """Dot product."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def scale(self, scalar: float) -> 'Vector3D':
        """Element-wise multiplication."""
        return Vector3D(self.x * scalar, self.y * scalar, self.z * scalar)

    def add(self, other: 'Vector3D') -> 'Vector3D':
        """Vector addition."""
        return Vector3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def sub(self, other: 'Vector3D') -> 'Vector3D':
        """Vector subtraction."""
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def clamp_magnitude(self, max_mag: float) -> 'Vector3D':
        """Clamp to max magnitude."""
        mag = self.magnitude()
        if mag <= max_mag:
            return Vector3D(self.x, self.y, self.z)
        return self.normalize().scale(max_mag)

    def to_list(self) -> List[float]:
        """Convert to [x, y, z]."""
        return [self.x, self.y, self.z]

    @staticmethod
    def from_list(lst: List[float]) -> 'Vector3D':
        """Create from [x, y, z]."""
        return Vector3D(lst[0], lst[1], lst[2])


@dataclass
class ConceptNode:
    """
    Atomic epistemic unit.

    position: location in semantic space (X, Y, Z axes)
    velocity: rate of change (clamped by V_max)
    mass: epistemic inertia (high mass → slow movement)
    energy: contradiction/tension (forces convergence)
    stability: long-term coherence (grows/decays slowly)
    confidence: belief strength (0.0-1.0)
    last_updated: timestamp of last change
    """
    id: str
    position: Vector3D
    velocity: Vector3D
    mass: float
    energy: float
    stability: float
    confidence: float
    last_updated: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "id": self.id,
            "position": self.position.to_list(),
            "velocity": self.velocity.to_list(),
            "mass": self.mass,
            "energy": self.energy,
            "stability": self.stability,
            "confidence": self.confidence,
            "last_updated": self.last_updated.isoformat(),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'ConceptNode':
        """Deserialize from dict."""
        return ConceptNode(
            id=d["id"],
            position=Vector3D.from_list(d["position"]),
            velocity=Vector3D.from_list(d["velocity"]),
            mass=d["mass"],
            energy=d["energy"],
            stability=d["stability"],
            confidence=d["confidence"],
            last_updated=datetime.fromisoformat(d["last_updated"]),
        )


@dataclass
class Attractor:
    """
    Emergent truth cluster.

    center: position in concept space
    radius: area of influence
    depth: pull strength (higher = stronger)
    confidence: creator's certainty
    created_by: mode that created it (wake / dream)
    id: unique identifier
    """
    id: str
    center: Vector3D
    radius: float
    depth: float
    confidence: float
    created_by: Mode
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Serialize."""
        return {
            "id": self.id,
            "center": self.center.to_list(),
            "radius": self.radius,
            "depth": self.depth,
            "confidence": self.confidence,
            "created_by": self.created_by.value,
            "created_at": self.created_at.isoformat(),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'Attractor':
        """Deserialize."""
        return Attractor(
            id=d["id"],
            center=Vector3D.from_list(d["center"]),
            radius=d["radius"],
            depth=d["depth"],
            confidence=d["confidence"],
            created_by=Mode(d["created_by"]),
            created_at=datetime.fromisoformat(d["created_at"]),
        )


@dataclass
class Force:
    """
    Proposal for state change. Forces are never stored; they are applied and logged.

    target_id: which concept is affected
    vector: direction in semantic space
    magnitude: strength of force (clamped by kernel)
    source: where this came from
    rationale: short text explaining why (for audit)
    """
    target_id: str
    vector: Vector3D
    magnitude: float
    source: ForceSource
    rationale: str = ""


@dataclass
class AxisEmphasis:
    """
    Proposal to reweight importance of semantic axes.

    axis_name: which axis (semantic_coherence, evidential_support, etc.)
    delta_weight: change to apply
    """
    axis_name: str
    delta_weight: float


@dataclass
class HSEState:
    """
    Hyper-Spatial Embedding State.
    Proprioceptive state derived from telemetry and logs.
    
    vector: 10000-dim binary vector (compressed as list of ints or bytes)
    velocity: rate of change from previous state (0.0-1.0)
    anomaly_score: similarity to known failure modes
    timestamp: observation time
    """
    vector: Any  # Usually List[int] or np.ndarray
    velocity: float
    anomaly_score: float
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "velocity": self.velocity,
            "anomaly_score": self.anomaly_score,
            "timestamp": self.timestamp.isoformat(),
            # Vector omitted by default to save bandwidth
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'HSEState':
        return HSEState(
            vector=d.get("vector", []),
            velocity=d["velocity"],
            anomaly_score=d["anomaly_score"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
        )


@dataclass
class KernelState:
    """
    Complete snapshot of geometry at a moment in time.

    timestamp: when this state is valid
    nodes: dict of concept nodes by id
    attractors: dict of attractors by id
    health_metrics: system health (stability_index, error_rate, entropy_level)
    axes_weights: current importance of each semantic axis
    hse_state: proprioceptive state from OTel/HSE Encoder
    """
    id: str
    timestamp: datetime
    nodes: Dict[str, ConceptNode]
    attractors: Dict[str, Attractor]
    health_metrics: Dict[str, float]
    axes_weights: Dict[str, float]
    hse_state: Optional[HSEState] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize."""
        data = {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "attractors": {aid: attr.to_dict() for aid, attr in self.attractors.items()},
            "health_metrics": self.health_metrics,
            "axes_weights": self.axes_weights,
        }
        if self.hse_state:
            data["hse_state"] = self.hse_state.to_dict()
        return data

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'KernelState':
        """Deserialize."""
        return KernelState(
            id=d["id"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            nodes={nid: ConceptNode.from_dict(nd) for nid, nd in d["nodes"].items()},
            attractors={aid: Attractor.from_dict(ad) for aid, ad in d["attractors"].items()},
            health_metrics=d["health_metrics"],
            axes_weights=d["axes_weights"],
            hse_state=HSEState.from_dict(d["hse_state"]) if "hse_state" in d else None,
        )


@dataclass
class SimulationResult:
    """
    Outcome of a simulation (no mutations applied).

    simulation_id: unique id for this run
    predicted_state: what state would be if forces applied
    metrics: stability, energy_delta, divergence
    """
    simulation_id: str
    predicted_state: KernelState
    metrics: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize."""
        return {
            "simulation_id": self.simulation_id,
            "predicted_state": self.predicted_state.to_dict(),
            "metrics": self.metrics,
        }


# ============================================================================
# Geometry Kernel
# ============================================================================

class GeometryKernel:
    """
    Physics engine for epistemic space.

    This is the only place where truth can move.
    """

    # Invariant constraints (fixed at init, not exposed to models)
    def __init__(
        self,
        v_max: float = 0.5,  # max velocity per timestep
        curvature_cap: float = 0.2,  # max change in direction per timestep
        inertia_friction: float = 0.1,  # damping on movement
        time_step: float = 1.0,  # clock tick
        initial_axes_weights: Optional[Dict[str, float]] = None,
    ):
        self.v_max = v_max
        self.curvature_cap = curvature_cap
        self.inertia_friction = inertia_friction
        self.time_step = time_step

        # Default semantic axes
        if initial_axes_weights is None:
            initial_axes_weights = {
                "semantic_coherence": 1.0,
                "evidential_support": 1.0,
                "temporal_stability": 1.0,
                "system_impact": 1.0,
                "confidence_vs_entropy": 1.0,
            }
        self.axes_weights = initial_axes_weights

        # State history (for replayability)
        self.state_history: Dict[str, KernelState] = {}
        self.current_state: Optional[KernelState] = None

    # ========================================================================
    # Core Operations
    # ========================================================================

    def initialize_state(self, nodes: List[ConceptNode], attractors: List[Attractor]) -> KernelState:
        """Create initial kernel state."""
        state = KernelState(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            nodes={node.id: node for node in nodes},
            attractors={attr.id: attr for attr in attractors},
            health_metrics={
                "stability_index": 1.0,
                "error_rate": 0.0,
                "entropy_level": 0.0,
            },
            axes_weights=self.axes_weights.copy(),
        )
        self.state_history[state.id] = state
        self.current_state = state
        return state

    def simulate(
        self,
        base_state_id: str,
        forces: List[Force],
        attractor_proposals: List[Attractor],
        axis_emphasis: Optional[Dict[str, float]] = None,
        mode: Mode = Mode.WAKE,
    ) -> SimulationResult:
        """
        Simulate forces without mutating state.

        Returns predicted next state and stability metrics.
        """
        if base_state_id not in self.state_history:
            raise ValueError(f"Unknown state id: {base_state_id}")

        base_state = self.state_history[base_state_id]

        # Copy state for simulation
        sim_nodes = {nid: self._copy_concept_node(node) for nid, node in base_state.nodes.items()}
        sim_attractors = {aid: self._copy_attractor(attr) for aid, attr in base_state.attractors.items()}
        sim_axes_weights = base_state.axes_weights.copy()

        # Apply axis emphasis (if provided)
        if axis_emphasis:
            for axis, delta in axis_emphasis.items():
                if axis in sim_axes_weights:
                    sim_axes_weights[axis] = max(0.0, sim_axes_weights[axis] + delta)

        # Apply forces
        for force in forces:
            if force.target_id not in sim_nodes:
                continue  # Ignore forces on unknown concepts

            node = sim_nodes[force.target_id]

            # Clamp force magnitude
            clamped_force = force.vector.normalize().scale(
                min(force.magnitude, self.v_max)
            )

            # Apply inertia: Δposition ∝ force / mass
            acceleration = clamped_force.scale(1.0 / node.mass) if node.mass > 0 else clamped_force
            new_velocity = node.velocity.add(acceleration.scale(self.time_step))

            # Apply velocity cap
            new_velocity = new_velocity.clamp_magnitude(self.v_max)

            # Check curvature (change in direction)
            direction_change = self._estimate_curvature(node.velocity, new_velocity)
            if direction_change > self.curvature_cap:
                # Soften the turn
                old_dir = node.velocity.normalize()
                new_dir = new_velocity.normalize()
                allowed_turn = old_dir.scale(1.0).add(new_dir.scale(self.curvature_cap))
                new_velocity = allowed_turn.clamp_magnitude(self.v_max)

            # Apply friction (damping)
            new_velocity = new_velocity.scale(1.0 - self.inertia_friction)

            # Update position
            new_position = node.position.add(new_velocity.scale(self.time_step))

            # Update node
            node.position = new_position
            node.velocity = new_velocity
            node.last_updated = datetime.utcnow()

            # Update energy (contradiction decreases if force resolves it, increases otherwise)
            if force.source == ForceSource.CONTRADICTION:
                node.energy = max(0.0, node.energy - 0.1)
            elif force.source == ForceSource.EVIDENCE:
                node.confidence = min(1.0, node.confidence + 0.05)

        # Add new attractors (dream mode can propose them freely)
        for proposal in attractor_proposals:
            sim_attractors[proposal.id] = proposal

        # Check for attractor overlap (energy increase)
        overlap_energy = self._compute_attractor_overlap(sim_attractors)

        # Compute stability metrics
        stability = self._compute_stability(sim_nodes, sim_attractors, base_state.health_metrics)
        energy_delta = overlap_energy - sum(n.energy for n in base_state.nodes.values())
        divergence = self._compute_divergence(base_state.nodes, sim_nodes)

        # Create predicted state
        predicted_state = KernelState(
            id=str(uuid.uuid4()),
            timestamp=base_state.timestamp.replace(
                second=base_state.timestamp.second + int(self.time_step)
            ),
            nodes=sim_nodes,
            attractors=sim_attractors,
            health_metrics=base_state.health_metrics.copy(),
            axes_weights=sim_axes_weights,
        )

        return SimulationResult(
            simulation_id=str(uuid.uuid4()),
            predicted_state=predicted_state,
            metrics={
                "stability": stability,
                "energy_delta": energy_delta,
                "divergence": divergence,
            },
        )

    def validate(
        self,
        simulation_id: str,
        health_metrics: Optional[Dict[str, float]] = None,
    ) -> Tuple[EvaluationOutcome, str]:
        """
        Validate a simulation result before apply.

        Checks:
        1. Invariant violations
        2. Health-dependent gating
        3. Monotonicity constraints

        Does NOT call robotics or policy manager; those are external gates.
        """
        # This is a minimal internal validation.
        # External gates (robotics, guardian) have separate APIs.

        # Check health gating
        if health_metrics is None:
            health_metrics = self.current_state.health_metrics if self.current_state else {}

        if health_metrics.get("stability_index", 1.0) < 0.5:
            return (EvaluationOutcome.SOFTENED, "system_health_insufficient")

        return (EvaluationOutcome.ACCEPTED, "passed_invariant_checks")

    def apply(
        self,
        simulation_id: str,
        approved_by: List[str],
    ) -> KernelState:
        """
        Apply a simulation result to persistent state.

        Only callable by orchestrator after full validation pipeline.
        approved_by: list of validators that approved (guardian, robotics, reviewer)
        """
        # In production, you'd track simulations and apply.
        # For now, this is a placeholder for the structure.
        raise NotImplementedError("apply() requires orchestrator integration")

    def snapshot(self, state_id: Optional[str] = None) -> Dict[str, Any]:
        """Get current state as JSON."""
        if state_id is None:
            state = self.current_state
        else:
            state = self.state_history.get(state_id)

        if state is None:
            return {}
        return state.to_dict()

    # ========================================================================
    # Helpers
    # ========================================================================

    def _copy_concept_node(self, node: ConceptNode) -> ConceptNode:
        """Deep copy a concept node."""
        return ConceptNode(
            id=node.id,
            position=Vector3D(node.position.x, node.position.y, node.position.z),
            velocity=Vector3D(node.velocity.x, node.velocity.y, node.velocity.z),
            mass=node.mass,
            energy=node.energy,
            stability=node.stability,
            confidence=node.confidence,
            last_updated=node.last_updated,
        )

    def _copy_attractor(self, attr: Attractor) -> Attractor:
        """Deep copy an attractor."""
        return Attractor(
            id=attr.id,
            center=Vector3D(attr.center.x, attr.center.y, attr.center.z),
            radius=attr.radius,
            depth=attr.depth,
            confidence=attr.confidence,
            created_by=attr.created_by,
            created_at=attr.created_at,
        )

    def _estimate_curvature(self, old_vel: Vector3D, new_vel: Vector3D) -> float:
        """Estimate change in direction between velocities."""
        old_norm = old_vel.normalize()
        new_norm = new_vel.normalize()
        dot = old_norm.dot(new_norm)
        dot = max(-1.0, min(1.0, dot))  # clamp to [-1, 1]
        return 1.0 - dot  # 0 = same direction, 2 = opposite

    def _compute_attractor_overlap(self, attractors: Dict[str, Attractor]) -> float:
        """Compute energy from overlapping attractors (contradiction)."""
        overlap = 0.0
        attr_list = list(attractors.values())
        for i, a1 in enumerate(attr_list):
            for a2 in attr_list[i+1:]:
                dist = (a1.center.sub(a2.center)).magnitude()
                if dist < (a1.radius + a2.radius):
                    overlap += 0.1  # each overlap adds energy
        return overlap

    def _compute_stability(
        self,
        nodes: Dict[str, ConceptNode],
        attractors: Dict[str, Attractor],
        health_metrics: Dict[str, float],
    ) -> float:
        """Estimate stability of configuration (0=unstable, 1=stable)."""
        if not nodes:
            return 0.0

        # High energy = unstable
        total_energy = sum(n.energy for n in nodes.values())
        energy_penalty = min(1.0, total_energy / len(nodes))

        # High velocity = unstable
        total_velocity = sum(n.velocity.magnitude() for n in nodes.values())
        velocity_penalty = min(1.0, total_velocity / len(nodes) / self.v_max)

        # Average stability of nodes
        avg_stability = sum(n.stability for n in nodes.values()) / len(nodes) if nodes else 0.0

        # System health contributes
        health_stability = health_metrics.get("stability_index", 1.0)

        return max(0.0, (avg_stability + health_stability - energy_penalty - velocity_penalty) / 2.0)

    def _compute_divergence(
        self,
        old_nodes: Dict[str, ConceptNode],
        new_nodes: Dict[str, ConceptNode],
    ) -> float:
        """Measure how much state changed."""
        total_distance = 0.0
        count = 0
        for nid, old_node in old_nodes.items():
            if nid in new_nodes:
                delta = new_nodes[nid].position.sub(old_node.position)
                total_distance += delta.magnitude()
                count += 1
        return total_distance / count if count > 0 else 0.0

    def _health_dependent_learning_throttle(self, health_metrics: Dict[str, float]) -> None:
        """
        Adjust kernel constraints based on system health.

        When system is unhealthy:
        - learning slows
        - dreaming disabled
        - self-modification becomes expensive
        """
        stability_index = health_metrics.get("stability_index", 1.0)

        if stability_index < 0.5:
            # System under stress
            self.v_max *= 0.7  # reduce velocity
            # Dreaming would be disabled at a higher level
            # Mass globally increases (harder to move beliefs)
            pass
        elif stability_index < 0.7:
            # System partially stressed
            self.v_max *= 0.85
            pass
        else:
            # System healthy
            self.v_max = 0.5  # reset to default

    def ingest_hse_state(self, hse_data: Dict[str, Any]) -> None:
        """
        Ingest a new HSE state vector.
        Affects system health and global constraints.
        """
        try:
            hse_state = HSEState(
                vector=hse_data.get("vector"),
                velocity=hse_data.get("velocity", 0.0),
                anomaly_score=hse_data.get("anomaly_score", 0.0),
                timestamp=datetime.now() # Use current time for ingest
            )
            
            if self.current_state:
                self.current_state.hse_state = hse_state
                
                # Feedback loop: High velocity/anomaly -> Reduce stability -> Slow down geometry
                stability_impact = 1.0 - min(1.0, hse_state.velocity * 2.0 + hse_state.anomaly_score)
                self.current_state.health_metrics["stability_index"] = stability_impact
                
                # Apply throttling based on new health
                self._health_dependent_learning_throttle(self.current_state.health_metrics)
                
        except Exception as e:
            # Don't crash kernel on bad HSE data
            print(f"Error ingesting HSE state: {e}")


# ============================================================================
# Example Usage & Testing
# ============================================================================

if __name__ == "__main__":
    # Create kernel
    kernel = GeometryKernel(v_max=0.5, curvature_cap=0.2)

    # Initialize with simple concepts
    nodes = [
        ConceptNode(
            id="concept:agent_reliability",
            position=Vector3D(0.0, 0.0, 0.0),
            velocity=Vector3D(0.0, 0.0, 0.0),
            mass=1.0,
            energy=0.0,
            stability=1.0,
            confidence=0.9,
            last_updated=datetime.utcnow(),
        ),
        ConceptNode(
            id="concept:system_coherence",
            position=Vector3D(1.0, 1.0, 1.0),
            velocity=Vector3D(0.0, 0.0, 0.0),
            mass=2.0,
            energy=0.0,
            stability=1.0,
            confidence=0.85,
            last_updated=datetime.utcnow(),
        ),
    ]

    attractors = [
        Attractor(
            id="attractor:stable_operation",
            center=Vector3D(0.5, 0.5, 0.5),
            radius=0.3,
            depth=0.8,
            confidence=0.95,
            created_by=Mode.WAKE,
            created_at=datetime.utcnow(),
        ),
    ]

    state = kernel.initialize_state(nodes, attractors)
    print("Initial state:")
    print(json.dumps(state.to_dict(), indent=2, default=str))

    # Simulate a force
    forces = [
        Force(
            target_id="concept:agent_reliability",
            vector=Vector3D(0.1, 0.05, 0.0),
            magnitude=0.2,
            source=ForceSource.EVIDENCE,
            rationale="Error rate decreased, evidence of improvement",
        ),
    ]

    result = kernel.simulate(state.id, forces, [], mode=Mode.WAKE)
    print("\nSimulation result:")
    print(json.dumps(result.to_dict(), indent=2, default=str))

    print("\nGeometry Kernel initialized and ready for integration.")
