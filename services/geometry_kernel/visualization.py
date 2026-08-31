"""
Geometry Visualization Schema (v1)

Defines human-readable geometry visualizations.

Not pretty. Informative.

Key principle: If you can't answer "what just moved and what pushed it?",
the visualization failed.

Visual primitives:
  - Concept Nodes: position (state), size (mass), color (confidence), glow (energy)
  - Attractors: wells with semi-transparent depth overlay
  - Trajectories: fading trails, color-coded by mode (dream/wake)
  - Energy Fields: heat-map volumes
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
import json
import math


class ColorScheme(Enum):
    """Color mappings for visualization."""
    CONFIDENCE_HUE = "hsl({hue}, 100%, 50%)"  # hue by confidence
    STABILITY_BRIGHTNESS = "hsl(0, 0%, {brightness}%)"  # gray scale
    ENERGY_GLOW = "rgba(255, 100, 0, {alpha})"  # orange glow


class VisualizationView(Enum):
    """Different visualization perspectives."""
    CONCEPTS = "concepts"  # nodes in space
    ATTRACTORS = "attractors"  # wells and basins
    ENERGY = "energy"  # contradiction/tension
    TRAJECTORIES = "trajectories"  # recent motion
    FULL = "full"  # all above in one view


@dataclass
class VisualNode:
    """
    Visual representation of a concept node.

    Position → belief state
    Size → mass (epistemic inertia)
    Color → confidence (0-1, mapped to hue 0-360°)
    Glow → energy (contradiction, mapped to radius)
    """
    id: str
    position: Tuple[float, float, float]  # (x, y, z)
    size: float  # mass
    confidence: float  # 0.0-1.0
    energy: float  # contradiction level
    label: str
    stability: float  # for tooltip
    velocity: Optional[Tuple[float, float, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON."""
        # Confidence → hue (0-360°)
        # 0 (low confidence) = red (0°)
        # 1 (high confidence) = green (120°)
        hue = int(self.confidence * 120)
        color = f"hsl({hue}, 100%, 50%)"

        # Energy → glow radius
        glow_radius = self.energy * 0.3

        return {
            "id": self.id,
            "position": list(self.position),
            "size": self.size,
            "color": color,
            "glow_radius": glow_radius,
            "label": self.label,
            "confidence": round(self.confidence, 2),
            "energy": round(self.energy, 2),
            "stability": round(self.stability, 2),
            "velocity": list(self.velocity) if self.velocity else None,
        }


@dataclass
class VisualAttractor:
    """
    Visual representation of an attractor (truth well).

    Center → position
    Radius → area of influence
    Depth → pull strength (shown as shading/opacity)
    Confidence → solidity (core truths are opaque)
    Mode → dream or wake (affects appearance)
    """
    id: str
    center: Tuple[float, float, float]
    radius: float
    depth: float  # pull strength
    confidence: float
    mode: str  # "wake" or "dream"
    label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize."""
        # Confidence → opacity (0.3-1.0)
        opacity = 0.3 + self.confidence * 0.7

        # Mode → color (wake=blue, dream=purple)
        color = "rgba(100, 150, 255, {opacity})" if mode == "wake" else "rgba(200, 100, 255, {opacity})"
        color = color.format(opacity=opacity)

        return {
            "id": self.id,
            "center": list(self.center),
            "radius": round(self.radius, 2),
            "depth": round(self.depth, 2),
            "confidence": round(self.confidence, 2),
            "mode": self.mode,
            "color": color,
            "opacity": round(opacity, 2),
            "label": self.label or self.id,
        }


@dataclass
class VisualEnergy:
    """Heat map of system energy (contradiction)."""
    total_energy: float
    hot_spots: List[Dict[str, Any]]  # [{id, energy, position}, ...]
    avg_energy: float
    status: str  # "critical", "elevated", "normal", "low"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize."""
        return {
            "total_energy": round(self.total_energy, 2),
            "avg_energy": round(self.avg_energy, 2),
            "status": self.status,
            "hot_spots": self.hot_spots,
        }


@dataclass
class VisualTrajectory:
    """Recent motion of a concept."""
    concept_id: str
    current_position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    speed: float
    mode: str  # "wake" or "dream" at last update
    recent_history: Optional[List[Tuple[float, float, float]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize."""
        # Mode → trail color (wake=blue, dream=purple)
        trail_color = "rgba(100, 150, 255, 0.5)" if self.mode == "wake" else "rgba(200, 100, 255, 0.5)"

        return {
            "concept_id": self.concept_id,
            "current": list(self.current_position),
            "velocity": list(self.velocity),
            "speed": round(self.speed, 3),
            "mode": self.mode,
            "trail_color": trail_color,
            "history": [list(p) for p in self.recent_history] if self.recent_history else None,
        }


class VisualizationBuilder:
    """Constructs visualization objects from kernel state."""

    @staticmethod
    def build_node_visualization(node: Any, mode: str = "wake") -> VisualNode:
        """Convert kernel ConceptNode to visual representation."""
        return VisualNode(
            id=node.id,
            position=(node.position.x, node.position.y, node.position.z),
            size=node.mass,
            confidence=node.confidence,
            energy=node.energy,
            label=node.id.replace("concept:", ""),
            stability=node.stability,
            velocity=(node.velocity.x, node.velocity.y, node.velocity.z),
        )

    @staticmethod
    def build_attractor_visualization(attractor: Any) -> VisualAttractor:
        """Convert kernel Attractor to visual representation."""
        return VisualAttractor(
            id=attractor.id,
            center=(attractor.center.x, attractor.center.y, attractor.center.z),
            radius=attractor.radius,
            depth=attractor.depth,
            confidence=attractor.confidence,
            mode=attractor.created_by.value,
            label=attractor.id.replace("attractor:", ""),
        )

    @staticmethod
    def build_energy_visualization(nodes: Dict[str, Any]) -> VisualEnergy:
        """Create energy field visualization."""
        if not nodes:
            return VisualEnergy(0.0, [], 0.0, "low")

        total = sum(n.energy for n in nodes.values())
        avg = total / len(nodes)

        # Hot spots: top 5 highest energy nodes
        hot_spots = sorted(
            [
                {
                    "id": node.id,
                    "energy": round(node.energy, 2),
                    "position": [node.position.x, node.position.y, node.position.z],
                }
                for node in nodes.values()
            ],
            key=lambda x: x["energy"],
            reverse=True,
        )[:5]

        # Status classification
        if total > 2.0:
            status = "critical"
        elif total > 1.0:
            status = "elevated"
        elif total > 0.2:
            status = "normal"
        else:
            status = "low"

        return VisualEnergy(
            total_energy=total,
            hot_spots=hot_spots,
            avg_energy=avg,
            status=status,
        )

    @staticmethod
    def build_trajectory_visualization(
        node: Any,
        mode: str = "wake",
        history: Optional[List[Any]] = None,
    ) -> VisualTrajectory:
        """Create trajectory visualization for a moving concept."""
        speed = node.velocity.magnitude()

        recent_history = None
        if history:
            recent_history = [
                (n.position.x, n.position.y, n.position.z) for n in history[-10:]  # last 10
            ]

        return VisualTrajectory(
            concept_id=node.id,
            current_position=(node.position.x, node.position.y, node.position.z),
            velocity=(node.velocity.x, node.velocity.y, node.velocity.z),
            speed=speed,
            mode=mode,
            recent_history=recent_history,
        )


# ============================================================================
# Dashboard Layout & Controls
# ============================================================================

class VisualizationDashboard:
    """
    Defines what controls and visualizations are required for human inspection.
    """

    REQUIRED_CONTROLS = [
        {
            "name": "time_scrubber",
            "type": "slider",
            "description": "Scrub through time history",
            "min": 0,
            "max": "dynamic",
        },
        {
            "name": "pause_play",
            "type": "button_group",
            "description": "Pause/Play/Step through state evolution",
            "options": ["play", "pause", "step_forward", "step_backward"],
        },
        {
            "name": "view_selector",
            "type": "dropdown",
            "description": "Select visualization view",
            "options": ["concepts", "attractors", "energy", "trajectories", "full"],
        },
        {
            "name": "concept_filter",
            "type": "multi_select",
            "description": "Filter which concepts to display",
            "dynamic": True,
        },
        {
            "name": "highlight_changed",
            "type": "toggle",
            "description": "Highlight concepts that moved this timestep",
        },
        {
            "name": "show_forces",
            "type": "toggle",
            "description": "Overlay applied forces as vectors",
        },
        {
            "name": "overlay_otel",
            "type": "toggle",
            "description": "Overlay OTEL events and health metrics",
        },
    ]

    REQUIRED_VIEWS = [
        {
            "name": "3D Concept Space",
            "description": "Nodes in XYZ semantic space, colored by confidence, sized by mass",
            "essential": True,
        },
        {
            "name": "Attractor Wells",
            "description": "Truth attractors as semi-transparent basins, shaded by depth",
            "essential": True,
        },
        {
            "name": "Energy Field",
            "description": "Contradiction/tension as heat map, shows unstable regions",
            "essential": True,
        },
        {
            "name": "Trajectory Trails",
            "description": "Fading motion trails, colored by wake/dream mode",
            "essential": True,
        },
        {
            "name": "Diff View",
            "description": "Show differences between two states (state A vs B)",
            "essential": True,
        },
        {
            "name": "Force Vector Overlay",
            "description": "Show applied forces as arrows, labeled with source and magnitude",
            "essential": False,
        },
        {
            "name": "OTEL Events Overlay",
            "description": "Show OTEL signals/events on timeline, colored by signal type",
            "essential": False,
        },
    ]

    @staticmethod
    def to_dict() -> Dict[str, Any]:
        """Serialize dashboard spec."""
        return {
            "required_controls": VisualizationDashboard.REQUIRED_CONTROLS,
            "required_views": VisualizationDashboard.REQUIRED_VIEWS,
            "critical_question": "Can you answer: 'What just moved and what pushed it?'",
        }


# ============================================================================
# Annotation & Human-Readable Output
# ============================================================================

class VisualizationAnnotations:
    """
    GLM can add captions and highlight interesting regions.

    GLM is allowed to:
    - Annotate regions
    - Point out unusual curvature
    - Describe conflicts

    GLM is NOT allowed to:
    - Decide what's true
    - Recommend acceptance
    - Narrativize failure
    """

    @staticmethod
    def glm_allowed_annotations() -> List[str]:
        """What GLM can safely add to visualizations."""
        return [
            "Region annotation: 'High curvature region — rapid belief shift'",
            "Conflict highlight: 'Attractors overlapping — energy spike detected'",
            "Anomaly flag: 'Concept drifted beyond normal envelope'",
            "Pattern note: 'Similar trajectory to state t-5, different outcome'",
            "Stability comment: 'System oscillating — two attractors competing'",
        ]

    @staticmethod
    def glm_forbidden_annotations() -> List[str]:
        """What GLM must NOT add."""
        return [
            "Truth claim: 'This concept is correct'",
            "Decision: 'This change should be accepted'",
            "Narrative: 'The system learned it was wrong'",
            "Explanation: 'The reason this failed is...'",
            "Authority: 'You should promote this'",
        ]

    @staticmethod
    def create_safe_annotation(
        annotation_type: str,
        content: str,
        region_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a safe annotation that doesn't leak authority."""
        if annotation_type not in ["region", "conflict", "anomaly", "pattern", "stability"]:
            raise ValueError(f"Unknown annotation type: {annotation_type}")

        return {
            "type": annotation_type,
            "content": content,
            "region_id": region_id,
            "authority": "observation",  # not decision
            "source": "glm_commentary",  # not glm_authority
        }


# ============================================================================
# Example Visualization Output
# ============================================================================

if __name__ == "__main__":
    from .core import ConceptNode, Attractor, Mode, Vector3D
    from datetime import datetime

    print("=" * 80)
    print("Geometry Visualization Schema (v1)")
    print("=" * 80)

    # Create example kernel objects
    node = ConceptNode(
        id="concept:system_coherence",
        position=Vector3D(0.5, 0.2, 0.1),
        velocity=Vector3D(0.05, 0.01, 0.0),
        mass=2.0,
        energy=0.3,
        stability=0.85,
        confidence=0.9,
        last_updated=datetime.utcnow(),
    )

    attractor = Attractor(
        id="attractor:stable_operation",
        center=Vector3D(0.5, 0.2, 0.0),
        radius=0.5,
        depth=0.8,
        confidence=0.95,
        created_by=Mode.WAKE,
        created_at=datetime.utcnow(),
    )

    # Build visualizations
    print("\n1. Visual Node:")
    vis_node = VisualizationBuilder.build_node_visualization(node)
    print(json.dumps(vis_node.to_dict(), indent=2))

    print("\n2. Visual Attractor:")
    vis_attr = VisualizationBuilder.build_attractor_visualization(attractor)
    print(json.dumps(vis_attr.to_dict(), indent=2))

    print("\n3. Trajectory:")
    trajectory = VisualizationBuilder.build_trajectory_visualization(node)
    print(json.dumps(trajectory.to_dict(), indent=2))

    print("\n4. Dashboard Spec:")
    spec = VisualizationDashboard.to_dict()
    print(json.dumps(spec, indent=2))

    print("\n5. GLM-Safe Annotations:")
    print("   Allowed:")
    for ann in VisualizationAnnotations.glm_allowed_annotations():
        print(f"     - {ann}")
    print("   Forbidden:")
    for ann in VisualizationAnnotations.glm_forbidden_annotations():
        print(f"     - {ann}")

    print("\nVisualization Schema ready.")
