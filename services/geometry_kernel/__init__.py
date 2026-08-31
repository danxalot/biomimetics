"""
ARCA Geometry Kernel

A temporal 3D physics engine for epistemic space.

Core principle: Knowledge has geometry, time is first-class, 
errors deform space, and optimization is movement (not loss minimization).

Modules:
  - core: Deterministic kernel (the physics engine)
  - glm_feasibility: Cheap semantic pre-checks using GLM
  - neo4j_schema: System identity and memory structure
  - api: Flask HTTP API (the public interface)
  - otel_mapping: Telemetry → cognitive forces
  - visualization: Human-readable geometry views
  - axes_and_priors: Initial coordinate system and constraints

Usage:
  1. Initialize kernel with axes_and_priors
  2. Load initial state (concepts, attractors)
  3. Accept forces from OTEL signals
  4. Run simulations before applying changes
  5. Use visualization for human inspection
  6. GLM provides cheap semantic pre-checks
  7. Robotics ER-1.5 provides expensive final audits
"""

from .core import (
    GeometryKernel,
    KernelState,
    ConceptNode,
    Attractor,
    Force,
    ForceSource,
    Mode,
    Vector3D,
    EvaluationOutcome,
    SimulationResult,
)

from .glm_feasibility import (
    GLMFeasibilityResponse,
    RiskLevel,
    FailureMode,
    PromotionThreshold,
    DreamCyclePipeline,
)

from .neo4j_schema import (
    NodeLabel,
    RelationshipType,
    BootstrapCypher,
    GraphQueries,
)

from .otel_mapping import (
    OTELSignal,
    SignalType,
    SignalInterpretation,
    SignalForceMapping,
    SignalForceMapper,
    HealthDependentThrottling,
)

from .visualization import (
    VisualizationView,
    VisualNode,
    VisualAttractor,
    VisualEnergy,
    VisualizationBuilder,
    VisualizationDashboard,
)

from .axes_and_priors import (
    SemanticAxis,
    SEMANTIC_AXES,
    BOUNDARY_CONDITIONS,
    CONSERVATION_LAWS,
    INITIAL_CONCEPTS,
    INITIAL_ATTRACTORS,
)

__version__ = "0.1.0"
__all__ = [
    # Core
    "GeometryKernel",
    "KernelState",
    "ConceptNode",
    "Attractor",
    "Force",
    "ForceSource",
    "Mode",
    "Vector3D",
    "EvaluationOutcome",
    "SimulationResult",
    # GLM Feasibility
    "GLMFeasibilityResponse",
    "RiskLevel",
    "FailureMode",
    "PromotionThreshold",
    "DreamCyclePipeline",
    # Neo4j
    "NodeLabel",
    "RelationshipType",
    "BootstrapCypher",
    "GraphQueries",
    # OTEL Mapping
    "OTELSignal",
    "SignalType",
    "SignalInterpretation",
    "SignalForceMapping",
    "SignalForceMapper",
    "HealthDependentThrottling",
    # Visualization
    "VisualizationView",
    "VisualNode",
    "VisualAttractor",
    "VisualEnergy",
    "VisualizationBuilder",
    "VisualizationDashboard",
    # Axes & Priors
    "SemanticAxis",
    "SEMANTIC_AXES",
    "BOUNDARY_CONDITIONS",
    "CONSERVATION_LAWS",
    "INITIAL_CONCEPTS",
    "INITIAL_ATTRACTORS",
]


def create_default_kernel() -> GeometryKernel:
    """
    Factory function to create a kernel with default configuration.

    Returns a GeometryKernel ready for use.
    """
    kernel = GeometryKernel(
        v_max=0.5,
        curvature_cap=0.2,
        inertia_friction=0.1,
        time_step=1.0,
        initial_axes_weights={axis.id: 1.0 for axis in SEMANTIC_AXES.values()},
    )
    return kernel


if __name__ == "__main__":
    print(f"ARCA Geometry Kernel v{__version__}")
    print("\nModules:")
    print("  - core: Physics engine for epistemic space")
    print("  - glm_feasibility: Cheap semantic pre-checks")
    print("  - neo4j_schema: System identity and memory")
    print("  - api: Flask HTTP service")
    print("  - otel_mapping: Telemetry → forces")
    print("  - visualization: Human-readable views")
    print("  - axes_and_priors: Coordinate system")
    print("\nReady to use.")
