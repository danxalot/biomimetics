"""
Modern Hopfield Network for HDC Memory
======================================

Implements a dense associative memory for Hyper-Dimensional Computing states using
Modern Hopfield Network theory (continuous attractor dynamics).

Key Features:
- Energy-based retrieval (Lagrangian formulation)
- Exponential storage capacity
- Pure NumPy/SciPy implementation (no PyTorch)

References:
- "Hopfield Networks is All You Need" (Ramsauer et al., 2020)
- ARCA Energy-Based Geometric Cognition Specification
"""

import logging
from typing import Union, Optional
import numpy as np
try:
    from scipy.special import logsumexp
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    # Fallback implementation if scipy not available
    def logsumexp(a, axis=None):
        """Compute log(sum(exp(a))) in a numerically stable way."""
        a_max = np.amax(a, axis=axis, keepdims=True)
        tmp = np.exp(a - a_max)
        s = np.sum(tmp, axis=axis, keepdims=True)
        out = np.log(s) + a_max
        if axis is not None:
            out = np.squeeze(out, axis=axis)
        return out

logger = logging.getLogger("HDCHopfield")


class HDCHopfieldMemory:
    """
    Energy-based associative memory for HDC states.
    
    Combines HDC's holographic properties with Hopfield's energy landscape.
    Stored patterns become energy minima (attractors).
    """
    
    def __init__(self, hv_dim: int = 4096, 
                 pattern_projection_dim: int = 512,
                 beta: float = 4.0):
        """
        Initialize the Hopfield memory.
        
        Args:
            hv_dim: Dimension of HDC vectors
            pattern_projection_dim: Dimension for Hopfield space projection
            beta: Inverse temperature (scaling factor)
        """
        self.hv_dim = hv_dim
        self.beta = beta  # Inverse temperature (scaling factor)
        
        # Project HDC vectors to Hopfield-compatible dimension (if needed)
        # or use identity if dimensions match.
        if hv_dim != pattern_projection_dim:
            # Initialize projection matrices
            self.input_projection_weight = np.random.randn(pattern_projection_dim, hv_dim).astype(np.float32) * np.sqrt(2.0 / (hv_dim + pattern_projection_dim))
            self.input_projection_bias = np.zeros(pattern_projection_dim, dtype=np.float32)
            self.output_projection_weight = np.random.randn(hv_dim, pattern_projection_dim).astype(np.float32) * np.sqrt(2.0 / (pattern_projection_dim + hv_dim))
            self.output_projection_bias = np.zeros(hv_dim, dtype=np.float32)
            self.internal_dim = pattern_projection_dim
        else:
            # Identity projection
            self.input_projection_weight = None
            self.input_projection_bias = None
            self.output_projection_weight = None
            self.output_projection_bias = None
            self.internal_dim = hv_dim
            
        # Stored patterns (X) - shape: [N, internal_dim]
        self.stored_patterns = np.zeros((0, self.internal_dim), dtype=np.float32)
        
        logger.info(f"HDCHopfieldMemory initialized: {hv_dim}D -> {self.internal_dim}D (beta={beta})")
    
    def _project_input(self, vectors: np.ndarray) -> np.ndarray:
        """Project vectors to Hopfield space."""
        if self.input_projection_weight is None:
            # Identity projection
            return vectors
        else:
            # Linear projection: Wx + b
            return np.dot(vectors, self.input_projection_weight.T) + self.input_projection_bias
    
    def _project_output(self, vectors: np.ndarray) -> np.ndarray:
        """Project vectors back to HDC space."""
        if self.output_projection_weight is None:
            # Identity projection
            return vectors
        else:
            # Linear projection: Wx + b
            return np.dot(vectors, self.output_projection_weight.T) + self.output_projection_bias
    
    def store_patterns(self, patterns: Union[np.ndarray, list]) -> None:
        """
        Store HDC patterns as attractors in the energy landscape.
        
        Args:
            patterns: Array of shape [N, hv_dim] containing patterns to store
        """
        # Convert to numpy array if needed
        if isinstance(patterns, list):
            patterns = np.array(patterns, dtype=np.float32)
        elif not isinstance(patterns, np.ndarray):
            patterns = np.asarray(patterns, dtype=np.float32)
        
        # Handle 1D case
        if patterns.ndim == 1:
            patterns = patterns.reshape(1, -1)
            
        # Validate dimension
        if patterns.shape[1] != self.hv_dim:
            raise ValueError(f"Expected patterns with {self.hv_dim} dimensions, got {patterns.shape[1]}")
        
        # Project to Hopfield space
        projected = self._project_input(patterns)
        
        # Modern Hopfield works best with normalized patterns
        # L2 normalize each pattern
        norms = np.linalg.norm(projected, axis=1, keepdims=True)
        # Avoid division by zero
        norms = np.maximum(norms, 1e-8)
        projected = projected / norms
        
        self.stored_patterns = projected.astype(np.float32)
        logger.info(f"Stored {len(patterns)} patterns in Hopfield Memory.")
    
    def compute_energy(self, query: Union[np.ndarray, list]) -> np.ndarray:
        """
        Compute energy of a query state E(xi).
        
        E = -lse(beta, X^T xi) + 0.5 * ||xi||^2
        
        Low energy = close to a stored pattern (attractor)
        High energy = far from all stored patterns (unstable region)
        
        Args:
            query: Query vector(s) of shape [hv_dim] or [B, hv_dim]
            
        Returns:
            Energy value(s) - scalar for single query, array for batch
        """
        # Convert to numpy array if needed
        if isinstance(query, list):
            query = np.array(query, dtype=np.float32)
        elif not isinstance(query, np.ndarray):
            query = np.asarray(query, dtype=np.float32)
        
        # Handle 1D case
        is_1d = query.ndim == 1
        if is_1d:
            query = query.reshape(1, -1)
            
        # Validate dimension
        if query.shape[1] != self.hv_dim:
            raise ValueError(f"Expected query with {self.hv_dim} dimensions, got {query.shape[1]}")
        
        # If no patterns stored, return zero energy
        if self.stored_patterns.shape[0] == 0:
            energy = np.zeros(query.shape[0], dtype=np.float32)
            return energy.squeeze() if is_1d else energy
        
        # Project and normalize query
        q = self._project_input(query)
        # L2 normalize
        q_norm = np.linalg.norm(q, axis=1, keepdims=True)
        q_norm = np.maximum(q_norm, 1e-8)  # Avoid division by zero
        q = q / q_norm
        
        # 1. Similarity Term (LogSumExp)
        # patterns: [N, D], query: [B, D] -> sim: [B, N]
        similarities = np.dot(q, self.stored_patterns.T)  # [B, N]
        
        # lse = (1/beta) * log(sum(exp(beta * sim)))
        if SCIPY_AVAILABLE:
            lse = (1.0 / self.beta) * logsumexp(self.beta * similarities, axis=1)
        else:
            # Manual logsumexp for beta * similarities
            max_val = np.max(self.beta * similarities, axis=1, keepdims=True)
            exp_shifted = np.exp(self.beta * similarities - max_val)
            sum_exp = np.sum(exp_shifted, axis=1)
            lse = (1.0 / self.beta) * (max_val.squeeze() + np.log(sum_exp))
        
        # 2. Norm Term (Quadratic confinement)
        # For normalized vectors, ||q||^2 = 1, so this is constant 0.5
        # but including for theoretical completeness
        prior = 0.5 * np.sum(q ** 2, axis=1)
        
        # Energy = -LSE + Prior
        # We invert sign so that "Stored Pattern" = Minimum Energy
        energy = -lse + prior
        
        return energy.squeeze() if is_1d else energy
    
    def retrieve(self, query: Union[np.ndarray, list], num_iterations: int = 1) -> np.ndarray:
        """
        Retrieve nearest pattern via Modern Hopfield Update Rule (Attention).
        
        xi_new = softmax(beta * X * xi_old^T) * X
        
        Args:
            query: Query vector(s) of shape [hv_dim] or [B, hv_dim]
            num_iterations: Number of update iterations (default: 1)
            
        Returns:
            Retrieved pattern(s) with same shape as input query
        """
        # Convert to numpy array if needed
        if isinstance(query, list):
            query = np.array(query, dtype=np.float32)
        elif not isinstance(query, np.ndarray):
            query = np.asarray(query, dtype=np.float32)
        
        # Handle 1D case
        is_1d = query.ndim == 1
        if is_1d:
            query = query.reshape(1, -1)
            
        # Validate dimension
        if query.shape[1] != self.hv_dim:
            raise ValueError(f"Expected query with {self.hv_dim} dimensions, got {query.shape[1]}")
        
        # If no patterns stored, return query as-is
        if self.stored_patterns.shape[0] == 0:
            return query.squeeze() if is_1d else query
        
        # Project query (no normalization for update rule as per paper)
        q = self._project_input(query)
        
        for _ in range(num_iterations):
            # Attention Mechanism
            # Q = q, K = stored_patterns, V = stored_patterns
            
            # 1. Attention Scores: beta * Q * K^T
            scores = self.beta * np.dot(q, self.stored_patterns.T)  # [B, N]
            
            # 2. Softmax to get probabilities
            # Softmax: exp(x_i) / sum(exp(x_j))
            max_scores = np.max(scores, axis=1, keepdims=True)
            exp_scores = np.exp(scores - max_scores)  # Subtract max for numerical stability
            sum_exp = np.sum(exp_scores, axis=1, keepdims=True)
            probs = exp_scores / sum_exp  # [B, N]
            
            # 3. Weighted Sum: P * V
            q = np.dot(probs, self.stored_patterns)  # [B, D]
        
        # Project back to HDC space
        retrieved = self._project_output(q)
        
        return retrieved.squeeze() if is_1d else retrieved
    
    def compute_energy_gradient(self, query: Union[np.ndarray, list]) -> np.ndarray:
        """
        Compute gradient of energy w.r.t. query to guide optimization.
        
        Analytical form: ∇E(ξ) = ξ - X · softmax(βXᵀξ)
        
        Args:
            query: Query vector(s) of shape [hv_dim] or [B, hv_dim]
            
        Returns:
            Gradient vector(s) with same shape as input query
        """
        # Convert to numpy array if needed
        if isinstance(query, list):
            query = np.array(query, dtype=np.float32)
        elif not isinstance(query, np.ndarray):
            query = np.asarray(query, dtype=np.float32)
        
        # Handle 1D case
        is_1d = query.ndim == 1
        if is_1d:
            query = query.reshape(1, -1)
            
        # Validate dimension
        if query.shape[1] != self.hv_dim:
            raise ValueError(f"Expected query with {self.hv_dim} dimensions, got {query.shape[1]}")
        
        # If no patterns stored, gradient is zero
        if self.stored_patterns.shape[0] == 0:
            grad = np.zeros_like(query)
            return grad.squeeze() if is_1d else grad
        
        # Project and normalize query (same as in compute_energy)
        q = self._project_input(query)
        q_norm = np.linalg.norm(q, axis=1, keepdims=True)
        q_norm = np.maximum(q_norm, 1e-8)  # Avoid division by zero
        q_normalized = q / q_norm
        
        # Compute softmax term: softmax(β * Xᵀ * ξ_normalized)
        # Xᵀ * ξ_normalized: [D, N] * [B, D]^T = [B, N]
        similarities = np.dot(q_normalized, self.stored_patterns.T)  # [B, N]
        
        # Softmax along patterns dimension (axis=1)
        max_sim = np.max(self.beta * similarities, axis=1, keepdims=True)
        exp_sim = np.exp(self.beta * similarities - max_sim)
        sum_exp = np.sum(exp_sim, axis=1, keepdims=True)
        softmax_output = exp_sim / sum_exp  # [B, N]
        
        # Compute X · softmax(βXᵀξ) = softmax_output · stored_patterns
        # softmax_output: [B, N], stored_patterns: [N, D] -> result: [B, D]
        x_softmax = np.dot(softmax_output, self.stored_patterns)  # [B, D]
        
        # Gradient: ξ_normalized - X · softmax(βXᵀξ)
        # Note: We use normalized query for consistency with energy computation
        grad_normalized = q_normalized - x_softmax  # [B, D]
        
        # Project gradient back to HDC space
        # For the gradient, we need to back-project through the same transformations
        # Since we used input projection + normalization, we need to invert this
        # For simplicity in inference, we return gradient in projected space
        # In a full implementation, we'd back-project through the inverse operations
        
        # For now, return gradient in HDC space by applying output projection
        # This is an approximation - the true gradient would require back-projection
        # through the input projection and normalization steps
        grad_hdc = self._project_output(grad_normalized)
        
        return grad_hdc.squeeze() if is_1d else grad_hdc


# Backward compatibility alias
ModernHopfieldNetwork = HDCHopfieldMemory