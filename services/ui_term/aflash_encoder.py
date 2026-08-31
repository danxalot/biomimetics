"""
AFlash Encoder - NumPy Version
=======================

Adaptive FLASH Encoder.
Projects arbitrary input vectors to high-dimensional binary vectors (HDC).
"""

import numpy as np
from typing import Optional


class BinarySign:
    """Straight-through estimator for sign() function."""
    
    @staticmethod
    def forward(input: np.ndarray) -> np.ndarray:
        """Apply sign function: values > 0 -> +1, others -> -1."""
        return np.where(input >= 0, 1.0, -1.0).astype(np.float32)
    
    @staticmethod
    def backward(grad_output: np.ndarray) -> np.ndarray:
        """Straight-through: pass gradient clamped to [-1, 1]."""
        return np.clip(grad_output, -1.0, 1.0)


class AFlashEncoder:
    """
    Adaptive FLASH Encoder.
    Projects arbitrary input vectors to high-dimensional binary vectors (HDC).
    """
    
    def __init__(self, input_dim=1024, hdc_dim=10000):
        self.input_dim = input_dim
        self.hdc_dim = hdc_dim
        
        # Random projection matrix (fixed, Gaussian initialized)
        # Shape: (hdc_dim, input_dim) for output = input @ weight.T
        self.projection_weight = np.random.normal(
            loc=0.0, scale=1.0, size=(hdc_dim, input_dim)
        ).astype(np.float32)
        
        # Batch normalization parameters
        # Running stats for normalization
        self.bn_running_mean = np.zeros(hdc_dim, dtype=np.float32)
        self.bn_running_var = np.ones(hdc_dim, dtype=np.float32)
        self.bn_momentum = 0.1
        self.bn_eps = 1e-5
        
        # Learnable scale and shift (from BatchNorm)
        self.bn_scale = np.ones(hdc_dim, dtype=np.float32)
        self.bn_shift = np.zeros(hdc_dim, dtype=np.float32)
    
    def _batch_norm(self, x: np.ndarray, training: bool = False) -> np.ndarray:
        """
        Batch normalization.
        
        Args:
            x: Input of shape (batch, hdc_dim)
            training: If True, update running stats
            
        Returns:
            Normalized output
        """
        if training:
            # Compute batch stats
            batch_mean = np.mean(x, axis=0)
            batch_var = np.var(x, axis=0)
            
            # Update running stats
            self.bn_running_mean = (
                (1 - self.bn_momentum) * self.bn_running_mean
                + self.bn_momentum * batch_mean
            )
            self.bn_running_var = (
                (1 - self.bn_momentum) * self.bn_running_var
                + self.bn_momentum * batch_var
            )
            
            mean = batch_mean
            var = batch_var
        else:
            mean = self.bn_running_mean
            var = self.bn_running_var
        
        # Normalize
        x_norm = (x - mean) / np.sqrt(var + self.bn_eps)
        
        # Scale and shift
        return self.bn_scale * x_norm + self.bn_shift
    
    def forward(self, x: np.ndarray) -> np.ndarray:
        """
        Forward pass.
        
        Args:
            x: Input array of shape (input_dim,) or (batch, input_dim)
            
        Returns:
            Binary HDC vector of shape (batch, hdc_dim) or (hdc_dim,)
        """
        # Ensure numpy array
        if isinstance(x, list):
            x = np.array(x, dtype=np.float32)
        else:
            x = x.astype(np.float32)
        
        # Ensure 2D
        if x.ndim == 1:
            x = x[np.newaxis, :]
        
        # Linear projection: (batch, input_dim) @ (hdc_dim, input_dim).T -> (batch, hdc_dim)
        projected = x @ self.projection_weight.T
        
        # Batch normalization
        normalized = self._batch_norm(projected, training=False)
        
        # Apply binary sign (straight-through for training, but we just do inference)
        output = BinarySign.forward(normalized)
        
        return output
    
    def encode(self, x) -> np.ndarray:
        """Helper to get numpy array output directly."""
        if isinstance(x, np.ndarray):
            output = self.forward(x)
        else:
            # Assume it's a list or other array-like
            output = self.forward(np.array(x, dtype=np.float32))
        
        return output.flatten().astype(np.int8)
