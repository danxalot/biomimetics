import logging
import json
import time
import math
import os
import redis
import numpy as np
from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

class PoincareKernel:
    """
    Implements hyperbolic geometry for structural attention.
    Uses the Poincare Disk model where distance -> infinity as points approach the edge (norm -> 1).
    """
    def __init__(self, dimension=2, curvature=1.0):
        self.dim = dimension
        self.c = curvature  # Curvature constant (-c)
        self.structures = {} # Stores {name: vector_position (np.array)}
        
    def _mobius_add(self, u, v):
        """
        Hyperbolic vector addition (Möbius addition).
        This ensures points stay within the disk (radius < 1).
        """
        # Ensure inputs are numpy arrays
        u = np.array(u)
        v = np.array(v)
        
        u2 = np.sum(u * u)
        v2 = np.sum(v * v)
        uv = np.sum(u * v)
        
        den = 1 + 2*self.c*uv + self.c**2 * u2 * v2
        if den == 0: den = 1e-9 # Prevent division by zero
        
        num = (1 + 2*self.c*uv + self.c*v2) * u + (1 - self.c*u2) * v
        
        return num / den

    def distance(self, u, v):
        """
        Calculates hyperbolic distance.
        As points approach the edge (norm -> 1), distance -> infinity.
        """
        u = np.array(u)
        v = np.array(v)
        
        sq_norm_diff = np.sum((u - v) ** 2)
        u2 = np.sum(u ** 2)
        v2 = np.sum(v ** 2)
        
        # Clip to prevent numerical instability near boundary
        u2 = min(u2, 0.9999)
        v2 = min(v2, 0.9999)
        
        arg = 1 + 2 * sq_norm_diff / ((1 - u2) * (1 - v2))
        return np.arccosh(max(arg, 1.0)) # Ensure arg >= 1

    def register_structure(self, name, vector=None):
        """
        Initialize a new context structure (e.g., 'Database_Schema').
        Default: Places it at the exact center (Active Focus).
        """
        if vector is None:
            vector = np.zeros(self.dim)
        else:
            vector = np.array(vector)
            
        self.structures[name] = vector

    def apply_force(self, name, force_vector):
        """
        Apply a 'physics' push to a structure. 
        Used to move concepts into focus (center) or out (edge).
        """
        if name not in self.structures:
            return None 
            
        current_pos = self.structures[name]
        # We add the force vector using Möbius addition to preserve geometry
        new_pos = self._mobius_add(current_pos, force_vector)
        self.structures[name] = new_pos
        return new_pos

    def retract(self, name, intensity=0.1):
        """
        The Core Mechanic: Pushes a structure toward the boundary.
        """
        if name not in self.structures:
            return
            
        current_pos = self.structures[name]
        norm = np.linalg.norm(current_pos)
        
        if norm == 0:
            # If at exact center, push in random direction
            direction = np.random.rand(self.dim)
            direction /= np.linalg.norm(direction)
        else:
            # Push further in the same direction it is already overlapping
            direction = current_pos / norm
            
        force = direction * intensity
        self.apply_force(name, force)

    def get_attention(self, name, query_point=None):
        """
        Returns Attention Score (0.0 to 1.0).
        Based on hyperbolic distance from the center (or a query point).
        """
        if name not in self.structures:
            return 0.0
            
        if query_point is None:
            query_point = np.zeros(self.dim) # Default: Attention from Ego (Center)
            
        pos = self.structures[name]
        dist = self.distance(pos, query_point)
        
        # Softmax-style decay based on distance: 1 / cosh(d)
        # As dist -> infinity (edge), score -> 0
        return 1.0 / np.cosh(dist)
    
    def get_state_dict(self):
        """Return clear dict for visualization/serialization"""
        return {k: v.tolist() for k, v in self.structures.items()}


class GeometricAttentionEngine:
    """
    Manages the 'Context Bubbles' for the agent using Poincare Hyperbolic Geometry.
    """
    def __init__(self, redis_client=None, neo4j_driver=None):
        self.r = redis_client or redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379"), decode_responses=True)
        self.neo4j = neo4j_driver
        if not self.neo4j:
            uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
            auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "password"))
            try:
                self.neo4j = GraphDatabase.driver(uri, auth=auth)
            except Exception as e:
                logger.warning(f"Neo4j driver init failed in AttentionEngine: {e}")

        self.kernel = PoincareKernel(dimension=2)
        
        # Load state from Redis on boot
        self._load_state()

    def _load_state(self):
        try:
            stored = self.r.get("arca:geometry:structures")
            if stored:
                data = json.loads(stored)
                for name, vec in data.items():
                    self.kernel.register_structure(name, vec)
                logger.info(f"Loaded {len(data)} structures into Poincare Kernel")
        except Exception as e:
            logger.error(f"Failed to load geometry state: {e}")

    def _save_state(self):
        try:
            data = self.kernel.get_state_dict()
            self.r.set("arca:geometry:structures", json.dumps(data))
        except Exception as e:
            logger.error(f"Failed to save geometry state: {e}")

    def update_context_bubbles(self, user_input: str, current_focus_structure_id: Optional[str] = None) -> Dict[str, Any]:
        """
        The Master Cycle:
        1. Identify active structure (heuristic/embedding)
        2. Apply Centripetal Force (pull to center)
        3. Apply Centrifugal Force (push others to edge)
        4. Retract/Crystallize dead structures
        """
        # 1. Identification
        # Heuristic: Check for explicit ID passed, or heuristic match in user_input
        active_structure = current_focus_structure_id
        
        if not active_structure:
            for struct in self.kernel.structures.keys():
                if struct.lower() in user_input.lower():
                    active_structure = struct
                    break
        
        # If new structure found (bootstrap), register it
        # This allows 'assimilate_concepts' to create structures that we then track
        if active_structure and active_structure not in self.kernel.structures:
            self.kernel.register_structure(active_structure)

        # 2. & 3. Physics Update
        updated_attentions = {}
        crystallized = []
        structures_to_remove = []

        if active_structure:
            # Pull Active to Center (Move towards origin)
            # To pull to center, we apply force opposite to current position
            current_pos = self.kernel.structures[active_structure]
            # Stronger pull based on distance? 
            # Simple version: Move 40% closer to center
            pull_force = -0.4 * current_pos 
            self.kernel.apply_force(active_structure, pull_force)
            if np.linalg.norm(self.kernel.structures[active_structure]) < 0.1:
                 logger.info(f"Structure {active_structure} is center-focused.")

        # Decay ALL others (Centrifugal Force)
        for name in list(self.kernel.structures.keys()):
            if name != active_structure:
                self.kernel.retract(name, intensity=0.08) # Gentle drift to edge
            
            # Calculate new attention
            att = self.kernel.get_attention(name)
            updated_attentions[name] = float(att)
            
            # 4. Crystallization Threshold
            # If attention drops below threshold (e.g. 0.05), we crystallize
            if att < 0.05:
                # But don't crystallize immediately if we just created it? 
                # (Assuming reasonable usage)
                structures_to_remove.append(name)

        # Process crystallization queue
        for name in structures_to_remove:
            self._crystallize_structure(name)
            if name in self.kernel.structures:
                del self.kernel.structures[name]
            updated_attentions.pop(name, None)
            crystallized.append(name)

        self._save_state()
        
        return {
            "active_structures": updated_attentions,
            "crystallized": crystallized,
            "focus": active_structure
        }

    def _crystallize_structure(self, structure_id: str):
        """
        Move a structure from Hot (Redis) to Cold (Neo4j).
        """
        logger.info(f"❄️ Crystallizing structure: {structure_id}")
        
        # 1. Persist to Neo4j
        if self.neo4j:
            try:
                # Fetch content payload if it exists in a separate key
                redis_key = f"arca:geometry:structure:{structure_id}"
                data = self.r.get(redis_key)
                payload = json.loads(data) if data else {"id": structure_id, "type": "crystallized_structure"}
                
                with self.neo4j.session() as session:
                    # Generic crystallization node
                    query = """
                    MERGE (s:Structure {id: $sid})
                    SET s.crystallized_at = timestamp()
                    """
                    session.run(query, sid=structure_id)
            except Exception as e:
                logger.error(f"Failed to crystallize {structure_id} to Neo4j: {e}")

        # 2. Key is already being removed from Kernel memory by caller
