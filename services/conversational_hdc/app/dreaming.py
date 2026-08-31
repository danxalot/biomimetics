
import logging
import asyncio
import time
import numpy as np
from typing import List, Dict, Any
from .conversational_state import GeometricMemoryShaper, ConversationalHDCState

logger = logging.getLogger("DreamingEngine")

class GeometricDreamingEngine:
    """
    Holographic Dreaming Engine for Recursive Manifold Consolidation.
    
    Functions:
    1. Iterates over recent 'Episodes' (Conversations/States).
    2. Consolidates them into the 'GeometricMemoryShaper' manifold.
    3. Prunes/Forgets weak memories to maintain stability.
    
    This is the 'Sleep' cycle for the AI.
    """
    
    def __init__(self, memory_shaper: GeometricMemoryShaper):
        self.shaper = memory_shaper
        self.pending_episodes: List[Dict[str, Any]] = []
        self.is_dreaming = False

    def add_episode(self, episode_hv: np.ndarray, metadata: dict, importance: float = 1.0):
        """
        Queue an episode for consolidation.
        """
        self.pending_episodes.append({
            'hv': episode_hv,
            'metadata': metadata,
            'importance': importance,
            'timestamp': time.time()
        })
        logger.info(f"Episode queued for dreaming. Pending: {len(self.pending_episodes)}")

    async def sleep_cycle(self, decay_rate: float = 0.99) -> dict:
        """
        Trigger the dreaming process (Consolidation + Forgetting).
        """
        if self.is_dreaming:
            return {"status": "already_dreaming"}
            
        self.is_dreaming = True
        logger.info("Entering Sleep Cycle (Holographic Dreaming)...")
        
        try:
            consolidated_count = 0
            start_energy = self._calculate_manifold_energy()
            
            # 1. Consolidation Phase
            # Process pending episodes and bake them into the manifold
            while self.pending_episodes:
                episode = self.pending_episodes.pop(0)
                
                # Apply deformation
                # We use the 'store_memory' method which implements the recursive update
                # M_new = M_old + (importance * v @ v.T)
                self.shaper.store_memory(
                    episode['hv'], 
                    importance=episode['importance']
                )
                consolidated_count += 1
                
                # Yield to event loop to avoid blocking implementation
                await asyncio.sleep(0.01)
                
            # 2. Forgetting/Pruning Phase
            # Decay the manifold to prevent saturation
            self.shaper.apply_forgetting(decay_rate)
            
            end_energy = self._calculate_manifold_energy()
            
            logger.info(f"Waking up. Consolidated: {consolidated_count}. Energy delta: {end_energy - start_energy:.4f}")
            
            return {
                "status": "woke_up",
                "consolidated_episodes": consolidated_count,
                "manifold_energy_delta": end_energy - start_energy,
                "total_deformations": len(self.shaper.deformations)
            }
            
        except Exception as e:
            logger.error(f"Nightmare (Error during dreaming): {e}")
            return {"status": "nightmare", "error": str(e)}
        finally:
            self.is_dreaming = False

    def _calculate_manifold_energy(self) -> float:
        """
        Calculate total energy (sum of importance) in the manifold.
        """
        return sum(d['importance'] for d in self.shaper.deformations)
