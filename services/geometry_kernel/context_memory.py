"""
Context Memory - NumPy Version
=======================

Manages the Riemannian Manifold of configuration and context.
Calculates gravitational pull of documents on the user's conversation vector.
"""

import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import logging

# Configure logging
logger = logging.getLogger("arca.geometry_kernel.context_memory")


@dataclass
class CelestialBody:
    """
    Represents a mass in the Riemannian Manifold (Context Memory).
    Can be a Document (Star), Chapter (Planet), or Paragraph (Moon).
    """
    id: str
    type: str  # STAR, PLANET, MOON
    mass: float
    position: np.ndarray  # NumPy array instead of torch.Tensor
    content_ref: str  # Reference to the actual content (file path or snippet)
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not isinstance(self.position, np.ndarray):
            self.position = np.array(self.position, dtype=np.float32)
        if self.children_ids is None:
            self.children_ids = []


class ManifoldContext:
    """
    Manages the Riemannian Manifold of configuration and context.
    Calculates gravitational pull of documents on the user's conversation vector.
    """
    
    def __init__(self, embedding_dim: int = 768):
        self.embedding_dim = embedding_dim
        self.celestial_bodies: Dict[str, CelestialBody] = {}
        self.gravity_constant = 1.0  # G
    
    def add_body(self, body_id: str, type: str, mass: float, 
                 position: np.ndarray, content_ref: str, 
                 parent_id: Optional[str] = None):
        """
        Adds a new body to the manifold.
        """
        if len(position) != self.embedding_dim:
            raise ValueError(
                f"Position vector dim {len(position)} does not match embedding dim {self.embedding_dim}"
            )
        
        # Ensure numpy array
        if not isinstance(position, np.ndarray):
            position = np.array(position, dtype=np.float32)
        
        body = CelestialBody(
            id=body_id,
            type=type,
            mass=mass,
            position=position.astype(np.float32),
            content_ref=content_ref,
            parent_id=parent_id
        )
        self.celestial_bodies[body_id] = body
        
        if parent_id and parent_id in self.celestial_bodies:
            self.celestial_bodies[parent_id].children_ids.append(body_id)
            
        logger.info(f"Added Celestial Body: {body_id} ({type}, Mass={mass})")
    
    def get_relevant_context(self, user_vector: np.ndarray, 
                                  top_k: int = 5, threshold: float = 0.5) -> List[Dict[str, Any]]:
        """
        Calculates which 'Gravity Well' the user is currently in.
        Returns the most relevant context nodes constrained by gravity.
        """
        if len(user_vector) != self.embedding_dim:
            raise ValueError(
                f"User vector dim {len(user_vector)} does not match embedding dim {self.embedding_dim}"
            )
    
        # Ensure numpy array
        if not isinstance(user_vector, np.ndarray):
            user_vector = np.array(user_vector, dtype=np.float32)
        
        relevant_bodies = []
    
        for body_id, body in self.celestial_bodies.items():
            # Calculate Geodesic Distance (Approximated as Euclidean in local tangent space)
            # Distance = |User_Vector - Doc_Vector|
            distance = np.linalg.norm(user_vector - body.position)
            
            # Gravitational Pull = (G * M) / r^2 (using r+epsilon for stability)
            # We use a simplified metric where distance is penalized
            if distance < 1e-6:
                distance = 1e-6  # Avoid division by zero
            
            gravitational_pull = (self.gravity_constant * body.mass) / (distance ** 2)
            
            # We can also use cosine similarity as a directional component
            # Cosine similarity = (a·b) / (|a|*|b|)
            norm_u = np.linalg.norm(user_vector)
            norm_b = np.linalg.norm(body.position)
            if norm_u > 1e-8 and norm_b > 1e-8:
                similarity = np.dot(user_vector, body.position) / (norm_u * norm_b)
            else:
                similarity = 0.0
            
            # Combined Score: heavy objects pull more, but you have to be close/aligned
            # This allows "Stars" to be visible from far away, but "Moons" require proximity.
            score = gravitational_pull * (similarity + 1) / 2  # Normalize sim to 0-1 range
            
            if score > threshold:
                relevant_bodies.append({
                    "id": body.id,
                    "type": body.type,
                    "content_ref": body.content_ref,
                    "score": float(score),
                    "distance": float(distance),
                    "similarity": float(similarity),
                })
    
        # Sort by gravitational pull (score)
        relevant_bodies.sort(key=lambda x: x["score"], reverse=True)
        
        return relevant_bodies[:top_k]
    
    def get_system_state_brief(self) -> str:
        """Returns a summary of the current manifold state."""
        star_count = sum(1 for b in self.celestial_bodies.values() if b.type == "STAR")
        planet_count = sum(1 for b in self.celestial_bodies.values() if b.type == "PLANET")
        return (f"Manifold contains {len(self.celestial_bodies)} bodies "
                f"({star_count} Stars, {planet_count} Planets)")
