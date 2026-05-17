"""HDC Infinite and Long-Term Memory Systems.

PyTorch port of `services/neural_system/hdc_infini_memory.py`.
Implements holographic memory systems for context preservation and episodic recall.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, List, Dict, Any, Tuple


class HDCInfiniMemory(nn.Module):
    """
    Infini-attention style memory using HDC bundling.
    Maintains a single fixed-width hypervector that holographically accumulates context.
    """
    
    def __init__(self, hv_dim: int = 4096, decay_rate: float = 0.99):
        super().__init__()
        self.hv_dim = hv_dim
        self.decay_rate = decay_rate
        
        # Memory state
        self.register_buffer("memory_hv", torch.zeros(hv_dim))
        self.register_buffer("position", torch.tensor(0, dtype=torch.long))
        self.register_buffer("initialized", torch.tensor(False))

    def update(self, x: torch.Tensor, importance: float = 1.0):
        """Bundle new content into the memory."""
        # x: [hv_dim]
        # 1. Apply temporal permutation (roll)
        positioned = torch.roll(x, shifts=self.position.item())
        
        if not self.initialized:
            self.memory_hv = positioned * importance
            self.initialized = torch.tensor(True)
        else:
            # 2. Decay and superimpose
            self.memory_hv = self.memory_hv * self.decay_rate + positioned * importance
            
        self.position += 1
        return self.memory_hv

    def query(self, q: torch.Tensor) -> torch.Tensor:
        """Measure resonance between query and memory."""
        # q: [..., hv_dim]
        return F.cosine_similarity(q, self.memory_hv.unsqueeze(0), dim=-1)

    def retrieve_at_position(self, pos: int) -> torch.Tensor:
        """Retrieve (noisy) content from a specific temporal position."""
        # Inverse permutation
        return torch.roll(self.memory_hv, shifts=-pos)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass for training: return memory-augmented state."""
        # For training, we might return the memory resonance as a feature
        resonance = self.query(x).unsqueeze(-1) # [..., 1]
        return resonance


class HDCLongMemory(nn.Module):
    """
    Episodic memory bank for storing and retrieving high-dimensional states.
    """
    
    def __init__(self, hv_dim: int = 4096, capacity: int = 10000):
        super().__init__()
        self.hv_dim = hv_dim
        self.capacity = capacity
        
        self.register_buffer("keys", torch.zeros(capacity, hv_dim))
        self.register_buffer("timestamps", torch.zeros(capacity))
        self.register_buffer("pointer", torch.tensor(0, dtype=torch.long))
        self.register_buffer("count", torch.tensor(0, dtype=torch.long))
        
        # Values can't always be tensors, but for this archive we'll assume they are
        self.register_buffer("values", torch.zeros(capacity, hv_dim))

    def store(self, key: torch.Tensor, value: torch.Tensor):
        """Store a (key, value) pair."""
        idx = self.pointer.item()
        self.keys[idx] = key
        self.values[idx] = value
        self.timestamps[idx] = torch.tensor(0.0) # Placeholder for actual time if needed
        
        self.pointer = (self.pointer + 1) % self.capacity
        if self.count < self.capacity:
            self.count += 1

    def retrieve(self, query: torch.Tensor, top_k: int = 5) -> Tuple[torch.Tensor, torch.Tensor]:
        """Retrieve top-k values based on cosine similarity."""
        if self.count == 0:
            return torch.zeros(top_k, self.hv_dim), torch.zeros(top_k)
            
        # [capacity, hv_dim] @ [hv_dim, 1] -> [capacity]
        sim = F.cosine_similarity(query.unsqueeze(0), self.keys[:self.count], dim=-1)
        
        scores, indices = torch.topk(sim, min(top_k, self.count.item()))
        return self.values[indices], scores

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass: retrieve and bundle."""
        vals, scores = self.retrieve(x, top_k=5)
        # Weighted sum of retrieved memories
        return torch.sum(vals * scores.unsqueeze(-1), dim=0)
