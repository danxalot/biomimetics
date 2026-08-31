"""
OCI Skill Bank Client: Interface to Oracle 26ai and FAISS.

Implements the "Tiered Memory" architecture:
- Tier 1 (Hot): FAISS binary index in RAM for instant lookup
- Tier 2 (Cold): Oracle 26ai for persistence and graph queries

Optimized for OCI ARM (4xA1 Ampere) with NEON instructions.
"""

import os
import json
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# FAISS import (optional for local-only mode)
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS not available - skill bank will use Oracle only")

# Oracle import (optional)
try:
    import oracledb
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    logger.warning("oracledb not available - skill bank will use FAISS only")


@dataclass
class SkillEntry:
    """A skill stored in the bank."""
    skill_id: str
    concept_name: str
    concept_type: str  # skill, concept, attractor, reflex
    state_vector: np.ndarray
    logic_payload: dict
    energy_level: float = 0.5
    uncertainty: float = 0.5
    hit_count: int = 0


class OCISkillBank:
    """
    Tiered skill bank with FAISS (hot) and Oracle 26ai (cold).
    
    Architecture:
    - FAISS IndexBinary for instant lookup (nanoseconds)
    - Oracle 26ai for persistence and graph queries
    - Sync on startup and periodic flush
    """
    
    def __init__(
        self,
        wallet_dir: Optional[str] = None,
        dsn: str = "arcadb_low",
        user: str = "ADMIN",
        password: Optional[str] = None,
        hdc_dim: int = 1024,
        use_binary: bool = True,
    ):
        """
        Initialize skill bank.
        
        Args:
            wallet_dir: Path to Oracle wallet directory
            dsn: TNS name (arcadb_low, arcadb_high, etc.)
            user: Database user
            password: Database password (or from env)
            hdc_dim: HDC vector dimension
            use_binary: Use binary FAISS index (faster) vs float
        """
        self.hdc_dim = hdc_dim
        self.use_binary = use_binary
        self.payloads: Dict[int, SkillEntry] = {}  # FAISS index → SkillEntry
        
        # Initialize FAISS index
        if FAISS_AVAILABLE:
            if use_binary:
                # Binary index for HDR vectors (Hamming distance)
                self.index = faiss.IndexBinaryFlat(hdc_dim)
            else:
                # Float index for HRR vectors (cosine/L2)
                self.index = faiss.IndexFlatL2(hdc_dim)
            logger.info(f"FAISS index initialized: dim={hdc_dim}, binary={use_binary}")
        else:
            self.index = None
        
        # Initialize Oracle connection
        self.oracle_conn = None
        if ORACLE_AVAILABLE and wallet_dir:
            try:
                oracledb.init_oracle_client(config_dir=wallet_dir)
                self.oracle_conn = oracledb.connect(
                    user=user,
                    password=password or os.environ.get("DB_ADMIN_PASSWORD"),
                    dsn=dsn,
                    wallet_location=wallet_dir,
                    wallet_password=os.environ.get("WALLET_PASSWORD"),
                )
                logger.info(f"Oracle 26ai connected: {dsn}")
            except Exception as e:
                logger.warning(f"Oracle connection failed: {e}")
        
        self._next_id = 0
    
    def load_from_oracle(self):
        """Load all skills from Oracle into FAISS (startup)."""
        if not self.oracle_conn or not self.index:
            return
        
        try:
            cursor = self.oracle_conn.cursor()
            cursor.execute("""
                SELECT skill_id, concept_name, concept_type, state_vector,
                       logic_payload, energy_level, uncertainty, hit_count
                FROM skill_bank
            """)
            
            vectors = []
            for row in cursor:
                skill_id, name, ctype, vec_blob, payload, energy, unc, hits = row
                
                # Convert BLOB to numpy
                if vec_blob:
                    vector = np.frombuffer(vec_blob.read(), dtype=np.int8 if self.use_binary else np.float32)
                else:
                    continue
                
                entry = SkillEntry(
                    skill_id=skill_id.hex() if isinstance(skill_id, bytes) else str(skill_id),
                    concept_name=name,
                    concept_type=ctype,
                    state_vector=vector,
                    logic_payload=json.loads(payload) if payload else {},
                    energy_level=float(energy),
                    uncertainty=float(unc),
                    hit_count=int(hits),
                )
                
                self.payloads[self._next_id] = entry
                vectors.append(vector)
                self._next_id += 1
            
            if vectors:
                if self.use_binary:
                    # Pack to uint8 for binary FAISS
                    packed = np.array(vectors, dtype=np.uint8)
                    self.index.add(np.packbits(packed, axis=1))
                else:
                    self.index.add(np.array(vectors, dtype=np.float32))
                
                logger.info(f"Loaded {len(vectors)} skills from Oracle into FAISS")
            
        except Exception as e:
            logger.error(f"Failed to load from Oracle: {e}")
    
    def search(
        self,
        query_vector: np.ndarray,
        k: int = 1,
        threshold: float = 0.2,
    ) -> List[Tuple[SkillEntry, float]]:
        """
        Search for similar skills.
        
        Args:
            query_vector: Query HDC vector
            k: Number of results
            threshold: Maximum distance threshold (0-1 normalized)
            
        Returns:
            List of (SkillEntry, distance) tuples
        """
        if not self.index or self.index.ntotal == 0:
            return []
        
        try:
            if self.use_binary:
                # Pack query for binary search
                packed = np.packbits(query_vector.astype(np.uint8)).reshape(1, -1)
                D, I = self.index.search(packed, k)
            else:
                query = query_vector.astype(np.float32).reshape(1, -1)
                D, I = self.index.search(query, k)
            
            results = []
            for i, (dist, idx) in enumerate(zip(D[0], I[0])):
                if idx >= 0 and idx in self.payloads:
                    # Normalize distance
                    norm_dist = dist / self.hdc_dim if self.use_binary else dist
                    if norm_dist <= threshold:
                        results.append((self.payloads[idx], norm_dist))
            
            return results
            
        except Exception as e:
            logger.error(f"FAISS search failed: {e}")
            return []
    
    def add_skill(self, entry: SkillEntry) -> bool:
        """
        Add a skill to both FAISS and Oracle.
        
        Args:
            entry: SkillEntry to add
            
        Returns:
            True if successful
        """
        try:
            # Add to FAISS
            if self.index:
                if self.use_binary:
                    packed = np.packbits(entry.state_vector.astype(np.uint8)).reshape(1, -1)
                    self.index.add(packed)
                else:
                    self.index.add(entry.state_vector.astype(np.float32).reshape(1, -1))
                
                self.payloads[self._next_id] = entry
                self._next_id += 1
            
            # Add to Oracle
            if self.oracle_conn:
                cursor = self.oracle_conn.cursor()
                cursor.execute("""
                    INSERT INTO skill_bank 
                    (concept_name, concept_type, state_vector, logic_payload, energy_level, uncertainty)
                    VALUES (:1, :2, :3, :4, :5, :6)
                """, (
                    entry.concept_name,
                    entry.concept_type,
                    entry.state_vector.tobytes(),
                    json.dumps(entry.logic_payload),
                    entry.energy_level,
                    entry.uncertainty,
                ))
                self.oracle_conn.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add skill: {e}")
            return False
    
    def get_reflex(self, query_vector: np.ndarray) -> Optional[dict]:
        """
        Fast reflex lookup - returns action if exact match found.
        
        Args:
            query_vector: Query HDC vector
            
        Returns:
            logic_payload if match found, None otherwise
        """
        results = self.search(query_vector, k=1, threshold=0.1)
        if results:
            entry, dist = results[0]
            if entry.concept_type == "reflex":
                entry.hit_count += 1
                return entry.logic_payload
        return None
    
    def find_attractor(self, query_vector: np.ndarray) -> Optional[Tuple[SkillEntry, float]]:
        """
        Find nearest attractor state (stable/healthy configuration).
        
        Args:
            query_vector: Current state vector
            
        Returns:
            (attractor_entry, distance) or None
        """
        if not self.oracle_conn:
            # FAISS-only: search all
            return self.search(query_vector, k=1)[0] if self.search(query_vector, k=1) else None
        
        # Use Oracle to filter attractors, then FAISS for distance
        try:
            cursor = self.oracle_conn.cursor()
            cursor.execute("""
                SELECT skill_id, concept_name, state_vector
                FROM skill_bank
                WHERE concept_type = 'attractor'
            """)
            
            best_match = None
            best_dist = float('inf')
            
            for row in cursor:
                skill_id, name, vec_blob = row
                if vec_blob:
                    vec = np.frombuffer(vec_blob.read(), dtype=np.int8)
                    dist = np.sum(query_vector != vec) / len(vec)  # Hamming
                    if dist < best_dist:
                        best_dist = dist
                        best_match = SkillEntry(
                            skill_id=str(skill_id),
                            concept_name=name,
                            concept_type="attractor",
                            state_vector=vec,
                            logic_payload={},
                        )
            
            return (best_match, best_dist) if best_match else None
            
        except Exception as e:
            logger.error(f"Attractor search failed: {e}")
            return None
    
    def get_state(self) -> dict:
        """Get current skill bank state."""
        return {
            "faiss_available": FAISS_AVAILABLE,
            "oracle_available": ORACLE_AVAILABLE,
            "faiss_size": self.index.ntotal if self.index else 0,
            "payload_count": len(self.payloads),
            "oracle_connected": self.oracle_conn is not None,
            "hdc_dim": self.hdc_dim,
            "use_binary": self.use_binary,
        }
    
    def close(self):
        """Clean up connections."""
        if self.oracle_conn:
            self.oracle_conn.close()
