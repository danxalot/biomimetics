"""
Dimensional Truncation (2048-dim → 512-dim)

Part of Stage 1: Exoteric Knowledge Graph Pipeline
Uses PCA or learned projection to compress vectors while preserving structure
"""

import numpy as np
from typing import List, Optional
import logging
import pickle
import os

logger = logging.getLogger(__name__)


class DimensionalTruncator:
    """Compress 2048-dim vectors to 512-dim using PCA or learned projection"""

    def __init__(self, target_dim: int = 512, method: str = "pca"):
        self.target_dim = target_dim
        self.method = method
        self.pca: Optional[np.ndarray] = None
        self.mean: Optional[np.ndarray] = None
        self.is_fitted = False

        # Storage for fitted PCA matrix
        self.pca_matrix_path = "/tmp/arca_pca_matrix.pkl"

    def fit(self, vectors_2048: np.ndarray):
        """
        Fit PCA on training data (2048-dim → 512-dim)

        Args:
            vectors_2048: Shape (n_samples, 2048)
        """
        if self.method == "pca":
            logger.info(f"Fitting PCA: {vectors_2048.shape} → {self.target_dim}")

            # Center data
            self.mean = np.mean(vectors_2048, axis=0)
            centered = vectors_2048 - self.mean

            # Compute covariance matrix
            cov_matrix = np.cov(centered.T)

            # Compute top eigenvectors (power iteration for efficiency)
            eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)

            # Sort by eigenvalue (descending)
            idx = np.argsort(eigenvalues)[::-1]
            eigenvectors = eigenvectors[:, idx]

            # Keep top k components
            self.pca = eigenvectors[:, : self.target_dim]
            self.is_fitted = True

            # Save PCA matrix
            self.save_pca_matrix()

            logger.info(
                f"PCA fitted. Explained variance: {np.sum(eigenvalues[: self.target_dim]) / np.sum(eigenvalues):.3f}"
            )
        else:
            raise ValueError(f"Unknown method: {self.method}")

    def transform(self, vectors_2048: np.ndarray) -> np.ndarray:
        """Transform 2048-dim vectors to 512-dim"""
        if not self.is_fitted:
            # Use identity projection if not fitted (first 512 dimensions)
            logger.warning(
                "Truncator not fitted, using identity projection (first 512 dims)"
            )
            return vectors_2048[:, :512]

        # Center and project
        centered = vectors_2048 - self.mean
        return centered @ self.pca

    def transform_single(self, vector_2048: List[float]) -> List[float]:
        """Transform single 2048-dim vector to 512-dim"""
        vector_array = np.array(vector_2048).reshape(1, -1)
        result = self.transform(vector_array)
        return result.flatten().tolist()

    def save_pca_matrix(self):
        """Save fitted PCA matrix to disk"""
        data = {
            "pca": self.pca,
            "mean": self.mean,
            "target_dim": self.target_dim,
            "method": self.method,
        }
        with open(self.pca_matrix_path, "wb") as f:
            pickle.dump(data, f)
        logger.info(f"Saved PCA matrix to {self.pca_matrix_path}")

    def load_pca_matrix(self):
        """Load fitted PCA matrix from disk"""
        if os.path.exists(self.pca_matrix_path):
            with open(self.pca_matrix_path, "rb") as f:
                data = pickle.load(f)
            self.pca = data["pca"]
            self.mean = data["mean"]
            self.target_dim = data["target_dim"]
            self.method = data["method"]
            self.is_fitted = True
            logger.info(f"Loaded PCA matrix from {self.pca_matrix_path}")
        else:
            logger.warning(f"PCA matrix not found at {self.pca_matrix_path}")


# Singleton instance
_truncator: Optional[DimensionalTruncator] = None


def get_truncator() -> DimensionalTruncator:
    """Get or create dimensional truncator singleton"""
    global _truncator
    if _truncator is None:
        _truncator = DimensionalTruncator(target_dim=512, method="pca")
        _truncator.load_pca_matrix()
    return _truncator


def truncate_vector_2048_to_512(vector_2048: List[float]) -> List[float]:
    """Convenience function to truncate a single vector"""
    truncator = get_truncator()
    return truncator.transform_single(vector_2048)


def batch_truncate_vectors(vectors_2048: np.ndarray) -> np.ndarray:
    """Batch truncate multiple vectors"""
    truncator = get_truncator()
    return truncator.transform(vectors_2048)
