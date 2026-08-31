
import redis
import numpy as np
import json
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class DragonflyClient:
    def __init__(self, host: str = "localhost", port: int = 6379):
        self.client = redis.Redis(host=host, port=port, decode_responses=True)
        self.index_name = "idx:concept"

    def create_index(self, dimension: int):
        """Create the vector search index in Dragonfly."""
        try:
            # Check if index exists
            self.client.execute_command("FT.INFO", self.index_name)
            logger.info("Index already exists.")
        except redis.exceptions.ResponseError:
            # Create Index
            # SCHEMA: concept_id TEXT, type TEXT, mass NUMERIC, vector VECTOR
            logger.info(f"Creating index {self.index_name}...")
            self.client.execute_command(
                "FT.CREATE", self.index_name,
                "ON", "HASH",
                "PREFIX", "1", "concept:",
                "SCHEMA",
                "concept_id", "TEXT",
                "type", "TAG",
                "mass", "NUMERIC",
                "vector", "VECTOR", "FLAT", "6",
                "TYPE", "FLOAT32",
                "DIM", str(dimension),
                "DISTANCE_METRIC", "COSINE"
            )

    def add_concept(self, concept_id: str, vector: List[float], metadata: Dict):
        """Add a concept to Dragonfly."""
        key = f"concept:{concept_id}"
        
        # Convert vector to bytes
        vector_bytes = np.array(vector, dtype=np.float32).tobytes()
        
        mapping = {
            "concept_id": concept_id,
            "vector": vector_bytes,
            "json_data": json.dumps(metadata) # Complete metadata as JSON blob
        }
        
        # Add basic searchable fields from metadata if they exist
        if "type" in metadata:
            mapping["type"] = metadata["type"]
        if "mass" in metadata:
            mapping["mass"] = metadata["mass"]

        self.client.hset(key, mapping=mapping)

    def search(self, query_vector: List[float], top_k: int = 10):
        """Search for similar concepts."""
        query_bytes = np.array(query_vector, dtype=np.float32).tobytes()
        
        # K-NN Query
        q = f"*=>[KNN {top_k} @vector $vec AS score]"
        
        res = self.client.execute_command(
            "FT.SEARCH", self.index_name,
            q,
            "PARAMS", "2", "vec", query_bytes,
            "DIALECT", "2"
        )
        return res
