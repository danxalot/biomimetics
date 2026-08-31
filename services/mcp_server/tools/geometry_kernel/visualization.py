"""
Geometry Visualization
Render logic converting raw physics state into human-readable visual primitives.
"""

from typing import Dict, List, Any
from .core import GeometryKernel, ConceptNode, Attractor, Vector3D

class VisualNode:
    def __init__(self, concept: ConceptNode):
        self.id = concept.id
        self.label = concept.name
        self.x = concept.position.x
        self.y = concept.position.y
        self.z = concept.position.z
        self.color = self._map_stability_to_color(concept.stability)
        self.size = self._map_mass_to_size(concept.mass)
        self.glow = self._map_energy_to_glow(concept.energy)
        
    def _map_stability_to_color(self, stability: float) -> str:
        # Green (Stable) -> Yellow -> Red (Unstable)
        if stability > 0.8: return "#00FF00" # Green
        if stability > 0.5: return "#FFFF00" # Yellow
        return "#FF0000" # Red

    def _map_mass_to_size(self, mass: float) -> float:
        # Base size 1.0, scales with sqrt of mass
        return 1.0 + (mass ** 0.5) * 0.5

    def _map_energy_to_glow(self, energy: float) -> float:
        return min(1.0, energy * 0.5)

    def to_dict(self) -> Dict:
        return self.__dict__

class GeometryVisualizer:
    """Generates view data for frontend."""
    
    @staticmethod
    def render_frame(kernel: GeometryKernel) -> Dict[str, Any]:
        params = kernel.get_state()
        
        nodes = [VisualNode(c).to_dict() for c in params.concepts.values()]
        
        attractors = []
        for a in params.attractors.values():
            attractors.append({
                "id": a.id,
                "label": a.name,
                "x": a.position.x,
                "y": a.position.y,
                "z": a.position.z,
                "radius": a.radius,
                "strength": a.strength,
                "color": "#0000FF" # Blue wells
            })

        axes = {
            "x": {"label": "Semantic Coherence", "min": -2, "max": 2},
            "y": {"label": "Evidential Support", "min": -2, "max": 2}, # Actually 0-1 logic but physics space is loose
            "z": {"label": "Temporal Stability", "min": -2, "max": 2}
        }

        return {
            "timestamp": params.timestamp,
            "nodes": nodes,
            "attractors": attractors,
            "axes": axes,
            "global_energy": params.global_energy,
            "stability": params.system_stability
        }
