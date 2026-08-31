"""
Pythia Isolated Databases

Manages Redis (trajectories) and Dragonfly (cache) on isolated network
"""

import redis
import json
import pickle
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import logging
import os
import time

logger = logging.getLogger(__name__)


class PythiaTrajectoryDB:
    """
    Redis database for Pythia's learned trajectories

    Stores training data from B1 and learned geometric trajectories
    Located on isolated network: localhost:6380
    """

    def __init__(self, host: str = "localhost", port: int = 6380):
        self.client = redis.Redis(
            host=host,
            port=port,
            db=0,
            decode_responses=False,  # Keep binary for pickle
        )
        self.vault_path = (
            "/Users/danexall/Documents/VS Code Projects/ARCA/arca_staging_vault"
        )

        # Ensure vault exists
        os.makedirs(self.vault_path, exist_ok=True)

        logger.info(f"Pythia Trajectory DB initialized: {host}:{port}")

    def load_b1_training_data(self) -> Dict[str, Any]:
        """Load B1 training data from arca_staging_vault"""
        b1_files = [
            "b1_trajectories.pkl",
            "b1_multivectors.pkl",
            "b1_hopfield_patterns.pkl",
        ]

        data = {}

        for filename in b1_files:
            filepath = os.path.join(self.vault_path, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "rb") as f:
                        data[filename.replace(".pkl", "")] = pickle.load(f)
                    logger.info(f"Loaded {filename}")
                except Exception as e:
                    logger.error(f"Error loading {filename}: {e}")
            else:
                logger.warning(f"File not found: {filename}")

        return data

    def store_trajectory(self, trajectory_id: str, trajectory: List[List[float]]):
        """Store a learned trajectory"""
        key = f"trajectory:{trajectory_id}"
        data = {
            "id": trajectory_id,
            "trajectory": trajectory,
            "timestamp": time.time(),
            "length": len(trajectory),
        }
        self.client.set(key, pickle.dumps(data))
        logger.info(f"Stored trajectory {trajectory_id} (length: {len(trajectory)})")

    def retrieve_trajectory(self, trajectory_id: str) -> Optional[List[List[float]]]:
        """Retrieve a trajectory by ID"""
        key = f"trajectory:{trajectory_id}"
        data = self.client.get(key)
        if data:
            parsed = pickle.loads(data)
            return parsed["trajectory"]
        return None

    def store_multivector_sequence(self, sequence_id: str, sequence: List[List[float]]):
        """Store a sequence of 32-dim multivectors"""
        key = f"multivector_seq:{sequence_id}"
        data = {"id": sequence_id, "sequence": sequence, "timestamp": time.time()}
        self.client.set(key, pickle.dumps(data))
        logger.info(f"Stored multivector sequence {sequence_id}")

    def store_hopfield_pattern(self, pattern_id: str, pattern: np.ndarray):
        """Store a Hopfield network pattern"""
        key = f"hopfield:{pattern_id}"
        data = {"id": pattern_id, "pattern": pattern, "timestamp": time.time()}
        self.client.set(key, pickle.dumps(data))
        logger.info(f"Stored Hopfield pattern {pattern_id}")

    def get_all_trajectories(self) -> Dict[str, List[List[float]]]:
        """Retrieve all stored trajectories"""
        trajectories = {}
        for key in self.client.scan_iter("trajectory:*"):
            data = self.client.get(key)
            if data:
                parsed = pickle.loads(data)
                trajectories[parsed["id"]] = parsed["trajectory"]
        return trajectories


class PythiaDragonflyDB:
    """
    Dragonfly database for Pythia's fast cache

    Stores 512-dim vectors and intermediate computations
    Located on isolated network: localhost:6381
    """

    def __init__(self, host: str = "localhost", port: int = 6381):
        self.client = redis.Redis(host=host, port=port, db=0, decode_responses=True)
        logger.info(f"Pythia Dragonfly DB initialized: {host}:{port}")

    def clear(self):
        """Clear all data in Dragonfly"""
        self.client.flushdb()
        logger.info("Dragonfly database cleared")

    def store_vector(
        self, key: str, vector: List[float], metadata: Optional[Dict] = None
    ):
        """Store a vector with metadata"""
        data = {"vector": vector, "metadata": metadata or {}, "timestamp": time.time()}
        self.client.set(key, json.dumps(data))
        logger.info(f"Stored vector: {key}")

    def retrieve_vector(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a vector"""
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None

    def batch_store(self, vectors: Dict[str, List[float]]):
        """Batch store multiple vectors"""
        pipeline = self.client.pipeline()
        for key, vector in vectors.items():
            data = {"vector": vector, "timestamp": time.time()}
            pipeline.set(key, json.dumps(data))
        pipeline.execute()
        logger.info(f"Batch stored {len(vectors)} vectors")


# Global instances
_trajectory_db: Optional[PythiaTrajectoryDB] = None
_dragonfly_db: Optional[PythiaDragonflyDB] = None


def get_trajectory_db() -> PythiaTrajectoryDB:
    """Get or create trajectory DB singleton"""
    global _trajectory_db
    if _trajectory_db is None:
        _trajectory_db = PythiaTrajectoryDB()
    return _trajectory_db


def get_dragonfly_db() -> PythiaDragonflyDB:
    """Get or create Dragonfly DB singleton"""
    global _dragonfly_db
    if _dragonfly_db is None:
        _dragonfly_db = PythiaDragonflyDB()
    return _dragonfly_db


def load_b1_training_data() -> Dict[str, Any]:
    """Convenience function to load B1 training data"""
    db = get_trajectory_db()
    return db.load_b1_training_data()


def clear_pythia_databases():
    """Clear both Pythia databases"""
    dragonfly = get_dragonfly_db()
    dragonfly.clear()

    # Redis doesn't have a simple flush in this context, but we can clear keys
    trajectory_db = get_trajectory_db()
    # Clear all trajectory keys
    for key in trajectory_db.client.scan_iter("trajectory:*"):
        trajectory_db.client.delete(key)
    for key in trajectory_db.client.scan_iter("multivector_seq:*"):
        trajectory_db.client.delete(key)
    for key in trajectory_db.client.scan_iter("hopfield:*"):
        trajectory_db.client.delete(key)

    logger.info("Both Pythia databases cleared")
