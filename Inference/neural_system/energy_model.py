"""
ARCA Unified Energy Model
=========================

Combines multiple energy functions to evaluate system stability and design quality.
Total Energy = α₁E_jepa + α₂E_hopfield + α₃E_geometric

Roles:
1. Stability Check: Is the current runtime state stable?
2. Design Validation: Is the proposed architectural change compliant with the "Vibe"?
"""

import numpy as np
import logging
from typing import List, Dict, Optional, Union

# Import Components
from services.neural_system.geometric_analyzer import HDCGeometricAnalyzer
from services.neural_system.hopfield_memory import HDCHopfieldMemory

logger = logging.getLogger("ARCAEnergy")

class ARCAEnergyModel:
    """
    Unified energy model for the entire ARCA system.
    """
    
    def __init__(self,
                 hopfield_memory: HDCHopfieldMemory,
                 geometric_analyzer: HDCGeometricAnalyzer):
        
        self.hopfield = hopfield_memory
        self.geometric = geometric_analyzer
        
        # Energy component weights (tunable)
        self.weights = {
            'jepa': 0.3,      # Predictability (Future integration)
            'hopfield': 0.4,  # Attractor proximity
            'geometric': 0.3, # Smoothness
        }
    
    def compute_design_energy(self, design_hv: np.ndarray,
                                reference_designs: np.ndarray) -> dict:
        """
        Compute energy for a proposed design (Validation Mode).
        
        Low energy = design is likely stable and efficient.
        High energy = design has potential issues.
        """
        # Ensure inputs are numpy arrays
            
        # 1. Attractor energy: does this design fit known good patterns?
        # We need patterns stored in Hopfield for this to work
        if self.hopfield.stored_patterns.shape[0] > 0:
            hopfield_energy = float(self.hopfield.compute_energy(design_hv))
        else:
            hopfield_energy = 0.5 # Neutral if no memory
        
        # 2. Geometric anomaly check
        # This requires reference designs (points in space)
        if len(reference_designs) > 0:
            anomalies = self.geometric.detect_geometric_anomalies(
                design_hv, reference_designs
            )
            geometric_energy = anomalies.get('overall_anomaly_score', 0.5)
            
            # 3. Smoothness in local neighborhood
            # Combine design with references to check manifold consistency
            combined_set = np.vstack([design_hv.reshape(1, -1), reference_designs[:20]]) # Limit for speed
            smoothness = self.geometric.compute_manifold_smoothness(combined_set)
            # Smoothness score is 0..1 (1=smooth), Energy is 1 - Smoothness
            smoothness_energy = 1.0 - smoothness.get('smoothness_score', 0.5)
        else:
            geometric_energy = 0.5
            smoothness_energy = 0.5
            anomalies = {}
        
        # Weighted Total
        # Normalize energies to roughly [0, 1] range before weighting
        total_energy = (
            self.weights['hopfield'] * hopfield_energy +
            self.weights['geometric'] * (0.6 * geometric_energy + 0.4 * smoothness_energy)
        )
        
        # Interpret
        recommendation = self._design_recommendation(total_energy)
        
        return {
            'total': float(total_energy),
            'components': {
                'attractor_energy': float(hopfield_energy),
                'geometric_anomaly': float(geometric_energy),
                'manifold_roughness': float(smoothness_energy)
            },
            'recommendation': recommendation,
            'details': anomalies
        }
    
    def _interpret_energy(self, total: float) -> str:
        if total < 0.3: return "Stable"
        if total < 0.6: return "Meta-Stable"
        return "Unstable"
    
    def _design_recommendation(self, energy: float) -> str:
        """Provide recommendation based on design energy."""
        if energy < 0.3:
            return "APPROVED: Design appears stable and efficient."
        elif energy < 0.5:
            return "CAUTION: Design shows minor concerns. Review anomalies."
        elif energy < 0.7:
            return "WARNING: Design has significant energy (Instability detected)."
        else:
            return "REJECTED: Design creates high-energy conflict with existing axioms."
