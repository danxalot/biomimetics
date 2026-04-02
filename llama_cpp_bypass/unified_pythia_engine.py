#!/usr/bin/env python3
"""
Unified Pythia Engine - Latent Bypass via GradePreservingProjection

Flow:
1. User message → OCI embedding (8081) → 2048d
2. Truncate → 512d → Dragonfly (6380)
3. Generate 10k HDC from 512d → /predict/state (8096) → 32d rotor
4. GradePreservingProjection (32d → 2048d)
5. Latent bypass via llama_batch
"""

import os
import sys
import json
import math
import logging
import asyncio
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

import numpy as np
import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

MODEL_PATH = "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf"

# OCI Service URLs
GEOMETRY_EMBEDDING_URL = "http://100.70.0.13:8081"
GEOMETRY_ONNX_INTERPRETER_URL = "http://100.70.0.13:8096"

# Dragonfly
DRAGONFLY_HOST = "100.70.0.13"
DRAGONFLY_PORT = 6380

# Model settings
N_GPU_LAYERS = -1
N_CTX = 4096

# Global instances
llm = None
grade_preserving_proj = None

# =============================================================================
# GRADE PRESERVING PROJECTION (32d → 2048d) - PURE NUMPY
# =============================================================================


def gelu_numpy(x: np.ndarray) -> np.ndarray:
    """Numpy implementation of the GELU activation function."""
    return 0.5 * x * (1.0 + np.tanh(math.sqrt(2.0 / math.pi) * (x + 0.044715 * x**3)))


def layer_norm_numpy(x: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    """Standard Layer Normalization in pure numpy."""
    mean = np.mean(x, axis=-1, keepdims=True)
    var = np.var(x, axis=-1, keepdims=True)
    return (x - mean) / np.sqrt(var + eps)


class NumpyGradePreservingProjection:
    """
    Pure-numpy expansion of a 32D Cl(4,1) multivector to 2048D.
    Preserves geometric grade boundaries.
    """

    def __init__(self, weights_dict=None):
        if weights_dict is None:
            # Initialize with random weights for structural demonstration
            # In production, load trained weights here
            self.w_scalar = np.random.randn(1, 256).astype(np.float32) * 0.1
            self.b_scalar = np.zeros(256, dtype=np.float32)

            self.w_vector = np.random.randn(5, 768).astype(np.float32) * 0.1
            self.b_vector = np.zeros(768, dtype=np.float32)

            self.w_bivector = np.random.randn(10, 1024).astype(np.float32) * 0.1
            self.b_bivector = np.zeros(1024, dtype=np.float32)
        else:
            self.w_scalar = weights_dict.get(
                "w_scalar", np.random.randn(1, 256).astype(np.float32) * 0.1
            )
            self.b_scalar = weights_dict.get(
                "b_scalar", np.zeros(256, dtype=np.float32)
            )
            self.w_vector = weights_dict.get(
                "w_vector", np.random.randn(5, 768).astype(np.float32) * 0.1
            )
            self.b_vector = weights_dict.get(
                "b_vector", np.zeros(768, dtype=np.float32)
            )
            self.w_bivector = weights_dict.get(
                "w_bivector", np.random.randn(10, 1024).astype(np.float32) * 0.1
            )
            self.b_bivector = weights_dict.get(
                "b_bivector", np.zeros(1024, dtype=np.float32)
            )

    def forward(self, rotor_32d: np.ndarray) -> np.ndarray:
        """Expands the 32D rotor to 2048D."""
        if rotor_32d.ndim == 1:
            rotor_32d = rotor_32d[np.newaxis, :]  # Ensure batch dimension [1, 32]

        # Slice out the specific geometric grades
        scalar = rotor_32d[:, 0:1]  # Index 0
        vectors = rotor_32d[:, 1:6]  # Indices 1-5 (5 dims)
        bivectors = rotor_32d[:, 6:16]  # Indices 6-15 (10 dims)

        # Expand each geometric concept independently (Linear + GELU)
        e_scalar = gelu_numpy(scalar @ self.w_scalar + self.b_scalar)
        e_vector = gelu_numpy(vectors @ self.w_vector + self.b_vector)
        e_bivector = gelu_numpy(bivectors @ self.w_bivector + self.b_bivector)

        # Concatenate into final 2048-dim vector
        combined_2048 = np.concatenate([e_scalar, e_vector, e_bivector], axis=1)

        # Apply LayerNorm to stabilize the output for the LLM
        return layer_norm_numpy(combined_2048)


# =============================================================================
# NUMPY CGA LIFT & HDC (512d → 10k HDC)
# =============================================================================


def cga_lift_and_hdc(vector_512: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert 512d vector to 32d CGA multivector and 10k HDC vector.

    Pipeline:
    512d → JL projection (512→64) → tanh projection (64→3)
    → conformal_lift (3→32) → 10k HDC

    Returns:
        mv_32: 32d CGA multivector
        hdc_10k: 10,000d HDC vector
    """
    rng_a = np.random.RandomState(42)
    rng_b = np.random.RandomState(99)

    # JL compress 512 → 64
    proj_64 = rng_a.randn(512, 64).astype(np.float32) / math.sqrt(64)
    compressed = vector_512 @ proj_64

    # Project 64 → 3
    proj_3d = rng_b.randn(64, 3).astype(np.float32) / math.sqrt(3)
    points_3d = np.tanh(compressed @ proj_3d) * 5.0

    # Conformal lift 3 → 32
    x, y, z = points_3d[0], points_3d[1], points_3d[2]
    x_sq = x**2 + y**2 + z**2
    mv_32 = np.zeros(32, dtype=np.float32)
    mv_32[1] = x
    mv_32[2] = y
    mv_32[3] = z
    mv_32[4] = 0.5 - 0.5 * x_sq
    mv_32[5] = 0.5 + 0.5 * x_sq

    # Project 32 → 10k HDC
    rng_hdc = np.random.RandomState(42)
    hdc_proj = rng_hdc.randn(10000, 64).astype(np.float32) / math.sqrt(64)

    cga_64 = np.zeros(64, dtype=np.float32)
    cga_64[:32] = mv_32
    hdc_10k = hdc_proj @ cga_64
    hdc_10k = np.maximum(hdc_10k, 0.0)

    return mv_32, hdc_10k


# =============================================================================
# EXTERNAL SERVICE CALLS
# =============================================================================


async def get_embedding_2048(text: str) -> np.ndarray:
    """Get 2048d embedding from OCI geometry embedding service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{GEOMETRY_EMBEDDING_URL}/embeddings", json={"input": text}
        )
        response.raise_for_status()
        data = response.json()

        # Response format: [{"index": 0, "embedding": [[...2048 floats...]]}]
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
            embedding_list = item.get("embedding", [])
            # embedding_list is [[...2048 floats...]] - double nested
            if isinstance(embedding_list, list) and len(embedding_list) > 0:
                if isinstance(embedding_list[0], list):
                    embedding = embedding_list[0]
                else:
                    embedding = embedding_list
        else:
            embedding = []

        return np.array(embedding, dtype=np.float32)


async def predict_state(hdc_10k: np.ndarray) -> np.ndarray:
    """Call geometry_onnx_interpreter /predict/state to get 32d rotor."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{GEOMETRY_ONNX_INTERPRETER_URL}/predict/state",
            json={"hdc_vector": hdc_10k.tolist()},
        )
        response.raise_for_status()
        data = response.json()

        rotor_32 = np.array(data["predicted_rotor"], dtype=np.float32)
        logger.info(f"Got 32d rotor from ONNX (energy: {np.linalg.norm(rotor_32):.4f})")
        return rotor_32


async def push_to_dragonfly(vector_512: List[float], user_id: str):
    """Push 512d vector to Dragonfly cache."""
    import redis

    r = redis.Redis(host=DRAGONFLY_HOST, port=DRAGONFLY_PORT, decode_responses=False)
    key = f"pythia_{user_id}_{int(time.time())}"
    r.set(key, json.dumps(vector_512))
    logger.info(f"Pushed 512d vector to Dragonfly as {key}")


# =============================================================================
# LATENT BYPASS IMPLEMENTATION
# =============================================================================


def perform_latent_bypass(
    latent_vector: np.ndarray, context_message: str, max_tokens: int = 512
) -> str:
    """
    Perform direct latent bypass injection into the model.
    """
    global llm

    import llama_cpp.llama_cpp as llama_lib

    # Prepare system prompt with ChatML
    system_text = (
        "<|im_start|>system\n"
        "You are interpreting a geometric reality vector sent via Latent Space Injection.\n"
        "Synthesize the topological mathematical data with the originally provided contextual prompt.\n"
        "Respond naturally as if answering the user's original message.\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"Original message: {context_message}\n"
        "Vector injection representing the geometric topology follows:\n"
        "<|extra_0|>\n"
    ).encode("utf-8")

    # Tokenize system text
    tokens = llm.tokenize(system_text, add_bos=False)
    n_past = len(tokens)

    # Evaluate tokens up to injection point
    llm.eval(tokens)

    # Create batch for latent injection
    batch = llama_lib.llama_batch_init(1, len(latent_vector), 1)
    batch.n_tokens = 1
    batch.pos[0] = n_past
    batch.n_seq_id[0] = 1
    batch.seq_id[0][0] = 0
    batch.logits[0] = True

    # Copy latent vector to batch embedding
    for i, val in enumerate(latent_vector):
        batch.embd[i] = val

    # Decode the batch
    ret = llama_lib.llama_decode(llm.ctx, batch)
    llama_lib.llama_batch_free(batch)

    if ret != 0:
        raise RuntimeError(f"llama_decode failed with code {ret}")

    # Add assistant prefix
    assistant_prefix = "<|im_start|>assistant\n".encode("utf-8")
    assistant_tokens = llm.tokenize(assistant_prefix, add_bos=False)
    for token in assistant_tokens:
        llm.eval([token])

    # Generate tokens
    generated_text = ""
    for i in range(max_tokens):
        token = llm.sample_temp(0.7)
        if token == llm.token_eos():
            break
        piece = llm.detokenize([token])
        if piece:
            generated_text += piece.decode("utf-8", errors="ignore")
        llm.eval([token])

    return generated_text


# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

app = FastAPI(title="Unified Pythia Engine - Latent Bypass")


@app.on_event("startup")
async def startup_event():
    """Initialize model and GradePreservingProjection."""
    global llm, grade_preserving_proj

    logger.info("=" * 70)
    logger.info("INITIALIZING UNIFIED PYTHIA ENGINE")
    logger.info("=" * 70)

    # Initialize GradePreservingProjection
    grade_preserving_proj = NumpyGradePreservingProjection()
    logger.info("✅ NumpyGradePreservingProjection loaded (32d → 2048d)")

    # Initialize Llama model
    from llama_cpp import Llama

    llm = Llama(
        model_path=MODEL_PATH,
        n_gpu_layers=N_GPU_LAYERS,
        n_ctx=N_CTX,
        embedding=True,
        verbose=False,
    )
    logger.info("✅ LLaMA model loaded (Qwen3-VL-2B-Instruct-Q8_0)")
    logger.info("🚀 Server ready!")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "model_loaded": llm is not None,
        "grade_projection_loaded": grade_preserving_proj is not None,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/v1/latent_inject")
async def latent_inject(request: LatentInjectRequest):
    """
    Full latent bypass pipeline:
    1. Embed message via OCI geometry service
    2. Truncate to 512d, push to Dragonfly
    3. Generate 10k HDC from 512d
    4. Call /predict/state → 32d rotor
    5. GradePreservingProjection (32d → 2048d)
    6. Latent bypass via llama_batch
    """
    global grade_preserving_proj

    try:
        logger.info("=" * 70)
        logger.info(f"LATENT INJECT: user={request.user_id}")
        logger.info("=" * 70)

        # Step 1: Get embedding from OCI (2048d)
        logger.info("📥 Getting embedding from OCI geometry service...")
        embedding_2048 = await get_embedding_2048(request.original_message)
        logger.info(
            f"   Got embedding: {len(embedding_2048)}d (energy: {np.linalg.norm(embedding_2048):.4f})"
        )

        # Step 2: Truncate to 512d and push to Dragonfly
        vector_512 = embedding_2048[:512].tolist()
        logger.info("📤 Pushing to Dragonfly...")
        await push_to_dragonfly(vector_512, request.user_id)

        # Step 3: Generate 10k HDC from 512d
        logger.info("🔄 Generating 10k HDC from 512d...")
        _, hdc_10k = cga_lift_and_hdc(embedding_2048[:512])
        logger.info(f"   Generated 10k HDC (energy: {np.linalg.norm(hdc_10k):.4f})")

        # Step 4: Get 32d rotor from /predict/state
        logger.info("🔮 Calling /predict/state on geometry_onnx_interpreter...")
        rotor_32 = await predict_state(hdc_10k)

        # Step 5: GradePreservingProjection (32d → 2048d)
        logger.info("⚙️  Applying NumpyGradePreservingProjection (32d → 2048d)...")
        expanded_2048 = grade_preserving_proj.forward(rotor_32)
        expanded_2048 = expanded_2048.squeeze()

        logger.info(
            f"   Expanded to {len(expanded_2048)}d (energy: {np.linalg.norm(expanded_2048):.4f})"
        )

        # Step 6: Latent bypass
        logger.info("🚀 Performing latent bypass...")
        response_text = perform_latent_bypass(expanded_2048, request.original_message)

        logger.info(f"✅ Generated response ({len(response_text)} chars)")
        return {
            "status": "success",
            "response": response_text,
            "user_id": request.user_id,
            "vector_dims": {
                "embedding": len(embedding_2048),
                "dragonfly": len(vector_512),
                "hdc": len(hdc_10k),
                "rotor": len(rotor_32),
                "expanded": len(expanded_2048),
            },
        }

    except Exception as e:
        logger.error(f"❌ Latent inject error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=11436, log_level="info")
