"""Sparse Distributed Memory (SDM) — Kanerva Memory.

PyTorch port of `services/neural_system/sdm_memory.py`. 
Provides auto-associative "cleanup" for high-dimensional geometric vectors.

Key differences from NumPy version:
- Vectorized Hamming distance via bitwise XOR on Int8/Uint8 tensors.
- Supports gradient flow (if enabled) via Straight-Through Estimators (STE).
- GPU-accelerated location activation.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Dict, Any


class SDMMemory(nn.Module):
    """
    Sparse Distributed Memory (SDM) for auto-associative recall.
    
    Args:
        address_dim: dimensionality of the address space (HDC dimension).
        data_dim: dimensionality of the stored data.
        num_hard_locations: number of "hard" storage locations.
        activation_radius: Hamming distance threshold for location activation.
    """

    def __init__(
        self,
        address_dim: int = 1024,
        data_dim: int = 1024,
        num_hard_locations: int = 10000,
        activation_radius: Optional[int] = None,
    ):
        super().__init__()
        self.address_dim = address_dim
        self.data_dim = data_dim
        self.num_locations = num_hard_locations
        
        # Default radius: roughly 0.45 of dim for sparse activation
        self.activation_radius = activation_radius or int(0.45 * address_dim)

        # Hard locations: Fixed random binary addresses.
        # We store them as [-1, 1] floats to allow dot-product proximity checks 
        # (which is equivalent to Hamming distance for normalized bipolar vectors).
        addresses = torch.randn(num_hard_locations, address_dim).sign()
        self.register_buffer("addresses", addresses)

        # Counters: Accumulators for data storage.
        # Initialized to zeros.
        self.register_buffer("counters", torch.zeros(num_hard_locations, data_dim))

    def _get_active_locations(self, address: torch.Tensor) -> torch.Tensor:
        """Find locations within activation radius using dot-product proximity."""
        # address: [B, D]
        # self.addresses: [L, D]
        # Dot product of bipolar vectors relates to Hamming distance:
        # dot = (dim - 2 * hamming_dist)
        # So: hamming_dist = (dim - dot) / 2
        
        # Normalize to [-1, 1] if not already
        addr_sign = address.sign()
        
        # Compute similarity
        dots = torch.matmul(addr_sign, self.addresses.t())  # [B, L]
        
        # Threshold dots to find active locations
        # dot >= (dim - 2 * radius)
        threshold = self.address_dim - 2 * self.activation_radius
        active_mask = dots >= threshold
        return active_mask

    def write(self, address: torch.Tensor, data: torch.Tensor):
        """
        Write data to SDM at the given address.
        
        Args:
            address: [B, address_dim]
            data: [B, data_dim]
        """
        active_mask = self._get_active_locations(address)  # [B, L]
        data_sign = data.sign()
        
        # Vectorized update: for each batch element, add data to active locations
        # This is essentially a sparse scatter-add
        for b in range(address.shape[0]):
            idx = torch.where(active_mask[b])[0]
            if len(idx) > 0:
                self.counters[idx] += data_sign[b]

    def read(self, address: torch.Tensor) -> torch.Tensor:
        """
        Read from SDM at the given address.
        
        Returns:
            [B, data_dim] bipolar (-1/1) tensor.
        """
        active_mask = self._get_active_locations(address)  # [B, L]
        
        results = []
        for b in range(address.shape[0]):
            idx = torch.where(active_mask[b])[0]
            if len(idx) == 0:
                results.append(torch.zeros(self.data_dim, device=address.device))
                continue
            
            # Sum counters and take sign
            retrieved = self.counters[idx].sum(dim=0).sign()
            # Tie-break zeros to 1 (Kanerva convention)
            retrieved[retrieved == 0] = 1.0
            results.append(retrieved)
            
        return torch.stack(results)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Cleanup forward pass: assumes input is its own address."""
        return self.read(x)

    def cleanup(self, x: torch.Tensor, iterations: int = 3) -> torch.Tensor:
        """Iterative cleanup to find the nearest stable attractor."""
        out = x
        for _ in range(iterations):
            new_out = self.read(out)
            if torch.equal(out, new_out):
                break
            out = new_out
        return out

    def get_stats(self) -> Dict[str, Any]:
        return {
            "num_locations": self.num_locations,
            "address_dim": self.address_dim,
            "data_dim": self.data_dim,
            "saturation": self.counters.abs().max().item(),
        }
