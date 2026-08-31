#!/usr/bin/env python3
"""
MuninnDB Server - Hebbian Learning & ACT-R Memory System

This server implements:
- Engram storage with temporal decay
- Hebbian learning ("neurons that fire together, wire together")
- ACT-R cognitive architecture for memory retrieval
- MCP server interface for 24/7 access
"""

import os
import json
import asyncio
import time
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import aiohttp
from google.cloud import pubsub_v1

# Configuration
@dataclass
class MuninnConfig:
    instance_id: str = "muninn-default"
    storage_path: str = "./data"
    
    # Pub/Sub configuration
    pubsub_project_id: str = "arca-471022"
    pubsub_subscription_id: str = "muninn-global-events"
    
    # Hebbian learning parameters
    hebbian_learning_rate: float = 0.1
    hebbian_decay_rate: float = 0.01  # per hour
    hebbian_retrieval_threshold: float = 0.3
    hebbian_max_connections: int = 100
    hebbian_coactivation_window: float = 300  # seconds
    hebbian_reinforcement_multiplier: float = 1.5
    
    # ACT-R parameters
    act_r_decay_rate: float = 0.5
    act_r_retrieval_threshold: float = 0.3
    act_r_associative_strength: float = 2.0
    act_r_source_activation: float = 0.5
    act_r_mismatch_penalty: float = 0.5
    
    # MCP server
    mcp_port: int = 8097
    mcp_host: str = "0.0.0.0"


@dataclass
class Engram:
    """A single memory unit"""
    id: str
    type: str
    timestamp: str
    content: Dict[str, Any]
    activation: float = 1.0
    last_accessed: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    access_count: int = 0
    connections: Dict[str, float] = field(default_factory=dict)  # engram_id -> strength
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


class MuninnDB:
    """Hebbian learning memory database"""
    
    def __init__(self, config: MuninnConfig):
        self.config = config
        self.storage_path = Path(config.storage_path)
        self.engrams: Dict[str, Engram] = {}
        self._load()
    
    def _load(self):
        """Load engrams from disk"""
        engrams_file = self.storage_path / "engrams.json"
        if engrams_file.exists():
            with open(engrams_file, "r") as f:
                data = json.load(f)
                self.engrams = {
                    k: Engram.from_dict(v) for k, v in data.items()
                }
            print(f"✅ Loaded {len(self.engrams)} engrams")
    
    def _save(self):
        """Save engrams to disk"""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        engrams_file = self.storage_path / "engrams.json"
        with open(engrams_file, "w") as f:
            json.dump(
                {k: v.to_dict() for k, v in self.engrams.items()},
                f,
                indent=2
            )
    
    def add_engram(self, engram: Engram):
        """Add a new engram"""
        self.engrams[engram.id] = engram
        self._save()
        
        # Apply Hebbian learning: connect to recently accessed engrams
        self._apply_hebbian_learning(engram)
    
    def _apply_hebbian_learning(self, new_engram: Engram):
        """
        Hebbian Learning: "Neurons that fire together, wire together"
        
        Connect new engram to recently accessed engrams within time window
        """
        now = datetime.utcnow()
        window = timedelta(seconds=self.config.hebbian_coactivation_window)
        
        # Find recently accessed engrams
        recent_engrams = []
        for engram_id, engram in self.engrams.items():
            if engram_id == new_engram.id:
                continue
            
            last_accessed = datetime.fromisoformat(engram.last_accessed)
            if now - last_accessed <= window:
                recent_engrams.append(engram)
        
        # Create connections
        for recent in recent_engrams[:self.config.hebbian_max_connections]:
            # Strengthen connection
            connection_strength = self.config.hebbian_learning_rate
            
            # Bidirectional connection
            new_engram.connections[recent.id] = (
                new_engram.connections.get(recent.id, 0) + connection_strength
            )
            recent.connections[new_engram.id] = (
                recent.connections.get(new_engram.id, 0) + connection_strength
            )
        
        self._save()
    
    def retrieve_engram(self, engram_id: str) -> Optional[Engram]:
        """Retrieve an engram by ID"""
        engram = self.engrams.get(engram_id)
        if engram:
            # Update access statistics
            engram.access_count += 1
            engram.last_accessed = datetime.utcnow().isoformat()
            
            # Reinforce activation
            engram.activation = min(
                1.0,
                engram.activation * self.config.hebbian_reinforcement_multiplier
            )
            
            self._save()
        
        return engram
    
    def search_by_relevance(self, query: str = None, limit: int = 10) -> List[Engram]:
        """
        Search engrams by relevance using ACT-R activation
        
        Activation = Base Level + Associative Activation
        """
        now = datetime.utcnow()
        scored_engrams = []
        
        for engram in self.engrams.values():
            # Base level activation (time decay)
            last_accessed = datetime.fromisoformat(engram.last_accessed)
            time_diff_hours = (now - last_accessed).total_seconds() / 3600
            
            # ACT-R base level equation: B = ln(t / d) where t is time, d is decay
            base_activation = math.log(
                (time_diff_hours + 1) ** (-self.config.act_r_decay_rate)
            )
            
            # Associative activation from connected engrams
            associative_activation = 0
            for connected_id, strength in engram.connections.items():
                connected_engram = self.engrams.get(connected_id)
                if connected_engram:
                    associative_activation += (
                        strength * connected_engram.activation
                    )
            
            associative_activation = min(
                self.config.act_r_associative_strength,
                associative_activation
            )
            
            # Total activation
            total_activation = (
                base_activation +
                self.config.act_r_source_activation +
                associative_activation
            )
            
            # Apply decay over time
            engram.activation = max(0, engram.activation - (
                time_diff_hours * self.config.hebbian_decay_rate
            ))
            
            scored_engrams.append((total_activation, engram))
        
        # Sort by activation and return top results
        scored_engrams.sort(key=lambda x: x[0], reverse=True)
        
        return [
            engram for _, engram in scored_engrams[:limit]
            if engram.activation >= self.config.hebbian_retrieval_threshold
        ]
    
    def apply_decay(self):
        """Apply temporal decay to all engrams (run periodically)"""
        now = datetime.utcnow()
        
        for engram in self.engrams.values():
            last_accessed = datetime.fromisoformat(engram.last_accessed)
            time_diff_hours = (now - last_accessed).total_seconds() / 3600
            
            # Decay activation
            engram.activation = max(0, engram.activation - (
                time_diff_hours * self.config.hebbian_decay_rate
            ))
        
        # Remove engrams with zero activation (forgotten)
        self.engrams = {
            k: v for k, v in self.engrams.items()
            if v.activation > 0
        }
        
        self._save()


# FastAPI App
app = FastAPI(title="MuninnDB", version="1.0.0")
config = MuninnConfig()
db = MuninnDB(config)


class EngramCreate(BaseModel):
    type: str
    content: Dict[str, Any]
    metadata: Dict[str, Any] = {}


@app.post("/engrams")
async def create_engram(engram_data: EngramCreate):
    """Create a new engram"""
    import uuid
    
    engram = Engram(
        id=str(uuid.uuid4()),
        type=engram_data.type,
        timestamp=datetime.utcnow().isoformat(),
        content=engram_data.content,
        metadata=engram_data.metadata,
    )
    
    db.add_engram(engram)
    
    return {"id": engram.id, "status": "created"}


@app.get("/engrams/{engram_id}")
async def get_engram(engram_id: str):
    """Retrieve an engram by ID"""
    engram = db.retrieve_engram(engram_id)
    
    if not engram:
        raise HTTPException(status_code=404, detail="Engram not found")
    
    return engram.to_dict()


@app.get("/engrams")
async def search_engrams(q: str = None, limit: int = 10):
    """Search engrams by relevance"""
    results = db.search_by_relevance(query=q, limit=limit)
    
    return [r.to_dict() for r in results]


@app.post("/apply-decay")
async def apply_decay():
    """Manually trigger decay (for testing)"""
    db.apply_decay()
    return {"status": "decay applied"}


@app.get("/stats")
async def get_stats():
    """Get memory statistics"""
    return {
        "total_engrams": len(db.engrams),
        "active_engrams": sum(
            1 for e in db.engrams.values()
            if e.activation >= config.hebbian_retrieval_threshold
        ),
        "forgotten_engrams": sum(
            1 for e in db.engrams.values()
            if e.activation < config.hebbian_retrieval_threshold
        ),
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=config.mcp_host,
        port=config.mcp_port
    )
