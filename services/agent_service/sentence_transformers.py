"""
Local shim for `sentence_transformers` to provide a lightweight fallback when
the real package or its dependencies (huggingface_hub) are incompatible in the
running environment. This file intentionally lives in the service build context
so the local import will shadow the system package at runtime inside the container.
"""
import numpy as np
import hashlib

class SentenceTransformer:
    """Minimal deterministic stub that exposes encode(texts) -> np.ndarray
    Not semantically meaningful, but lets the service start and run basic flows.
    """
    def __init__(self, *args, **kwargs):
        pass

    def encode(self, texts, convert_to_numpy=True):
        if isinstance(texts, str):
            texts = [texts]
        vectors = []
        for t in texts:
            h = hashlib.sha256(t.encode('utf-8')).digest()
            arr = np.frombuffer(h, dtype=np.uint8).astype(np.float32) / 255.0
            vectors.append(arr)
        result = np.vstack(vectors)
        return result if convert_to_numpy else result.tolist()
