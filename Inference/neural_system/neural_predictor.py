import logging
import os
from pathlib import Path

import numpy as np
import requests

logger = logging.getLogger(__name__)


class HDCNeuralPredictor:
    """
    Bridges the Holographic Mind (10k-dim Hypervectors) with the
    Neural Mind (JEPA/Latent Embeddings).

    Refactored to use verified Translation Bridge (10k <-> 2048).
    """

    def __init__(self, hdc_dim=10000, latent_dim=2048, seed=42):
        self.hdc_dim = hdc_dim
        self.latent_dim = 2048
        self.rng = np.random.default_rng(seed)

        if latent_dim != 2048:
            logger.warning(
                "HDCNeuralPredictor latent_dim=%s requested, but verified translation bridge uses 2048; using 2048.",
                latent_dim,
            )

        # 1. Load Verified Translation Bridge
        self.bridge = None
        weights_path = self._resolve_translation_bridge_weights()

        try:
            try:
                from services.pythia_mind.translation_bridge import (
                    NumpyTranslationBridge,
                )
            except ImportError:
                from services.translation_bridge.translation_bridge import (
                    NumpyTranslationBridge,
                )

            self.bridge = NumpyTranslationBridge(str(weights_path))
            logger.info(f"✅ Translation Bridge loaded from {weights_path}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Translation Bridge: {e}")
            raise

        # 2. JEPA Configuration (OCI)
        self.jepa_url = os.getenv("JEPA_SERVICE_URL", "http://td_jepa:8094/predict")
        self.jepa_active = False

    def _resolve_translation_bridge_weights(self) -> Path:
        """
        Resolve translation bridge weights with strict enforcement.
        Uses definitive source: /models/translation_bridge_v1.npz

        Resolution order:
        1. TRANSLATION_BRIDGE_WEIGHTS environment variable (if set)
        2. /app/models/translation_bridge_v1.npz (definitive source)
        """
        # Check environment variable first
        env_path = os.getenv("TRANSLATION_BRIDGE_WEIGHTS")
        if env_path:
            candidate = Path(env_path)
            if candidate.exists():
                logger.info(f"Loading translation bridge from ENV path: {candidate}")
                return candidate
            else:
                logger.warning(f"TRANSLATION_BRIDGE_WEIGHTS points to non-existent file: {candidate}")
        
        # Definitive source path
        definitive_path = Path("/app/models/translation_bridge_v1.npz")
        if definitive_path.exists():
            logger.info(f"Loading translation bridge from definitive source: {definitive_path}")
            return definitive_path
        
        # If we get here, the file is missing - log warning and return None
        searched = ", ".join([
            f"TRANSLATION_BRIDGE_WEIGHTS={env_path}" if env_path else "TRANSLATION_BRIDGE_WEIGHTS (not set)",
            str(definitive_path)
        ])
        logger.warning(
            f"Translation bridge weights not found. Searched: {searched}. "
            f"Translation bridge will be disabled."
        )
        return None

    def project_to_latent(self, hv):
        """Compresses HDC vector to Latent Space (2048d)."""
        if self.bridge:
            return self.bridge.hdc_to_dense(np.asarray(hv, dtype=np.float32))
        raise RuntimeError("Translation Bridge not initialized.")

    def reconstruct_hv(self, latent):
        """Reconstructs HDC vector from Latent Space."""
        if self.bridge:
            return self.bridge.dense_to_hdc(np.asarray(latent, dtype=np.float32))
        raise RuntimeError("Translation Bridge not initialized.")

    def predict_latent_trajectory(self, latent_state):
        """
        Calls the OCI td_jepa service for a geometric prediction.
        """
        try:
            # Attempt to call OCI JEPA Service
            response = requests.post(
                self.jepa_url, json={"latent": latent_state.tolist()}, timeout=2.0
            )
            if response.status_code == 200:
                return np.array(response.json()["predicted_latent"], dtype=np.float32)
            else:
                raise RuntimeError(
                    f"JEPA service returned status {response.status_code}"
                )
        except Exception as e:
            logger.error(f"❌ OCI JEPA Prediction Failed: {e}")
            raise RuntimeError(
                "JEPA service unreachable and mock fallbacks are DISABLED."
            )

    def predict_next(self, hdc_vector):
        """
        Cognitive Loop:
        HDC_t -> Latent_t -> Latent_t+1 (JEPA) -> HDC_t+1
        """
        # 1. Encode
        z_t = self.project_to_latent(hdc_vector)

        # 2. Predict (OCI JEPA or local drift)
        z_next = self.predict_latent_trajectory(z_t)

        # 3. Decode
        v_next = self.reconstruct_hv(z_next)

        return v_next
