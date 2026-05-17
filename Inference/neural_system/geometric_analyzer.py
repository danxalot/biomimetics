"""
Energy-Based Geometric Cognition for ARCA
Geometric Analyzer Component
========================================

This module implements the geometric analysis tools for the Energy-Based HDC architecture.
It evaluates the smoothness, curvature, and stability of HDC state trajectories and manifolds.

Key Metrics:
- Local Curvature: Detects sharp turns in state space (instability).
- Manifold Smoothness: consistency of local tangent spaces (coherence).
- Lipschitz Constant: smoothness of function mappings.
- Anomaly Detection: isolation and roughness checks.

References:
- "Energy-Based Geometric Cognition for ARCA"
"""

import numpy as np
from typing import List, Dict, Union, Optional
import logging

# Configure Logging
logger = logging.getLogger("HDCGeometry")

class HDCGeometricAnalyzer:
    """
    Analyze geometric properties of HDC configurations.
    
    Smooth, low-curvature shapes = good designs
    Sharp, high-curvature shapes = problematic designs
    """
    
    def __init__(self, hv_dim: int = 4096):
        self.hv_dim = hv_dim
        
    def compute_local_curvature(self, trajectory: np.ndarray) -> np.ndarray:
        """
        Compute curvature along a trajectory in HDC space.
        
        trajectory: [T, D] sequence of HDC vectors
        
        Curvature κ = |dT/ds| where T is the unit tangent vector
        High curvature = sharp turns = instability
        """
        T = len(trajectory)
        if T < 3:
            return np.zeros(0)

        curvatures = np.zeros(T - 2)
        
        for t in range(1, T - 1):
            # First derivative (tangent)
            tangent = trajectory[t + 1] - trajectory[t - 1]
            tangent_norm = np.linalg.norm(tangent)
            if tangent_norm > 1e-9:
                tangent = tangent / tangent_norm
            else:
                tangent = np.zeros_like(tangent)
            
            # Second derivative (curvature direction)
            # Finite difference approximation of second derivative
            second_deriv = trajectory[t + 1] - 2 * trajectory[t] + trajectory[t - 1]
            
            # Curvature magnitude
            curvatures[t - 1] = np.linalg.norm(second_deriv)
        
        return curvatures
    
    def compute_manifold_smoothness(self, points: np.ndarray, 
                                     k_neighbors: int = 10) -> dict:
        """
        Compute smoothness metrics for a point cloud in HDC space.
        
        Uses local PCA to estimate tangent space consistency.
        
        Smooth manifold = consistent local structure
        Rough manifold = inconsistent local structure
        """
        try:
            from sklearn.neighbors import NearestNeighbors
            from sklearn.decomposition import PCA
        except ImportError:
            logger.warning("scikit-learn not found. Skipping manifold smoothness.")
            return {'smoothness_score': 0.0, 'error': 'missing_dependency'}
        
        N = len(points)
        if N < k_neighbors:
             logger.warning(f"Not enough points for manifold analysis. Need {k_neighbors}, got {N}.")
             return {'smoothness_score': 0.0, 'warning': 'not_enough_points'}
        
        # Find k nearest neighbors for each point
        nn = NearestNeighbors(n_neighbors=k_neighbors, metric='hamming')
        nn.fit(points)
        distances, indices = nn.kneighbors(points)
        
        # Compute local tangent space at each point
        tangent_dims = []
        
        for i in range(N):
            neighbors = points[indices[i]]
            
            # Local PCA
            # Limit components to minimal of (samples-1, features)
            n_comps = min(k_neighbors - 1, self.hv_dim, 10)
            pca = PCA(n_components=n_comps)
            pca.fit(neighbors)
            
            # Effective dimensionality (how many components explain 90% variance)
            cumvar = np.cumsum(pca.explained_variance_ratio_)
            eff_dim = np.searchsorted(cumvar, 0.9) + 1
            tangent_dims.append(eff_dim)
        
        # Smoothness = consistency of tangent space dimension
        dim_variance = np.var(tangent_dims)
        
        return {
            'mean_local_dimension': float(np.mean(tangent_dims)),
            'dimension_variance': float(dim_variance),  # Low = smooth
            'smoothness_score': 1.0 / (1.0 + float(dim_variance)),  # Higher = smoother
            'local_dimensions': tangent_dims
        }
    
    def compute_lipschitz_constant(self, func, sample_points: np.ndarray) -> float:
        """
        Estimate Lipschitz constant of a function over HDC space.
        
        Lipschitz constant L means: |f(x) - f(y)| <= L * |x - y|
        
        Low L = function changes slowly = smooth
        High L = function can change rapidly = not smooth
        """
        N = len(sample_points)
        max_ratio = 0.0
        
        # Sample pairs (limit iterations for performance)
        limit = min(N, 1000)
        
        for i in range(limit):
            # Check a few random pairs instead of all-to-all O(N^2)
            # or check consecutive if sorted? Random is better for global estimate.
            # Using loop with j > i for distinct pairs
            for j in range(i + 1, min(i + 20, limit)): # Optimization: Check local window or random
                x_i, x_j = sample_points[i], sample_points[j]
                
                # Input distance (Euclidean or Hamming depending on space)
                # Assuming normalized vectors or binary
                input_dist = np.linalg.norm(x_i - x_j)
                
                if input_dist > 1e-6:  # Avoid division by zero
                    # Output distance
                    f_i = func(x_i)
                    f_j = func(x_j)
                    output_dist = np.linalg.norm(f_i - f_j)
                    
                    ratio = output_dist / input_dist
                    max_ratio = max(max_ratio, ratio)
        
        return max_ratio
    
    def detect_geometric_anomalies(self, design_hv: np.ndarray,
                                    reference_designs: np.ndarray) -> dict:
        """
        Detect if a design has geometric anomalies compared to known good designs.
        
        Anomalies indicate:
        - Sharp edges (discontinuities)
        - Isolated regions (disconnected components)
        - High local curvature (instability)
        """
        try:
            from sklearn.neighbors import NearestNeighbors
        except ImportError:
             return {'error': 'missing_dependency'}

        if len(reference_designs) == 0:
             return {'error': 'no_reference_designs'}
        
        # Find nearest reference designs
        nn = NearestNeighbors(n_neighbors=min(5, len(reference_designs)), metric='euclidean') # Changed to euclidean for float vectors
        nn.fit(reference_designs)
        distances, indices = nn.kneighbors(design_hv.reshape(1, -1))
        
        neighbors = reference_designs[indices[0]]
        
        # Check 1: Is design too far from all references? (isolated)
        min_distance = distances[0, 0]
        # Threshold depends on distribution, heuristic 0.4 for cosine-like distance
        is_isolated = min_distance > 0.4 
        
        # Check 2: Are nearest neighbors consistent? (smooth region)
        neighbor_distances = []
        n_neighbors_count = len(neighbors)
        if n_neighbors_count > 1:
            for i in range(n_neighbors_count):
                for j in range(i + 1, n_neighbors_count):
                    d = np.linalg.norm(neighbors[i] - neighbors[j])
                    neighbor_distances.append(d)
            
            neighbor_variance = np.var(neighbor_distances) if neighbor_distances else 0.0
            is_rough_region = neighbor_variance > 0.1
        else:
            neighbor_variance = 0.0
            is_rough_region = False
        
        # Check 3: Does interpolation make sense? (no sharp transitions)
        interpolation_smoothness = self._check_interpolation_smoothness(
            design_hv, neighbors
        )
        
        return {
            'is_isolated': bool(is_isolated),
            'isolation_distance': float(min_distance),
            'is_rough_region': bool(is_rough_region),
            'region_variance': float(neighbor_variance),
            'interpolation_smoothness': float(interpolation_smoothness),
            'overall_anomaly_score': float(
                0.4 * float(is_isolated) + 
                0.3 * float(is_rough_region) + 
                0.3 * (1.0 - interpolation_smoothness)
            )
        }
    
    def _check_interpolation_smoothness(self, target: np.ndarray, 
                                         neighbors: np.ndarray) -> float:
        """
        Check if target can be smoothly reached from neighbors.
        
        Smooth = gradual changes along path
        Rough = sudden large changes
        """
        smoothness_scores = []
        
        for neighbor in neighbors:
            # Linear Interpolation Check
            # In a smooth manifold, f(lerp(a,b)) should be close to lerp(f(a), f(b))
            # Here we just check energy/distance monotonicity
            
            steps = 10
            path_energies = []
            
            for t in np.linspace(0, 1, steps):
                interpolated = (1 - t) * neighbor + t * target
                # Distance to target should decrease monotonically
                d_to_target = np.linalg.norm(interpolated - target)
                path_energies.append(d_to_target)
            
            # Check monotonicity
            is_monotonic = all(
                path_energies[i] >= path_energies[i+1] - 1e-5 # tolerance
                for i in range(len(path_energies)-1)
            )
            smoothness_scores.append(1.0 if is_monotonic else 0.5)
        
        if not smoothness_scores:
            return 1.0
            
        return np.mean(smoothness_scores)
