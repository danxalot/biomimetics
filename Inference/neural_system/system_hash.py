import os
import subprocess
import logging
import numpy as np
from typing import Dict, Optional, List
import sys

# Import HDC tools with multiple fallback paths
_hdc_imported = False

# Try absolute import first (when running from project root)
try:
    from services.mcp_server.tools.hdc_memory import HDCEngine, AFLASHEncoder
    _hdc_imported = True
except ImportError:
    pass

# Try relative path resolution (for standalone/testing)
if not _hdc_imported:
    try:
        # Get the path relative to this file
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        _mcp_tools_path = os.path.join(_this_dir, '..', 'mcp_server', 'tools')
        if _mcp_tools_path not in sys.path:
            sys.path.insert(0, _mcp_tools_path)
        from hdc_memory import HDCEngine, AFLASHEncoder
        _hdc_imported = True
    except ImportError:
        pass

# Try local package import (for container deployment)
if not _hdc_imported:
    try:
        from .hdc_memory import HDCEngine, AFLASHEncoder
        _hdc_imported = True
    except ImportError:
        pass

if not _hdc_imported:
    raise ImportError("Could not import HDCEngine and AFLASHEncoder from hdc_memory")

logger = logging.getLogger(__name__)

class SystemHash:
    """
    Holographic GitOps Engine.
    Computes a 'System Hash Hypervector' representing the entire state of the codebase.
    Used to validate deployments mathematically.
    """
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = os.path.abspath(repo_path)
        self.hdc = HDCEngine(dimensionality=10000)
        self.encoder = AFLASHEncoder(self.hdc)
        
        # Axiom Vector (The "Constitution" of the System)
        # In a real system, this would be loaded from a secure genesis block.
        # Here we seed it deterministically.
        self.axiom_vector = self.hdc.bind(
            self.hdc.get_basis("AXIOM_SAFETY"),
            self.hdc.get_basis("AXIOM_STABILITY")
        )

    def _get_git_files(self) -> List[str]:
        """Get list of tracked files via git"""
        try:
            result = subprocess.run(
                ["git", "ls-files"], 
                cwd=self.repo_path, 
                capture_output=True, 
                text=True,
                check=True
            )
            return result.stdout.strip().split('\n')
        except subprocess.CalledProcessError:
            logger.warning("Not a git repository or git error. Falling back to os.walk.")
            files = []
            for root, _, filenames in os.walk(self.repo_path):
                if ".git" in root: continue
                for f in filenames:
                    files.append(os.path.join(root, f))
            return files

    def _get_file_hash(self, filepath: str) -> str:
        """Get git hash-object of a file (fast content hash)"""
        try:
             result = subprocess.run(
                ["git", "hash-object", filepath],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
             return result.stdout.strip()
        except:
            return "000000"

    def compute_repo_vector(self) -> np.ndarray:
        """
        Encodes the codebase structure into a single hypervector.
        V_Repo = Sum( V_Path_i * V_ContentHash_i )
        """
        files = self._get_git_files()
        
        repo_vector = np.zeros(self.hdc.D, dtype=np.float32)
        
        # We process a subset or simple encoding to be fast
        # (Full content encoding is slow, we use the Hash string as a proxy for content)
        
        count = 0
        for fpath in files:
            if not fpath: continue
            
            # 1. Path Vector
            v_path = self.encoder.encode_text(fpath) # Encode path struct
            
            # 2. Content Vector (from Hash)
            # We treat the SHA-1 string as a "concept"
            fhash = self._get_file_hash(fpath)
            v_hash = self.hdc.get_basis(fhash) # Deterministic vector from SHA string
            
            # 3. Bind Path * Content
            v_file = self.hdc.bind(v_path, v_hash)
            
            # 4. Superpose
            repo_vector += v_file
            count += 1
            
        # Bipolarize result
        return np.sign(repo_vector)

    def compute_system_vector(self) -> np.ndarray:
        """
        Computed Full System State.
        V_Sys = V_Repo + V_Env + V_Axiom
        """
        v_repo = self.compute_repo_vector()
        v_axiom = self.axiom_vector
        
        # Simple System Vector
        v_sys = self.hdc.bundle([v_repo, v_axiom])
        return v_sys

    def verify_alignment(self, v_proposed: np.ndarray, tolerance: float = 0.7) -> bool:
        """
        Holographic GitOps Check.
        Does the proposed system state align with the Axioms?
        
        Similarity(V_Proposed, V_Axiom) > Threshold?
        """
        # Note: In a real bundle, similarity to one component is ~1/sqrt(N)
        # So if V_Sys = V_Repo + V_Axiom (2 components), similarity to V_Axiom should be ~0.707
        
        sim = self.hdc.similarity(v_proposed, self.axiom_vector)
        logger.info(f"Axiom Alignment Score: {sim:.4f} (Threshold: {tolerance})")
        
        return sim >= tolerance
