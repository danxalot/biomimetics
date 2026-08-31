"""
Axes and Priors
Defines the coordinate system and initial state of the Geometry Kernel.
"""

from typing import List, Tuple
from dataclasses import dataclass
from .core import GeometryKernel, ConceptNode, Attractor, Vector3D

@dataclass
class Axes:
    """Semantic definitions of the 3D space."""
    X: str = "Semantic Coherence (-1: Chaos, +1: Order)"
    Y: str = "Evidential Support (0: Baseless, 1: Proven)"
    Z: str = "Temporal Stability (0: Fleeting, 1: Permanent)"

@dataclass
class Priors:
    """Initial system values."""
    concepts: List[ConceptNode]
    attractors: List[Attractor]

def create_default_kernel() -> GeometryKernel:
    """Factory function to initialize a kernel with ARCA's default priors."""
    kernel = GeometryKernel()
    
    # --- Attractors (Goals/Basins) ---
    # 1. Stable Operation (The goal state)
    kernel.add_attractor(Attractor(
        id="attr_stable_ops",
        name="Stable Operation",
        position=Vector3D(0.8, 0.9, 0.9), # High coherence, high evidence, high stability
        strength=2.0,
        radius=1.5,
        type="basin"
    ))

    # 2. Recovery Mode (Fallback basin)
    kernel.add_attractor(Attractor(
        id="attr_recovery",
        name="Recovery & Repair",
        position=Vector3D(0.2, 0.5, 0.4), # Moderate stats
        strength=1.5,
        radius=1.0,
        type="basin"
    ))

    # 3. Learning/Exploration (High variance area)
    kernel.add_attractor(Attractor(
        id="attr_learning",
        name="Active Learning",
        position=Vector3D(0.0, 0.2, 0.1), # Low stability/evidence (new things)
        strength=1.0,
        radius=0.8,
        type="orbit" 
    ))

    # --- Initial Concepts (System Vitals) ---
    base_concepts = [
        ConceptNode(
            id="sys_coherence",
            name="System Coherence",
            position=Vector3D(0.5, 0.5, 0.5),
            velocity=Vector3D.zero(),
            mass=5.0, # Heavy, hard to move
            energy=0.0,
            stability=1.0,
            description="Overall logical consistency of the system."
        ),
        ConceptNode(
            id="agent_reliability",
            name="Agent Reliability",
            position=Vector3D(0.7, 0.8, 0.6),
            velocity=Vector3D.zero(),
            mass=3.0,
            energy=0.0,
            stability=0.9,
            description="Trust score of agent outputs."
        ),
        ConceptNode(
            id="memory_consistency",
            name="Memory Consistency",
            position=Vector3D(0.6, 0.7, 0.8),
            velocity=Vector3D.zero(),
            mass=4.0,
            energy=0.0,
            stability=0.95,
            description="Alignment between Episodic and Structural memory."
        ),
         ConceptNode(
            id="error_rate",
            name="Error Rate (Inverse)",
            position=Vector3D(0.9, 0.9, 0.5), # Starts high (meaning low error)
            velocity=Vector3D.zero(),
            mass=1.0, # Light, reacts fast to spikes
            energy=0.0,
            stability=0.5,
            description="Inverse of system error rate (High = Healthy)."
        ),
    ]

    for c in base_concepts:
        kernel.add_concept(c)

    return kernel
