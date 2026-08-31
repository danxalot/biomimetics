"""
Energy-Based Cognition Layer for ARCA Neural System

Implements:
- JEPAEnergy: Prediction error as energy landscape
- HDCHopfieldMemory: Modern Hopfield network for HDC state attractors  
- HDCGeometricAnalyzer: Curvature and smoothness metrics for design quality
- ARCAEnergyModel: Unified energy computation combining all components

Based on: Energy-Based Geometric Cognition for ARCA source document.
"""

import math
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class EnergyResult:
    """Result container for energy computations."""
    total: float
    components: Dict[str, float]
    interpretation: str
    recommendation: Optional[str] = None


class JEPAEnergy:
    """
    JEPA prediction error defines an energy landscape.
    
    Energy(state) = ||predicted_representation - actual_representation||²
    
    Low energy = predictable state = stable, understood configuration
    High energy = unpredictable state = novel, unstable, or anomalous
    """
    
    def __init__(self, context_encoder, predictor, target_encoder):
        """
        Args:
            context_encoder: Encodes context window
            predictor: Predicts future representation from context
            target_encoder: EMA of context encoder for stable targets
        """
        self.context_encoder = context_encoder
        self.predictor = predictor
        self.target_encoder = target_encoder
    
    def compute_energy(
        self, 
        current_state: np.ndarray,
        context: np.ndarray,
        future_state: np.ndarray
    ) -> np.ndarray:
        """
        Compute JEPA energy for a state transition.
        
        Low energy = transition was predictable = stable dynamics
        High energy = transition was surprising = instability or novelty
        """
        # Encode context
        z_context = self.context_encoder(context)
        
        # Predict future representation
        z_predicted = self.predictor(z_context)
        
        # Get actual future representation (no gradient)
        z_actual = self.target_encoder(future_state)
        
        # Energy is prediction error (MSE)
        energy = np.sum((z_predicted - z_actual) ** 2, axis=-1)
        
        return energy
    
    def compute_trajectory_energy(self, trajectory: List[np.ndarray]) -> np.ndarray:
        """
        Compute total energy of a trajectory.
        
        Smooth trajectories have low total energy.
        Erratic trajectories have high total energy.
        """
        total_energy = np.array(0.0)
        
        for t in range(len(trajectory) - 1):
            # Context: up to 5 previous timesteps + current
            start_idx = max(0, t - 4)  # t-4 to t gives 5 elements
            context = np.stack(trajectory[start_idx:t+1])
            current = trajectory[t]
            future = trajectory[t + 1]
            
            energy = self.compute_energy(current, context, future)
            total_energy = total_energy + energy
        
        return total_energy


class HDCHopfieldMemory:
    """
    Energy-based associative memory for HDC states.
    
    Combines HDC's holographic properties with Hopfield's energy landscape.
    
    Key properties:
    - Stored patterns become energy minima (attractors)
    - Query retrieval = energy minimization
    - Pattern completion = gradient descent on energy surface
    - Capacity scales exponentially with dimension
    """
    
    def __init__(
        self, 
        hv_dim: int = 10000,
        num_heads: int = 8,
        pattern_projection_dim: int = 512,
        beta: float = 4.0  # Inverse temperature (sharpness)
    ):
        self.hv_dim = hv_dim
        self.beta = beta
        
        # Project HDC vectors to Hopfield-compatible dimension
        # Input projection: hv_dim -> pattern_projection_dim
        limit_in = math.sqrt(6.0 / (hv_dim + pattern_projection_dim))
        self.input_projection_weight = np.random.uniform(-limit_in, limit_in, (pattern_projection_dim, hv_dim)).astype(np.float32)
        self.input_projection_bias = np.zeros(pattern_projection_dim, dtype=np.float32)
        
        # Output projection: pattern_projection_dim -> hv_dim
        limit_out = math.sqrt(6.0 / (pattern_projection_dim + hv_dim))
        self.output_projection_weight = np.random.uniform(-limit_out, limit_out, (hv_dim, pattern_projection_dim)).astype(np.float32)
        self.output_projection_bias = np.zeros(hv_dim, dtype=np.float32)
        
        # Stored patterns (learned or set explicitly)
        self.stored_patterns: Optional[np.ndarray] = None
        
        # Pattern projection dimension
        self.pattern_dim = pattern_projection_dim
    
    def store_patterns(self, patterns: np.ndarray):
        """
        Store HDC patterns as attractors in the energy landscape.
        
        Args:
            patterns: [N, hv_dim] - patterns to store
        """
        # Project to Hopfield space: [N, hv_dim] @ [pattern_projection_dim, hv_dim]^T + [pattern_projection_dim] -> [N, pattern_projection_dim]
        projected = np.dot(patterns, self.input_projection_weight.T) + self.input_projection_bias
        self.stored_patterns = projected
        logger.info(f"Stored {len(patterns)} patterns as attractors")
    
    def _logsumexp(self, x: np.ndarray, axis: int = None) -> np.ndarray:
        """Compute log(sum(exp(x))) in a numerically stable way."""
        x_max = np.max(x, axis=axis, keepdims=True)
        return x_max + np.log(np.sum(np.exp(x - x_max), axis=axis, keepdims=True))
    
    def compute_energy(self, query: np.ndarray) -> np.ndarray:
        """
        Compute energy of a query state.
        
        Low energy = close to a stored pattern (attractor)
        High energy = far from all stored patterns (unstable region)
        """
        if self.stored_patterns is None:
            raise ValueError("No patterns stored - call store_patterns() first")
        
        # Ensure query is 2D: [B, hv_dim]
        if query.ndim == 1:
            query = query.reshape(1, -1)
        
        # Project query: [B, hv_dim] @ [pattern_projection_dim, hv_dim]^T + [pattern_projection_dim] -> [B, pattern_projection_dim]
        q = np.dot(query, self.input_projection_weight.T) + self.input_projection_bias
        
        # Compute Modern Hopfield energy
        # E = -lse(β, X^T q) + 0.5 * ||q||²
        # similarities = X^T q = [pattern_projection_dim, N] @ [N, B]^T -> [pattern_projection_dim, B]
        # Actually, we want [N, B] where N is num_patterns, B is batch_size
        similarities = np.dot(self.stored_patterns, q.T)  # [N, B]
        
        # lse = log(sum(exp(β * similarities))) / β for each batch element
        lse = self._logsumexp(self.beta * similarities, axis=0) / self.beta  # [B]
        query_norm = 0.5 * np.sum(q ** 2, axis=1)  # [B]
        
        energy = -lse + query_norm  # [B]
        
        # Return scalar if input was 1D
        if energy.shape[0] == 1 and query.ndim == 1:
            return energy[0]
        return energy
    
    def retrieve(self, query: np.ndarray, num_iterations: int = 3) -> np.ndarray:
        """
        Retrieve nearest pattern via energy minimization.
        
        Iterative retrieval converges to energy minimum.
        """
        # Ensure query is 2D: [B, hv_dim]
        was_1d = False
        if query.ndim == 1:
            query = query.reshape(1, -1)
            was_1d = True
        
        # Project query: [B, hv_dim] @ [pattern_projection_dim, hv_dim]^T + [pattern_projection_dim] -> [B, pattern_projection_dim]
        q = np.dot(query, self.input_projection_weight.T) + self.input_projection_bias
        
        for _ in range(num_iterations):
            # Hopfield update rule (softmax attention over stored patterns)
            # attention = softmax((stored_patterns @ q.T) * beta, axis=0)  # [N, B] -> transpose to [B, N]
            attn_weights = np.dot(self.stored_patterns, q.T) * self.beta  # [N, B]
            attn_weights = np.exp(attn_weights - np.max(attn_weights, axis=0, keepdims=True))  # [N, B]
            attn_weights = attn_weights / np.sum(attn_weights, axis=0, keepdims=True)  # [N, B]
            attn_weights = attn_weights.T  # [B, N]
            
            # q = attention @ stored_patterns  # [B, N] @ [N, pattern_projection_dim] -> [B, pattern_projection_dim]
            q = np.dot(attn_weights, self.stored_patterns)  # [B, pattern_projection_dim]
        
        # Project back to HDC space: [B, pattern_projection_dim] @ [hv_dim, pattern_projection_dim]^T + [hv_dim] -> [B, hv_dim]
        retrieved = np.dot(q, self.output_projection_weight.T) + self.output_projection_bias
        
        # Binarize for HDC
        retrieved = np.sign(retrieved)
        
        # Return original shape
        if was_1d:
            return retrieved.squeeze(0)
        return retrieved
    
    def compute_energy_gradient(self, query: np.ndarray) -> np.ndarray:
        """
        Compute gradient of energy w.r.t. query.
        
        This tells us which direction to move to decrease energy
        (toward nearest attractor).
        """
        # For NumPy, we'll compute the gradient analytically
        # Energy E = -lse(β, X^T q) + 0.5 * ||q||²
        # where q = W_i * x + b_i
        
        # Ensure query is 2D: [B, hv_dim]
        was_1d = False
        if query.ndim == 1:
            query = query.reshape(1, -1)
            was_1d = True
        
        # Project query: [B, hv_dim] @ [pattern_projection_dim, hv_dim]^T + [pattern_projection_dim] -> [B, pattern_projection_dim]
        q = np.dot(query, self.input_projection_weight.T) + self.input_projection_bias
        
        # Compute lse component gradient
        # lse = log(sum(exp(β * X^T q))) / β
        # d(lse)/dq = (softmax(β * X^T q) @ X)  # [B, pattern_projection_dim]
        similarities = np.dot(self.stored_patterns, q.T)  # [N, B]
        beta_similarities = self.beta * similarities  # [N, B]
        
        # Softmax over patterns (axis=0) for each batch
        exp_beta_sim = np.exp(beta_similarities - np.max(beta_similarities, axis=0, keepdims=True))  # [N, B]
        softmax_weights = exp_beta_sim / np.sum(exp_beta_sim, axis=0, keepdims=True)  # [N, B]
        
        # d(lse)/dq = (softmax_weights.T @ stored_patterns)  # [B, N] @ [N, pattern_projection_dim] -> [B, pattern_projection_dim]
        dlse_dq = np.dot(softmax_weights.T, self.stored_patterns)  # [B, pattern_projection_dim]
        
        # d(0.5 * ||q||²)/dq = q  # [B, pattern_projection_dim]
        dq_norm_dq = q  # [B, pattern_projection_dim]
        
        # dE/dq = -dlse_dq + dq_norm_dq  # [B, pattern_projection_dim]
        dE_dq = -dlse_dq + dq_norm_dq  # [B, pattern_projection_dim]
        
        # dq/dx = W_i  # [pattern_projection_dim, hv_dim]
        # dE/dx = dE/dq * dq/dx = dE/dq @ W_i  # [B, pattern_projection_dim] @ [pattern_projection_dim, hv_dim] -> [B, hv_dim]
        dE_dx = np.dot(dE_dq, self.input_projection_weight)  # [B, hv_dim]
        
        # Return original shape
        if was_1d:
            return dE_dx.squeeze(0)
        return dE_dx


class HDCGeometricAnalyzer:
    """
    Analyze geometric properties of HDC configurations.
    
    Smooth, low-curvature shapes = good designs
    Sharp, high-curvature shapes = problematic designs
    """
    
    def __init__(self, hv_dim: int = 10000):
        self.hv_dim = hv_dim
    
    def compute_local_curvature(self, trajectory: np.ndarray) -> np.ndarray:
        """
        Compute curvature along a trajectory in HDC space.
        
        Args:
            trajectory: [T, D] sequence of HDC vectors
            
        Returns:
            Curvature values for each point (high = sharp turns = instability)
        """
        T = len(trajectory)
        curvatures = np.zeros(T - 2)
        
        for t in range(1, T - 1):
            # First derivative (tangent)
            tangent = trajectory[t + 1] - trajectory[t - 1]
            tangent_norm = np.linalg.norm(tangent)
            if tangent_norm > 0:
                tangent = tangent / tangent_norm
            
            # Second derivative (curvature direction)
            second_deriv = trajectory[t + 1] - 2 * trajectory[t] + trajectory[t - 1]
            
            # Curvature magnitude
            curvatures[t - 1] = np.linalg.norm(second_deriv)
        
        return curvatures
    
    def compute_manifold_smoothness(
        self, 
        points: np.ndarray,
        k_neighbors: int = 10
    ) -> Dict:
        """
        Compute smoothness metrics for a point cloud in HDC space.
        
        Uses local PCA to estimate tangent space consistency.
        
        Returns:
            Dict with smoothness_score (0-1), local_dimensions, etc.
        """
        # Simple Hamming distance nearest neighbors (manual implementation)
        N = len(points)
        
        # Compute pairwise Hamming distances
        distances = np.zeros((N, N))
        for i in range(N):
            for j in range(i+1, N):
                # Hamming distance for binary vectors
                dist = np.sum(points[i] != points[j]) / len(points[i])
                distances[i, j] = dist
                distances[j, i] = dist
        
        # Find k nearest neighbors for each point (excluding self)
        indices = np.zeros((N, k_neighbors), dtype=int)
        dist_values = np.zeros((N, k_neighbors))
        
        for i in range(N):
            # Get distances to all other points
            dist_to_others = distances[i].copy()
            dist_to_others[i] = np.inf  # Exclude self
            # Get indices of k nearest neighbors
            nearest_idx = np.argsort(dist_to_others)[:k_neighbors]
            indices[i] = nearest_idx
            dist_values[i] = dist_to_others[nearest_idx]
        
        # Compute local tangent space at each point (simplified - using variance as proxy)
        # Since we don't have sklearn PCA, we'll use a simpler measure of local consistency
        tangent_dims = []
        
        for i in range(N):
            neighbors = points[indices[i]]
            # For binary HDC vectors, we can use the variance of neighbors as a proxy for dimensionality
            # Higher variance in neighbor positions indicates higher effective dimensionality
            neighbor_variance = np.var(neighbors.astype(float))
            # Map variance to a dimension-like value (heuristic)
            eff_dim = min(10, max(1, int(neighbor_variance * 10)))  # Scale to 1-10 range
            tangent_dims.append(eff_dim)
        
        # Smoothness = consistency of tangent space dimension
        dim_variance = np.var(tangent_dims)
        
        return {
            'mean_local_dimension': np.mean(tangent_dims),
            'dimension_variance': dim_variance,  # Low = smooth
            'smoothness_score': 1.0 / (1.0 + dim_variance),  # Higher = smoother
            'local_dimensions': tangent_dims
        }
    
    def detect_geometric_anomalies(
        self,
        design_hv: np.ndarray,
        reference_designs: np.ndarray
    ) -> Dict:
        """
        Detect if a design has geometric anomalies compared to known good designs.
        
        Anomalies indicate:
        - Sharp edges (discontinuities)
        - Isolated regions (disconnected components)
        - High local curvature (instability)
        """
        # Ensure design_hv is 2D: [1, D] if it's 1D
        if design_hv.ndim == 1:
            design_hv = design_hv.reshape(1, -1)
        
        # Find nearest reference designs using manual Hamming distance
        # Compute Hamming distances from design to all reference designs
        # design_hv: [1, D], reference_designs: [N, D] -> distances: [N]
        distances = np.sum(reference_designs != design_hv, axis=1) / reference_designs.shape[1]
        
        # Get indices of 5 nearest neighbors
        k = 5
        if len(distances) < k:
            k = len(distances)
        nearest_indices = np.argsort(distances)[:k]
        nearest_distances = distances[nearest_indices]
        
        neighbors = reference_designs[nearest_indices]
        
        # Check 1: Is design too far from all references? (isolated)
        min_distance = nearest_distances[0] if len(nearest_distances) > 0 else 1.0
        is_isolated = min_distance > 0.4  # More than 40% bits different
        
        # Check 2: Are nearest neighbors consistent? (smooth region)
        neighbor_distances = []
        for i in range(len(neighbors)):
            for j in range(i + 1, len(neighbors)):
                d = np.sum(neighbors[i] != neighbors[j]) / len(neighbors[i])
                neighbor_distances.append(d)
        
        neighbor_variance = np.var(neighbor_distances) if neighbor_distances else 0
        is_rough_region = neighbor_variance > 0.1
        
        # Overall anomaly score
        overall_score = (
            0.5 * float(is_isolated) + 
            0.5 * float(is_rough_region)
        )
        
        return {
            'is_isolated': is_isolated,
            'isolation_distance': float(min_distance),
            'is_rough_region': is_rough_region,
            'region_variance': float(neighbor_variance),
            'overall_anomaly_score': overall_score
        }


class ARCAEnergyModel:
    """
    Unified energy model for the entire ARCA system.
    
    Combines:
    - JEPA prediction energy (dynamics stability)
    - Hopfield attractor energy (state coherence)
    - Geometric smoothness energy (design quality)
    
    Total Energy = α₁E_jepa + α₂E_hopfield + α₃E_geometric
    
    Low total energy = stable, efficient, well-designed system
    """
    
    def __init__(
        self,
        jepa_predictor: Optional[JEPAEnergy] = None,
        hopfield_memory: Optional[HDCHopfieldMemory] = None,
        geometric_analyzer: Optional[HDCGeometricAnalyzer] = None
    ):
        self.jepa = jepa_predictor
        self.hopfield = hopfield_memory
        self.geometric = geometric_analyzer or HDCGeometricAnalyzer()
        
        # Energy component weights (tunable)
        self.weights = {
            'jepa': 0.4,       # Predictability
            'hopfield': 0.35,  # Attractor proximity
            'geometric': 0.25  # Smoothness
        }
    
    def compute_state_energy(
        self,
        current_state: np.ndarray,
        context: Optional[List[np.ndarray]] = None,
        future_state: Optional[np.ndarray] = None
    ) -> EnergyResult:
        """
        Compute comprehensive energy for a system state.
        """
        energies = {}
        
        # 1. Hopfield energy: distance from attractors
        if self.hopfield is not None and self.hopfield.stored_patterns is not None:
            hopfield_energy = self.hopfield.compute_energy(
                current_state
            )
            # Handle both scalar and array returns
            if np.isscalar(hopfield_energy):
                energies['hopfield'] = float(hopfield_energy)
            else:
                energies['hopfield'] = float(hopfield_energy[0]) if len(hopfield_energy) == 1 else float(np.mean(hopfield_energy))
        else:
            energies['hopfield'] = 0.0
        
        # 2. JEPA energy: prediction consistency (if context provided)
        if self.jepa is not None and context is not None and future_state is not None:
            jepa_energy = self.jepa.compute_energy(
                current_state,
                np.stack(context),
                future_state
            )
            # Handle both scalar and array returns
            if np.isscalar(jepa_energy):
                energies['jepa'] = float(jepa_energy)
            else:
                energies['jepa'] = float(jepa_energy[0]) if len(jepa_energy) == 1 else float(np.mean(jepa_energy))
        else:
            energies['jepa'] = 0.0
        
        # 3. Geometric energy: local smoothness
        if context is not None and len(context) >= 3:
            trajectory = np.stack(context + [current_state])
            curvatures = self.geometric.compute_local_curvature(trajectory)
            energies['geometric'] = float(np.mean(curvatures))
        else:
            energies['geometric'] = 0.0
        
        # Compute weighted total
        total_energy = sum(
            self.weights[key] * energies[key]
            for key in energies
        )
        
        return EnergyResult(
            total=total_energy,
            components=energies,
            interpretation=self._interpret_energy(total_energy, energies)
        )
    
    def compute_design_energy(
        self,
        design_hv: np.ndarray,
        reference_designs: np.ndarray
    ) -> EnergyResult:
        """
        Compute energy for a proposed design.
        
        Used for validation BEFORE implementation.
        
        Low energy = design is likely stable and efficient
        High energy = design has potential issues
        """
        # 1. Attractor energy: does this design fit known good patterns?
        if self.hopfield is not None:
            hopfield_energy = self.hopfield.compute_energy(
                design_hv
            )
            # Handle both scalar and array returns
            if np.isscalar(hopfield_energy):
                hopfield_energy = float(hopfield_energy)
            else:
                hopfield_energy = float(hopfield_energy[0]) if len(hopfield_energy) == 1 else float(np.mean(hopfield_energy))
        else:
            hopfield_energy = 0.5  # Neutral if no patterns stored
        
        # 2. Geometric anomaly check
        anomalies = self.geometric.detect_geometric_anomalies(
            design_hv, reference_designs
        )
        geometric_energy = anomalies['overall_anomaly_score']
        
        total_energy = 0.5 * hopfield_energy + 0.5 * geometric_energy
        
        return EnergyResult(
            total=total_energy,
            components={
                'attractor_distance': hopfield_energy,
                'geometric_anomaly': geometric_energy
            },
            interpretation=self._interpret_energy(total_energy, {}),
            recommendation=self._design_recommendation(total_energy)
        )
    
    def _interpret_energy(self, total: float, components: Dict) -> str:
        """Interpret energy levels in human terms."""
        if total < 0.2:
            stability = "Highly stable"
        elif total < 0.5:
            stability = "Moderately stable"
        elif total < 0.8:
            stability = "Marginally stable"
        else:
            stability = "Unstable"
        
        # Find dominant energy source
        if components:
            dominant = max(components, key=components.get)
            dominant_desc = {
                'jepa': "unpredictable dynamics",
                'hopfield': "distance from known stable states",
                'geometric': "local trajectory roughness"
            }
            return f"{stability}. Primary concern: {dominant_desc.get(dominant, dominant)}"
        
        return stability
    
    def _design_recommendation(self, energy: float) -> str:
        """Provide recommendation based on design energy."""
        if energy < 0.2:
            return "APPROVED: Design appears stable and efficient. Proceed."
        elif energy < 0.4:
            return "CAUTION: Minor concerns. Review highlighted areas."
        elif energy < 0.6:
            return "WARNING: Significant energy. Consider modifications."
        else:
            return "REJECTED: High energy. Major redesign recommended."


# Factory function for easy instantiation
def create_energy_model(
    hv_dim: int = 10000,
    store_reference_patterns: Optional[np.ndarray] = None
) -> ARCAEnergyModel:
    """
    Create a ready-to-use energy model.
    
    Args:
        hv_dim: Dimension of HDC vectors
        store_reference_patterns: Optional reference patterns to store as attractors
    """
    hopfield = HDCHopfieldMemory(hv_dim=hv_dim)
    
    if store_reference_patterns is not None:
        hopfield.store_patterns(store_reference_patterns)
    
    geometric = HDCGeometricAnalyzer(hv_dim=hv_dim)
    
    return ARCAEnergyModel(
        hopfield_memory=hopfield,
        geometric_analyzer=geometric
    )
