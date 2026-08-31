"""
Initial Geometry Kernel Axes & Priors

Defines the initial coordinate system and boundary conditions for the epistemic geometry.

These are the hard-coded foundational axes that give the space meaning on day one.
The system learns within these rails, not outside them.

Semantic Axes (what the dimensions mean):
  - Semantic Coherence (X): how well ideas fit together
  - Evidential Support (Y): how much real-world evidence backs a belief
  - Temporal Stability (Z): how long-lived and consistent a concept is
  - System Impact (implicit, via mass/risk): how much change affects outcomes

Boundary Conditions:
  - Max velocity (V_max): prevents semantic whiplash
  - Max curvature: prevents narrative flip-flopping
  - Energy conservation: contradictions don't vanish, only redistribute
  - Rollback guarantee: every state has a path back

Conservation Laws:
  - Evidence mass doesn't disappear
  - Contradictions increase local energy until resolved
  - Stability grows slowly, decays slowly
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
import json


# ============================================================================
# Semantic Axes
# ============================================================================

class SemanticAxis(Enum):
    """The coordinate system of epistemic space."""
    SEMANTIC_COHERENCE = "semantic_coherence"  # X: how well things fit together
    EVIDENTIAL_SUPPORT = "evidential_support"  # Y: backing from evidence
    TEMPORAL_STABILITY = "temporal_stability"  # Z: persistence and consistency
    # System impact is expressed through mass and risk, not as a 4D axis


@dataclass
class AxisDefinition:
    """
    Formal definition of a semantic axis.

    name: human-readable name
    id: machine identifier
    description: what this dimension measures
    min_value: minimum extent
    max_value: maximum extent
    neutral_value: "normal" center
    polarity: which direction is "good"
    """
    name: str
    id: str
    description: str
    min_value: float
    max_value: float
    neutral_value: float
    polarity: str  # "positive", "negative", or "bipolar"
    example_low: str  # what low looks like
    example_high: str  # what high looks like


# ============================================================================
# Initial Axes Specifications
# ============================================================================

SEMANTIC_AXES: Dict[str, AxisDefinition] = {
    "semantic_coherence": AxisDefinition(
        name="Semantic Coherence",
        id="semantic_coherence",
        description="How well concepts fit together logically and semantically. "
                    "Do the ideas reinforce each other or contradict?",
        min_value=-1.0,
        max_value=1.0,
        neutral_value=0.0,
        polarity="positive",
        example_low="Contradictory reasoning, ideas fight each other",
        example_high="All concepts aligned, mutually reinforcing logic",
    ),
    "evidential_support": AxisDefinition(
        name="Evidential Support",
        id="evidential_support",
        description="How much real-world or logical evidence backs a belief. "
                    "Anchored in observable reality vs. pure speculation.",
        min_value=0.0,
        max_value=1.0,
        neutral_value=0.5,
        polarity="positive",
        example_low="No supporting evidence, pure hallucination",
        example_high="Strong evidence from multiple sources, well-grounded",
    ),
    "temporal_stability": AxisDefinition(
        name="Temporal Stability",
        id="temporal_stability",
        description="How stable and long-lived a concept is. "
                    "Core truths are stable; transient states are fluid.",
        min_value=0.0,
        max_value=1.0,
        neutral_value=0.5,
        polarity="positive",
        example_low="Ephemeral, changes every cycle, no persistence",
        example_high="Core identity, unchanged over long history",
    ),
}


# ============================================================================
# Boundary Conditions & Constraints
# ============================================================================

@dataclass
class BoundaryCondition:
    """
    Hard constraint on how the geometry can evolve.

    These prevent bad configurations even without explicit rules.
    """
    name: str
    description: str
    type: str  # velocity_cap, curvature_cap, energy, mass, etc.
    value: float
    unit: str
    rationale: str


BOUNDARY_CONDITIONS: Dict[str, BoundaryCondition] = {
    "max_velocity": BoundaryCondition(
        name="Max Velocity",
        description="Maximum distance a concept can move per timestep",
        type="velocity_cap",
        value=0.5,
        unit="units/tick",
        rationale="Prevents semantic whiplash; beliefs can't flip overnight",
    ),
    "max_curvature": BoundaryCondition(
        name="Max Curvature",
        description="Maximum change in direction per timestep",
        type="curvature_cap",
        value=0.2,
        unit="radians/tick",
        rationale="Prevents narrative flip-flopping; smooth transitions only",
    ),
    "inertia_friction": BoundaryCondition(
        name="Inertia Friction",
        description="Damping applied to all movement",
        type="friction",
        value=0.1,
        unit="fraction_per_tick",
        rationale="Favors stability; movement requires continuous pressure",
    ),
    "energy_conservation": BoundaryCondition(
        name="Energy Conservation",
        description="Contradictions don't vanish; they move or dissipate slowly",
        type="conservation",
        value=0.05,
        unit="dissipation_per_tick",
        rationale="Forces resolution; energy can't be ignored",
    ),
}


# ============================================================================
# Conservation Laws
# ============================================================================

@dataclass
class ConservationLaw:
    """
    Invariant that must be preserved across all state transitions.

    These ensure the system doesn't silently lose important information.
    """
    name: str
    description: str
    formula: str
    enforced_where: str  # kernel core, simulation, validation, etc.
    example: str


CONSERVATION_LAWS: List[ConservationLaw] = [
    ConservationLaw(
        name="Evidence Mass Conservation",
        description="The total evidential mass supporting beliefs doesn't vanish, "
                    "only redistributes when updated",
        formula="∑(evidence) before = ∑(evidence) after ± δ_dissipation",
        enforced_where="kernel_simulate()",
        example="If concept A loses 0.1 units of evidence, that evidence must "
                "either move to another concept or slowly decay (not disappear)",
    ),
    ConservationLaw(
        name="Contradiction Resolution",
        description="Contradictions increase local energy until resolved, "
                    "forcing eventual consistency",
        formula="energy ↑ when δ(conflicting_forces) > threshold",
        enforced_where="force application",
        example="If we try to hold two contradictory beliefs, the system "
                "becomes unstable (high energy) until one is revised",
    ),
    ConservationLaw(
        name="Stability Inertia",
        description="Stability grows slowly, decays slowly; long-lived truths "
                    "resist novelty",
        formula="dS/dt = +learning_rate - decay_rate (with |dS/dt| capped)",
        enforced_where="node updates",
        example="A concept that's been stable for 1000 cycles won't suddenly become "
                "unstable from a single contradictory signal",
    ),
    ConservationLaw(
        name="Rollback Guarantee",
        description="Every state must have a valid inverse; no state is irreversible",
        formula="∀ state_t: ∃ state_t-1 reachable via reverse_forces",
        enforced_where="validation()",
        example="If we moved concept A from (0,0,0) to (0.5,0.2,0.1), "
                "we must be able to reverse that move later",
    ),
]


# ============================================================================
# Initial Concept Priors (Day 1 Setup)
# ============================================================================

@dataclass
class ConceptPrior:
    """
    Prior beliefs about initial concepts.

    These define the starting geometry before learning begins.
    """
    id: str
    name: str
    initial_position: Tuple[float, float, float]
    initial_mass: float  # epistemic inertia (hard truths = high mass)
    initial_stability: float  # 0.0-1.0
    initial_confidence: float  # 0.0-1.0
    core_identity: bool  # if True, moves very slowly
    polarity: str  # positive (want it high) or negative (want it low)
    description: str


INITIAL_CONCEPTS: Dict[str, ConceptPrior] = {
    "system_coherence": ConceptPrior(
        id="concept:system_coherence",
        name="System Coherence",
        initial_position=(0.0, 0.0, 0.0),
        initial_mass=2.0,  # high mass = hard to move = core
        initial_stability=1.0,
        initial_confidence=0.95,
        core_identity=True,
        polarity="positive",
        description="The system is internally consistent and logically sound",
    ),
    "agent_reliability": ConceptPrior(
        id="concept:agent_reliability",
        name="Agent Reliability",
        initial_position=(1.0, 0.0, 0.0),
        initial_mass=1.5,
        initial_stability=0.9,
        initial_confidence=0.9,
        core_identity=True,
        polarity="positive",
        description="Agents behave predictably and recover from errors",
    ),
    "semantic_coherence": ConceptPrior(
        id="concept:semantic_coherence",
        name="Semantic Coherence",
        initial_position=(0.5, 1.0, 0.0),
        initial_mass=1.5,
        initial_stability=0.85,
        initial_confidence=0.85,
        core_identity=False,
        polarity="positive",
        description="Concepts reinforce each other semantically",
    ),
    "error_rate": ConceptPrior(
        id="concept:error_rate",
        name="Error Rate (Low)",
        initial_position=(-1.0, -1.0, 0.0),
        initial_mass=0.8,
        initial_stability=0.8,
        initial_confidence=0.8,
        core_identity=False,
        polarity="negative",
        description="System errors are rare and recoverable",
    ),
    "latency": ConceptPrior(
        id="concept:latency",
        name="Latency (Low)",
        initial_position=(-0.8, -0.5, 0.2),
        initial_mass=0.6,
        initial_stability=0.7,
        initial_confidence=0.75,
        core_identity=False,
        polarity="negative",
        description="System responds quickly to requests",
    ),
    "memory_consistency": ConceptPrior(
        id="concept:memory_consistency",
        name="Memory Consistency",
        initial_position=(0.0, 0.5, 0.5),
        initial_mass=1.8,
        initial_stability=0.95,
        initial_confidence=0.92,
        core_identity=True,
        polarity="positive",
        description="Memories are persistent and reliable",
    ),
}


# ============================================================================
# Initial Attractors (Basins of Attraction)
# ============================================================================

@dataclass
class AttractorPrior:
    """
    Prior distribution of attractors (truth wells).

    These define the stable states the system should naturally settle into.
    """
    id: str
    name: str
    center: Tuple[float, float, float]
    radius: float
    depth: float  # pull strength
    confidence: float  # how certain we are this is a good attractor
    mode: str  # wake or dream
    description: str


INITIAL_ATTRACTORS: Dict[str, AttractorPrior] = {
    "stable_operation": AttractorPrior(
        id="attractor:stable_operation",
        name="Stable Operation",
        center=(0.3, 0.3, 0.0),
        radius=0.6,
        depth=0.9,
        confidence=0.98,
        mode="wake",
        description="System runs smoothly with all agents healthy and no errors",
    ),
    "recovery_mode": AttractorPrior(
        id="attractor:recovery_mode",
        name="Recovery Mode",
        center=(-0.5, -0.5, 0.2),
        radius=0.4,
        depth=0.6,
        confidence=0.85,
        mode="wake",
        description="System is recovering from errors; agents retrying",
    ),
    "learning_exploration": AttractorPrior(
        id="attractor:learning_exploration",
        name="Learning & Exploration",
        center=(0.0, 0.5, 0.7),
        radius=0.5,
        depth=0.5,
        confidence=0.7,
        mode="dream",
        description="System is exploring alternative configurations (dream mode)",
    ),
}


# ============================================================================
# Mass Assignments (Epistemic Inertia)
# ============================================================================

def get_mass_from_identity(core_identity: bool, initial_mass: float) -> float:
    """
    Compute epistemic mass.

    Core identities are harder to move (higher mass).
    """
    if core_identity:
        return initial_mass * 1.5  # 50% more inertia for core truths
    return initial_mass


# ============================================================================
# Initialization Checklist
# ============================================================================

def initialize_kernel_geometry() -> Dict[str, Any]:
    """
    Generate complete initialization spec for kernel.

    Returns dict suitable for passing to GeometryKernel.__init__()
    """
    return {
        "semantic_axes": {axis_id: asdict(axis) for axis_id, axis in SEMANTIC_AXES.items()},
        "boundary_conditions": {cond_id: asdict(cond) for cond_id, cond in BOUNDARY_CONDITIONS.items()},
        "conservation_laws": [asdict(law) for law in CONSERVATION_LAWS],
        "initial_concepts": {cid: asdict(concept) for cid, concept in INITIAL_CONCEPTS.items()},
        "initial_attractors": {aid: asdict(attr) for aid, attr in INITIAL_ATTRACTORS.items()},
    }


# ============================================================================
# Documentation & Human-Readable Export
# ============================================================================

def export_axes_documentation() -> str:
    """Export axes spec as readable documentation."""
    doc = """
# ARCA Geometry Kernel — Initial Axes & Priors

## Semantic Axes

The epistemic space is 3-dimensional, plus time:

"""
    for axis_id, axis in SEMANTIC_AXES.items():
        doc += f"""
### {axis.name} (X/Y/Z)

**What it measures:** {axis.description}

**Range:** [{axis.min_value}, {axis.max_value}]  
**Center:** {axis.neutral_value}  
**Polarity:** {axis.polarity}

**Low:** {axis.example_low}  
**High:** {axis.example_high}

"""

    doc += "\n## Boundary Conditions\n\nHard constraints on evolution:\n"
    for cond_id, cond in BOUNDARY_CONDITIONS.items():
        doc += f"\n**{cond.name}:** {cond.value} {cond.unit}\n{cond.description}\n"

    doc += "\n## Conservation Laws\n\nInvariants that must hold:\n"
    for law in CONSERVATION_LAWS:
        doc += f"\n**{law.name}**\n{law.description}\n"

    doc += "\n## Initial Concepts\n\nDay 1 beliefs:\n"
    for cid, concept in INITIAL_CONCEPTS.items():
        doc += f"\n- **{concept.name}** ({concept.id})\n"
        doc += f"  - Position: {concept.initial_position}\n"
        doc += f"  - Mass: {concept.initial_mass} (core: {concept.core_identity})\n"
        doc += f"  - Stability: {concept.initial_stability}\n"
        doc += f"  - Polarity: {concept.polarity}\n"

    doc += "\n## Initial Attractors\n\nBasins of attraction (stable states):\n"
    for aid, attr in INITIAL_ATTRACTORS.items():
        doc += f"\n- **{attr.name}** ({attr.id})\n"
        doc += f"  - Center: {attr.center}\n"
        doc += f"  - Radius: {attr.radius}\n"
        doc += f"  - Depth (pull strength): {attr.depth}\n"
        doc += f"  - Mode: {attr.mode}\n"

    return doc


if __name__ == "__main__":
    from dataclasses import asdict

    print("=" * 80)
    print("ARCA Geometry Kernel — Initial Axes & Priors")
    print("=" * 80)

    # Print semantic axes
    print("\nSemantic Axes:")
    for axis_id, axis in SEMANTIC_AXES.items():
        print(f"  {axis.name} ({axis_id})")
        print(f"    Range: [{axis.min_value}, {axis.max_value}]")
        print(f"    Description: {axis.description}")

    # Print boundary conditions
    print("\nBoundary Conditions:")
    for cond_id, cond in BOUNDARY_CONDITIONS.items():
        print(f"  {cond.name}: {cond.value} {cond.unit}")
        print(f"    {cond.rationale}")

    # Print initial concepts
    print("\nInitial Concepts:")
    for cid, concept in INITIAL_CONCEPTS.items():
        print(f"  {concept.name}")
        print(f"    Position: {concept.initial_position}")
        print(f"    Mass: {concept.initial_mass}, Stability: {concept.initial_stability}")

    # Print initialization spec
    print("\nInitialization Spec (JSON):")
    spec = initialize_kernel_geometry()
    print(json.dumps(spec, indent=2, default=str)[:500] + "...")

    # Export full documentation
    print("\n" + "=" * 80)
    print("Full Documentation:")
    print("=" * 80)
    print(export_axes_documentation())

    print("\nGeometry Kernel axes & priors initialized.")
