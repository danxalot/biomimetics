import numpy as np
from sklearn.cluster import DBSCAN
import time
import logging

logger = logging.getLogger(__name__)

class ParticlePhysicsEngine:
    def __init__(self, redis_client):
        self.r = redis_client

    # --- PROCESS A: GRANULAR COLLISION (The "Thunderdome") ---
    def assimilate_atoms(self, current_atoms, future_atoms):
        """
        Resolves conflicts between granular idea atoms.
        """
        # 1. Pool Universe
        universe = []
        for a in current_atoms:
            a['origin'] = 'CURRENT'
            universe.append(a)
        for a in future_atoms:
            a['origin'] = 'FUTURE'
            universe.append(a)

        if not universe:
            return {"accepted": [], "rejected": []}

        # 2. Vectorize (Assumes vectors are pre-populated by embedding model)
        # Filter out atoms without vectors
        valid_universe = [a for a in universe if a.get('vector') is not None]
        if not valid_universe:
            logger.warning("No atoms with valid vectors found.")
            # If no vectors, accept everything (fallback) or reject all? 
            # Fallback: Accept Future
            return {"accepted": future_atoms, "rejected": []}

        vectors = np.array([a['vector'] for a in valid_universe])
        
        # 3. Cluster (Identify Collision Zones)
        # eps=0.3 implies high semantic similarity requirement
        try:
            clustering = DBSCAN(eps=0.3, min_samples=1, metric='cosine').fit(vectors)
        except Exception as e:
            logger.error(f"DBSCAN failed: {e}")
            return {"accepted": future_atoms, "rejected": []} # Fail open to future
        
        accepted = []
        rejected = []

        # 4. Resolve Collisions per Cluster
        unique_labels = set(clustering.labels_)
        for label in unique_labels:
            indices = [i for i, x in enumerate(clustering.labels_) if x == label]
            candidates = [valid_universe[i] for i in indices]
            
            winner = self._select_winner(candidates)
            accepted.append(winner)
            
            for loser in candidates:
                if loser != winner:
                    # Calculate distance if vectors exist
                    v_winner = np.array(winner['vector'])
                    v_loser = np.array(loser['vector'])
                    dist = np.linalg.norm(v_winner - v_loser)
                    
                    rejected.append({
                        "id": loser['id'],
                        "rejected_for": winner['id'],
                        "reason": f"Lower Mass ({loser['mass']} vs {winner['mass']})",
                        "cost_metric": float(dist) # Geometric Distance
                    })

        return {"accepted": accepted, "rejected": rejected}

    def _select_winner(self, candidates):
        """
        Winner Logic:
        1. Future wins if Mass > 1.5x Current (Significant Upgrade).
        2. Otherwise, heaviest Mass wins.
        """
        current = next((x for x in candidates if x['origin'] == 'CURRENT'), None)
        futures = [x for x in candidates if x['origin'] == 'FUTURE']
        
        if not futures: return current
        if not current: return max(futures, key=lambda x: x['mass'])
        
        best_future = max(futures, key=lambda x: x['mass'])
        
        # Evolution Threshold
        if best_future['mass'] > (current['mass'] * 1.5):
            return best_future 
        else:
            return current 

    # --- PROCESS B: MACRO ANALYSIS (Lagrange Points) ---
    def calculate_lagrange_point(self, system_a, system_b):
        """
        Finds synthesis zone between two full documents.
        """
        vec_a = np.array(system_a['trajectory'])
        vec_b = np.array(system_b['trajectory'])
        mass_a = system_a['gravity_well']['mass']
        mass_b = system_b['gravity_well']['mass']
        
        # L1 Point Approximation
        l1_vector = vec_a + (vec_b - vec_a) * (mass_b / (mass_a + mass_b))
        
        return l1_vector.tolist()

    # --- PROCESS C: TIME (Orbital Decay) ---
    def apply_orbital_decay(self, atom, last_access_time):
        """
        Reduces mass of old ideas.
        """
        # Lambda decay constant
        decay_rate = 0.05 
        weeks_old = (time.time() - last_access_time) / (60 * 60 * 24 * 7)
        
        atom['mass'] = atom['mass'] * np.exp(-decay_rate * weeks_old)
        return atom
