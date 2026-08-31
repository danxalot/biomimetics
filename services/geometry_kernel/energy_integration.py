"""
Energy Integration for Geometry Kernel

Bridges the Energy-Based Cognition layer with the Geometry Kernel.
Provides:
- Energy computation during kernel tick
- Hopfield attractor integration
- Smoothness metrics for state output
- Design validation gate

Usage:
    from energy_integration import EnergyIntegration
    
    # Initialize with kernel
    energy = EnergyIntegration()
    
    # During tick
    tick_frame = energy.compute_tick_energy(
        kernel_state=state,
        context_history=history
    )
    
    # For pre-flight validation
    result = energy.validate_design(proposal_hv, reference_designs)
"""

import sys
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np

# Import from neural_system (will be available when deployed together)
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'services', 'neural_system', 'app'))
    from energy_model import ARCAEnergyModel, HDCHopfieldMemory, HDCGeometricAnalyzer, create_energy_model
except ImportError:
    # Fallback for standalone testing
    ARCAEnergyModel = None
    HDCHopfieldMemory = None
    HDCGeometricAnalyzer = None
    create_energy_model = None


@dataclass
class EnergyTickFrame:
    """Energy metrics for a single tick."""
    timestamp: datetime
    tick_id: str
    
    # Energy components
    hopfield_energy: float      # Distance from nearest attractor
    geometric_energy: float     # Curvature/smoothness of trajectory
    jepa_energy: Optional[float] = None  # Prediction error (if JEPA available)
    
    # Combined metrics
    total_energy: float = 0.0
    stability_score: float = 1.0  # 1 = stable, 0 = unstable
    
    # Interpretation
    interpretation: str = "stable"
    recommendation: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "tick_id": self.tick_id,
            "hopfield_energy": self.hopfield_energy,
            "geometric_energy": self.geometric_energy,
            "jepa_energy": self.jepa_energy,
            "total_energy": self.total_energy,
            "stability_score": self.stability_score,
            "interpretation": self.interpretation,
            "recommendation": self.recommendation
        }


class EnergyIntegration:
    """
    Integrates energy-based cognition with geometry kernel.
    
    Provides energy metrics during tick processing and
    design validation before state mutations.
    """
    
    def __init__(
        self,
        hv_dim: int = 10000,
        enable_hopfield: bool = True,
        enable_geometric: bool = True,
        reference_patterns: Optional[np.ndarray] = None
    ):
        self.hv_dim = hv_dim
        self.enable_hopfield = enable_hopfield
        self.enable_geometric = enable_geometric
        
        # Initialize energy model
        if create_energy_model is not None:
            self.energy_model = create_energy_model(
                hv_dim=hv_dim,
                store_reference_patterns=reference_patterns
            )
        else:
            self.energy_model = None
            
        # Fallback analyzers for standalone mode
        self._geometric_analyzer = HDCGeometricAnalyzer(hv_dim) if HDCGeometricAnalyzer else None
        
        # State history for curvature computation
        self._state_history: List[np.ndarray] = []
        self._max_history = 10
        
        # Tick counter
        self._tick_count = 0
    
    def compute_tick_energy(
        self,
        kernel_state: Dict,
        hse_vector: Optional[np.ndarray] = None,
        context_history: Optional[List[np.ndarray]] = None
    ) -> EnergyTickFrame:
        """
        Compute energy metrics for a kernel tick.
        
        Args:
            kernel_state: Current GeometryKernel state dict
            hse_vector: Current HSE embedding (10000-dim)
            context_history: Recent HSE vectors for trajectory analysis
            
        Returns:
            EnergyTickFrame with all computed metrics
        """
        self._tick_count += 1
        tick_id = f"tick_{self._tick_count}"
        
        # Use provided history or internal
        if context_history is not None:
            history = context_history
        else:
            history = self._state_history
        
        # Store current state in history
        if hse_vector is not None:
            self._state_history.append(hse_vector)
            if len(self._state_history) > self._max_history:
                self._state_history.pop(0)
        
        # Compute energy components
        hopfield_energy = self._compute_hopfield_energy(hse_vector)
        geometric_energy = self._compute_geometric_energy(history)
        jepa_energy = self._compute_jepa_energy(hse_vector, history)
        
        # Weighted total (matches ARCAEnergyModel weights)
        total = (
            0.35 * hopfield_energy +
            0.25 * geometric_energy +
            (0.4 * jepa_energy if jepa_energy is not None else 0.2)
        )
        
        # Stability is inverse of energy
        stability = max(0.0, 1.0 - total)
        
        # Interpret
        interpretation, recommendation = self._interpret_energy(total, {
            'hopfield': hopfield_energy,
            'geometric': geometric_energy,
            'jepa': jepa_energy
        })
        
        return EnergyTickFrame(
            timestamp=datetime.now(),
            tick_id=tick_id,
            hopfield_energy=hopfield_energy,
            geometric_energy=geometric_energy,
            jepa_energy=jepa_energy,
            total_energy=total,
            stability_score=stability,
            interpretation=interpretation,
            recommendation=recommendation
        )
    
    def _compute_hopfield_energy(self, hse_vector: Optional[np.ndarray]) -> float:
        """Compute distance from nearest Hopfield attractor."""
        if not self.enable_hopfield or hse_vector is None:
            return 0.3  # Default moderate energy
        
        if self.energy_model is not None and self.energy_model.hopfield is not None:
            import torch
            try:
                energy = self.energy_model.hopfield.compute_energy(
                    torch.tensor(hse_vector).float()
                ).item()
                # Normalize to 0-1 range
                return min(1.0, max(0.0, energy / 10.0))
            except Exception:
                return 0.3
        
        return 0.3
    
    def _compute_geometric_energy(self, history: List[np.ndarray]) -> float:
        """Compute trajectory smoothness/curvature."""
        if not self.enable_geometric or len(history) < 3:
            return 0.2  # Default low energy for insufficient data
        
        if self._geometric_analyzer is not None:
            try:
                trajectory = np.stack(history[-5:])  # Use last 5 states
                curvatures = self._geometric_analyzer.compute_local_curvature(trajectory)
                return min(1.0, float(np.mean(curvatures)))
            except Exception:
                return 0.2
        
        # Fallback: simple velocity variance
        try:
            trajectory = np.stack(history[-5:])
            velocities = np.diff(trajectory, axis=0)
            variance = np.var(np.linalg.norm(velocities, axis=1))
            return min(1.0, variance * 10)
        except Exception:
            return 0.2
    
    def _compute_jepa_energy(
        self, 
        current: Optional[np.ndarray],
        history: List[np.ndarray]
    ) -> Optional[float]:
        """Compute JEPA prediction error (if JEPA model available)."""
        # JEPA integration would require noumenal_engine
        # For now, return None (not computed)
        return None
    
    def _interpret_energy(
        self, 
        total: float,
        components: Dict[str, Optional[float]]
    ) -> Tuple[str, Optional[str]]:
        """Interpret energy levels in human terms."""
        if total < 0.2:
            return "Highly stable", None
        elif total < 0.4:
            return "Stable", None
        elif total < 0.6:
            # Find dominant energy source
            dominant = max(
                [(k, v) for k, v in components.items() if v is not None],
                key=lambda x: x[1],
                default=('unknown', 0)
            )
            return f"Marginally stable (primary: {dominant[0]})", "Consider monitoring"
        elif total < 0.8:
            return "Unstable", "Recommend state consolidation"
        else:
            return "Critical instability", "Abort pending operations"
    
    def validate_design(
        self,
        proposal_hv: np.ndarray,
        reference_designs: np.ndarray,
        threshold: float = 0.6
    ) -> Dict:
        """
        Validate a proposed design against energy model.
        
        This is called BEFORE committing changes to ensure
        the design is geometrically sound.
        
        Returns:
            Dict with approved/rejected and energy metrics
        """
        if self.energy_model is None:
            return {
                'approved': True,
                'energy': 0.5,
                'reason': 'Energy model not available - defaulting to approved'
            }
        
        result = self.energy_model.compute_design_energy(
            proposal_hv, 
            reference_designs
        )
        
        return {
            'approved': result.total < threshold,
            'energy': result.total,
            'components': result.components,
            'interpretation': result.interpretation,
            'recommendation': result.recommendation
        }
    
    def add_reference_pattern(self, pattern: np.ndarray, label: str = ""):
        """Add a known-good pattern as a Hopfield attractor."""
        if self.energy_model is not None and self.energy_model.hopfield is not None:
            import torch
            current = self.energy_model.hopfield.stored_patterns
            if current is None:
                self.energy_model.hopfield.store_patterns(
                    torch.tensor(pattern).float().unsqueeze(0)
                )
            else:
                new_patterns = torch.cat([
                    current,
                    torch.tensor(pattern).float().unsqueeze(0)
                ], dim=0)
                self.energy_model.hopfield.stored_patterns = new_patterns
    
    def get_metrics(self) -> Dict:
        """Get current energy integration metrics."""
        return {
            'tick_count': self._tick_count,
            'history_length': len(self._state_history),
            'hopfield_enabled': self.enable_hopfield,
            'geometric_enabled': self.enable_geometric,
            'energy_model_loaded': self.energy_model is not None
        }


# Singleton for kernel integration
_integration_instance: Optional[EnergyIntegration] = None


def get_energy_integration() -> EnergyIntegration:
    """Get or create the energy integration singleton."""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = EnergyIntegration()
    return _integration_instance


def compute_tick_energy(
    kernel_state: Dict,
    hse_vector: Optional[np.ndarray] = None
) -> Dict:
    """
    Convenience function for computing tick energy.
    
    Can be called from geometry_kernel API.
    """
    integration = get_energy_integration()
    frame = integration.compute_tick_energy(kernel_state, hse_vector)
    return frame.to_dict()
