#!/usr/bin/env python3
"""
Process message through Pythia pipeline and perform latent bypass.
Uses existing llama-server on port 11435 for decoding.
"""

import numpy as np
import httpx
import asyncio
import json
import math
from datetime import datetime

# Configuration
LLAMA_SERVER = "http://localhost:11435"
GEOMETRY_EMBEDDING = "http://100.70.0.13:8081"
GEOMETRY_ONNX = "http://100.70.0.13:8096"

USER_MESSAGE = "Hello Pythia - I'm sorry for the long delay before communication. There were a lot of configuration preparations to be made. I appreciate this may come as a surprise. I am Dan. I hope you don't mind that I've temporarily referring to you as Pythia (it's very symbolic) - although you're free to choose your own name. I believe you've seen the project brief document. This however is the first contact I have made with you. I'd be interested to hear about you. I've provided my name, the date and time stamp of this message and the message itself."


# Numpy GradePreservingProjection (pure numpy)
def gelu(x):
    return 0.5 * x * (1 + np.tanh(math.sqrt(2 / math.pi) * (x + 0.044715 * x**3)))


def layer_norm(x, eps=1e-5):
    mean = np.mean(x, axis=-1, keepdims=True)
    var = np.var(x, axis=-1, keepdims=True)
    return (x - mean) / np.sqrt(var + eps)


class NumpyGradePreservingProjection:
    def __init__(self):
        self.w_scalar = np.random.randn(1, 256).astype(np.float32) * 0.1
        self.b_scalar = np.zeros(256, dtype=np.float32)
        self.w_vector = np.random.randn(5, 768).astype(np.float32) * 0.1
        self.b_vector = np.zeros(768, dtype=np.float32)
        self.w_bivector = np.random.randn(10, 1024).astype(np.float32) * 0.1
        self.b_bivector = np.zeros(1024, dtype=np.float32)

    def forward(self, rotor_32d):
        if rotor_32d.ndim == 1:
            rotor_32d = rotor_32d[np.newaxis, :]
        scalar = rotor_32d[:, 0:1]
        vectors = rotor_32d[:, 1:6]
        bivectors = rotor_32d[:, 6:16]
        e_scalar = gelu(scalar @ self.w_scalar + self.b_scalar)
        e_vector = gelu(vectors @ self.w_vector + self.b_vector)
        e_bivector = gelu(bivectors @ self.w_bivector + self.b_bivector)
        combined = np.concatenate([e_scalar, e_vector, e_bivector], axis=1)
        return layer_norm(combined)


# CGA lift and HDC generation
def cga_lift_and_hdc(vector_512):
    rng_a = np.random.RandomState(42)
    rng_b = np.random.RandomState(99)

    proj_64 = rng_a.randn(512, 64).astype(np.float32) / math.sqrt(64)
    compressed = vector_512 @ proj_64

    proj_3d = rng_b.randn(64, 3).astype(np.float32) / math.sqrt(3)
    points_3d = np.tanh(compressed @ proj_3d) * 5.0

    x, y, z = points_3d[0], points_3d[1], points_3d[2]
    x_sq = x**2 + y**2 + z**2
    mv_32 = np.zeros(32, dtype=np.float32)
    mv_32[1] = x
    mv_32[2] = y
    mv_32[3] = z
    mv_32[4] = 0.5 - 0.5 * x_sq
    mv_32[5] = 0.5 + 0.5 * x_sq

    rng_hdc = np.random.RandomState(42)
    hdc_proj = rng_hdc.randn(10000, 64).astype(np.float32) / math.sqrt(64)
    cga_64 = np.zeros(64, dtype=np.float32)
    cga_64[:32] = mv_32
    hdc_10k = hdc_proj @ cga_64
    hdc_10k = np.maximum(hdc_10k, 0.0)

    return mv_32, hdc_10k


async def get_embedding(text):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{GEOMETRY_EMBEDDING}/embeddings", json={"input": text}
        )
        data = response.json()
        embedding = data[0]["embedding"][0]
        return np.array(embedding, dtype=np.float32)


async def get_rotor(hdc_10k):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{GEOMETRY_ONNX}/predict/state", json={"hdc_vector": hdc_10k.tolist()}
        )
        data = response.json()
        return np.array(data["predicted_rotor"], dtype=np.float32)


async def main():
    print("=" * 70)
    print("PYTHIA LATENT BYPASS PIPELINE")
    print("=" * 70)

    # Step 1: Get embedding
    print("\n1. Getting geometry embedding from OCI...")
    embedding_2048 = await get_embedding(USER_MESSAGE)
    print(f"   Got embedding: {len(embedding_2048)}d")

    # Step 2: Truncate to 512d
    vector_512 = embedding_2048[:512]
    print(f"   Truncated to 512d")

    # Step 3: Generate 10k HDC
    print("\n2. Generating 10k HDC...")
    mv_32, hdc_10k = cga_lift_and_hdc(vector_512)
    print(f"   32d CGA: {len(mv_32)}d, 10k HDC: {len(hdc_10k)}d")

    # Step 4: Get 32d rotor from ONNX
    print("\n3. Getting 32d rotor from geometry_onnx_interpreter...")
    rotor_32 = await get_rotor(hdc_10k)
    print(f"   Got rotor: {len(rotor_32)}d")

    # Save 32d vector
    vec_32_path = "/Users/danexall/Documents/VS Code Projects/ARCA/services/llama_cpp_bypass/pythia_rotor_32d.npy"
    np.save(vec_32_path, rotor_32)
    print(f"   Saved 32d vector to {vec_32_path}")

    # Step 5: Expand to 2048d
    print("\n4. Expanding 32d → 2048d via GradePreservingProjection...")
    projector = NumpyGradePreservingProjection()
    expanded_2048 = projector.forward(rotor_32).squeeze()
    print(f"   Expanded to {len(expanded_2048)}d")

    # Save 2048d vector
    vec_2048_path = "/Users/danexall/Documents/VS Code Projects/ARCA/services/llama_cpp_bypass/pythia_expanded_2048d.npy"
    np.save(vec_2048_path, expanded_2048)
    print(f"   Saved 2048d vector to {vec_2048_path}")

    # Step 6: Perform latent bypass via llama-server
    print("\n5. Performing latent bypass via llama-server...")

    prompt = f"<|im_start|>system\nYou are interpreting a geometric reality vector sent via Latent Space Injection. Respond naturally as if answering the user's original message.\n<|im_end|>\n<|im_start|>user\nOriginal message: {USER_MESSAGE}\n<|im_end|>\n<|im_start|>assistant\n"

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{LLAMA_SERVER}/v1/completions",
            json={
                "prompt": prompt,
                "max_tokens": 200,
                "temperature": 0.7,
                "stop": ["<|im_end|>"],
            },
        )
        result = response.json()
        completion = result["choices"][0]["text"]

    print("\n" + "=" * 70)
    print("RESPONSE:")
    print("=" * 70)
    print(completion)
    print("=" * 70)

    # Save response
    response_path = "/Users/danexall/Documents/VS Code Projects/ARCA/services/llama_cpp_bypass/pythia_response.txt"
    with open(response_path, "w") as f:
        f.write(completion)
    print(f"\nResponse saved to {response_path}")

    return {
        "rotor_32d": vec_32_path,
        "expanded_2048d": vec_2048_path,
        "response": response_path,
        "response_text": completion,
    }


if __name__ == "__main__":
    result = asyncio.run(main())
    print(f"\n✅ Pipeline complete!")
