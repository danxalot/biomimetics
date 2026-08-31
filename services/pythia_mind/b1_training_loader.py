"""
B1 Training Data Loader

Loads B1 training data and populates Pythia's Redis and Dragonfly databases
"""

import pickle
import numpy as np
from typing import Dict, List, Any, Optional
import logging
import os
import time

logger = logging.getLogger(__name__)


class B1TrainingLoader:
    """
    Load B1 training data and populate Pythia databases

    B1 training data includes:
    - Geometric trajectories
    - Multivector sequences
    - Hopfield network patterns
    - Training metadata
    """

    def __init__(self, vault_path: str):
        self.vault_path = vault_path
        self.trajectory_db = None
        self.dragonfly_db = None

        # Import after to avoid circular imports
        from pythia_databases import get_trajectory_db, get_dragonfly_db

        self.trajectory_db = get_trajectory_db()
        self.dragonfly_db = get_dragonfly_db()

        logger.info(f"B1 Training Loader initialized: {vault_path}")

    def load_all_data(self) -> Dict[str, Any]:
        """Load all B1 training data from vault"""
        data = {}

        # List of expected B1 data files
        b1_files = {
            "trajectories": "b1_trajectories.pkl",
            "multivectors": "b1_multivectors.pkl",
            "hopfield_patterns": "b1_hopfield_patterns.pkl",
            "training_metadata": "b1_training_metadata.pkl",
            "conformal_data": "b1_conformal_data.pkl",
            "bridge_mappings": "b1_bridge_mappings.pkl",
        }

        for key, filename in b1_files.items():
            filepath = os.path.join(self.vault_path, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "rb") as f:
                        data[key] = pickle.load(f)
                    logger.info(f"✓ Loaded {filename}")
                except Exception as e:
                    logger.error(f"✗ Error loading {filename}: {e}")
            else:
                logger.warning(f"⚠ File not found: {filename}")

        return data

    def populate_databases(self, b1_data: Dict[str, Any]):
        """Populate Redis and Dragonfly with B1 data"""
        logger.info("Populating Pythia databases with B1 training data...")

        # 1. Store trajectories in Redis
        if "trajectories" in b1_data:
            trajectories = b1_data["trajectories"]
            for i, traj in enumerate(trajectories):
                traj_id = f"b1_traj_{i:04d}"
                self.trajectory_db.store_trajectory(traj_id, traj)
            logger.info(f"✓ Stored {len(trajectories)} trajectories in Redis")

        # 2. Store multivector sequences
        if "multivectors" in b1_data:
            multivectors = b1_data["multivectors"]
            for i, seq in enumerate(multivectors):
                seq_id = f"b1_seq_{i:04d}"
                self.trajectory_db.store_multivector_sequence(seq_id, seq)
            logger.info(f"✓ Stored {len(multivectors)} multivector sequences")

        # 3. Store Hopfield patterns
        if "hopfield_patterns" in b1_data:
            patterns = b1_data["hopfield_patterns"]
            for i, pattern in enumerate(patterns):
                pattern_id = f"b1_hopfield_{i:04d}"
                self.trajectory_db.store_hopfield_pattern(pattern_id, pattern)
            logger.info(f"✓ Stored {len(patterns)} Hopfield patterns")

        # 4. Store conformal data in Dragonfly
        if "conformal_data" in b1_data:
            conformal = b1_data["conformal_data"]
            for key, value in conformal.items():
                dragonfly_key = f"conformal:{key}"
                if isinstance(value, np.ndarray):
                    value = value.tolist()
                self.dragonfly_db.store_vector(dragonfly_key, value)
            logger.info(f"✓ Stored {len(conformal)} conformal parameters")

        # 5. Store bridge mappings
        if "bridge_mappings" in b1_data:
            bridges = b1_data["bridge_mappings"]
            for key, value in bridges.items():
                dragonfly_key = f"bridge:{key}"
                if isinstance(value, np.ndarray):
                    value = value.tolist()
                self.dragonfly_db.store_vector(dragonfly_key, value)
            logger.info(f"✓ Stored {len(bridges)} bridge mappings")

        logger.info("✅ B1 data population complete!")

    def generate_sample_b1_data(self) -> Dict[str, Any]:
        """Generate sample B1 data if files don't exist"""
        logger.info("Generating sample B1 training data...")

        # Generate sample trajectories (50 trajectories, 100 steps each, 32-dim)
        trajectories = []
        for _ in range(50):
            traj = []
            for step in range(100):
                # Simulate geometric motion
                t = step / 100.0
                point = [
                    np.sin(t * 2 * np.pi),
                    np.cos(t * 2 * np.pi),
                    t,
                    *[0.0] * 29,  # Pad to 32 dims
                ]
                traj.append(point)
            trajectories.append(traj)

        # Generate sample multivector sequences
        multivectors = []
        for _ in range(30):
            seq = []
            for step in range(50):
                mv = np.random.randn(32) * 0.1
                seq.append(mv.tolist())
            multivectors.append(seq)

        # Generate Hopfield patterns
        hopfield_patterns = []
        for _ in range(20):
            pattern = np.random.choice([-1, 1], size=128)
            hopfield_patterns.append(pattern)

        # Generate conformal data
        conformal_data = {
            "basis_vectors": np.eye(5).tolist(),
            "projection_matrix": np.random.randn(512, 32).tolist(),
            "normalization_params": {"mean": 0.0, "std": 1.0},
        }

        # Generate bridge mappings
        bridge_mappings = {
            "hdc_to_dense_weights": np.random.randn(10000, 2048).tolist(),
            "dense_to_hdc_weights": np.random.randn(2048, 10000).tolist(),
            "cycle_consistency_params": {"lambda": 1.0, "lr": 0.001},
        }

        b1_data = {
            "trajectories": trajectories,
            "multivectors": multivectors,
            "hopfield_patterns": hopfield_patterns,
            "training_metadata": {
                "version": "B1",
                "created": time.time(),
                "num_trajectories": len(trajectories),
                "num_multivectors": len(multivectors),
                "num_hopfield_patterns": len(hopfield_patterns),
            },
            "conformal_data": conformal_data,
            "bridge_mappings": bridge_mappings,
        }

        # Save to vault
        self._save_b1_data(b1_data)

        logger.info(f"✓ Generated sample B1 data:")
        logger.info(f"  - {len(trajectories)} trajectories")
        logger.info(f"  - {len(multivectors)} multivector sequences")
        logger.info(f"  - {len(hopfield_patterns)} Hopfield patterns")

        return b1_data

    def _save_b1_data(self, b1_data: Dict[str, Any]):
        """Save B1 data to vault"""
        os.makedirs(self.vault_path, exist_ok=True)

        for key, data in b1_data.items():
            if key != "training_metadata":  # Don't save metadata as pickle
                filename = f"b1_{key}.pkl"
                filepath = os.path.join(self.vault_path, filename)
                with open(filepath, "wb") as f:
                    pickle.dump(data, f)
                logger.info(f"Saved {filename}")


def load_and_populate_b1_data():
    """Main function to load B1 data and populate databases"""
    vault_path = "/Users/danexall/Documents/VS Code Projects/ARCA/arca_staging_vault"

    loader = B1TrainingLoader(vault_path)

    # Try to load existing data
    b1_data = loader.load_all_data()

    # If no data exists, generate sample data
    if not b1_data:
        logger.info("No B1 data found, generating sample data...")
        b1_data = loader.generate_sample_b1_data()

    # Populate databases
    loader.populate_databases(b1_data)

    return b1_data
