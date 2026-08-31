import numpy as np
from typing import List, Dict, Any

class EnergyService:
    """
    Hamiltonian Safety Monitor.
    Ensures the AI system doesn't enter unstable high-energy states.
    """
    
    def __init__(self, kuramoto_field=None, predictor=None, alert_threshold: float = 0.8):
        self.field = kuramoto_field
        self.predictor = predictor # HDCNeuralPredictor (JEPA)
        self.threshold = alert_threshold
        self.history = []

    def compute_system_energy(self, monads: List[Any]) -> float:
        """
        Compute total Hamiltonian H = Kinetic + Potential.
        Kinetic = Frequency deviation from natural freq.
        Potential = Interaction stress (desynchronization).
        """
        if not monads:
            return 0.0
            
        total_E = 0.0
        for m in monads:
            # Kinetic: E_k = 0.5 * (d_theta - omega)^2  (Strain against natural rhythm)
            # Simplified: Just using amplitude * velocity for now if available
            # Using monad.energy from JEPA instead
            total_E += getattr(m, 'energy', 0.0)
            
        return total_E / len(monads)

    def compute_total_energy(self) -> float:
        """Helper to compute energy for all active monads in the field."""
        if not self.field or not self.field.monads:
            return 0.0
        monads = list(self.field.monads.values())
        return self.compute_system_energy(monads)

    def preflight_check(self, proposed_plan_vector: Any, current_state_vector: Any) -> bool:
        """
        Design Validator:
        Checks if a proposed action (plan) requires too much energy or pushes
        the system into the 'Red Zone'.
        
        Uses JEPA to Dream the consequences of the plan.
        """
        # 1. Classical Heuristic (Baseline)
        # estimated_cost = complexity * 0.5 
        # (Replaced by Neural Prediction)
        
        if self.predictor is None:
            # Fallback if no brain available
            print("Warning: No Predictor for Preflight. Approving blindly.")
            return True
            
        # 2. Neural Prediction (The "Thinking" Audit)
        # Fuse Current State + Plan
        # (Using simple addition/superposition for now)
        fused_state = current_state_vector + proposed_plan_vector
        
        # Predict Consequence (Next State)
        predicted_future = self.predictor.predict_next(fused_state)
        
        # 3. Evaluate Energy of Future State
        # E = |P - A|^2 (Drift from healthy attractor)
        # For now, we use the Predictor's internal energy metric or simple drift
        
        # Calculate drift from current (Change Magnitude)
        drift = np.linalg.norm(predicted_future - current_state_vector)
        
        # Normalize drift (approx 100 for large vectors)
        norm_drift = drift / 100.0
        
        if norm_drift > self.threshold:
            print(f"🛑 Design Validator: Plan REJECTED. Predicted Energy Spike: {norm_drift:.2f} > {self.threshold}")
            return False
            
        print(f"✅ Design Validator: Plan APPROVED. Predicted Drift: {norm_drift:.2f}")
        return True

    def log_energy(self, tick: int, energy: float):
        self.history.append((tick, energy))
        # Keep buffer small
        if len(self.history) > 1000:
            self.history.pop(0)
