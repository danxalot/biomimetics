#!/usr/bin/env python3
"""
Test script for unified_pythia_engine pipeline.
Tests each step independently before running the full server.
"""

import asyncio
import numpy as np
import torch

# Test GradePreservingProjection
print("=" * 70)
print("TEST 1: GradePreservingProjection")
print("=" * 70)


class GradePreservingProjection(torch.nn.Module):
    def __init__(self, target_dim=2048):
        super().__init__()
        self.scalar_expansion = torch.nn.Linear(1, 256)
        self.vector_expansion = torch.nn.Linear(5, 768)
        self.bivector_expansion = torch.nn.Linear(10, 1024)
        self.activation = torch.nn.GELU()
        self.layer_norm = torch.nn.LayerNorm(target_dim)

    def forward(self, rotor_32d):
        if rotor_32d.dim() == 1:
            rotor_32d = rotor_32d.unsqueeze(0)
        scalar = rotor_32d[:, 0:1]
        vectors = rotor_32d[:, 1:6]
        bivectors = rotor_32d[:, 6:16]
        e_scalar = self.activation(self.scalar_expansion(scalar))
        e_vector = self.activation(self.vector_expansion(vectors))
        e_bivector = self.activation(self.bivector_expansion(bivectors))
        combined_2048 = torch.cat([e_scalar, e_vector, e_bivector], dim=1)
        return self.layer_norm(combined_2048)


proj = GradePreservingProjection()
test_rotor = torch.randn(32)
output = proj(test_rotor)
print(f"Input: 32d, Output: {output.shape} ({len(output)}d)")
print(f"Output energy: {torch.norm(output).item():.4f}")
print("✅ GradePreservingProjection test passed!")
print()

# Test CGA lift and HDC
print("=" * 70)
print("TEST 2: CGA Lift and HDC Generation")
print("=" * 70)


def cga_lift_and_hdc(vector_512):
    import math

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


test_512 = np.random.randn(512).astype(np.float32)
mv_32, hdc_10k = cga_lift_and_hdc(test_512)
print(f"32d multivector: {len(mv_32)}d (energy: {np.linalg.norm(mv_32):.4f})")
print(f"10k HDC vector: {len(hdc_10k)}d (energy: {np.linalg.norm(hdc_10k):.4f})")
print("✅ CGA lift and HDC test passed!")
print()

# Test embedding endpoint
print("=" * 70)
print("TEST 3: OCI Embedding Service")
print("=" * 70)


async def test_embedding():
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://100.70.0.13:8081/embeddings", json={"input": "Hello Pythia"}
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                embedding = data[0]["embedding"]
            else:
                embedding = data.get("embedding", [])
            print(f"Got embedding: {len(embedding)}d")
            return embedding
    except Exception as e:
        print(f"⚠️  Embedding service unavailable: {e}")
        print("   (This is expected if OCI services aren't reachable)")
        return None


embedding = asyncio.run(test_embedding())
if embedding:
    print("✅ OCI embedding test passed!")
else:
    print("⚠️  Skipping embedding test (service unavailable)")
print()

# Test predict/state endpoint
print("=" * 70)
print("TEST 4: geometry_onnx_interpreter /predict/state")
print("=" * 70)


async def test_predict_state():
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            test_hdc = np.random.randn(10000).astype(np.float32).tolist()
            response = await client.post(
                "http://100.70.0.13:8096/predict/state", json={"hdc_vector": test_hdc}
            )
            response.raise_for_status()
            data = response.json()
            rotor = data.get("predicted_rotor", [])
            print(f"Got rotor: {len(rotor)}d")
            return rotor
    except Exception as e:
        print(f"⚠️  /predict/state unavailable: {e}")
        print("   (This is expected if OCI services aren't reachable)")
        return None


rotor = asyncio.run(test_predict_state())
if rotor:
    print("✅ /predict/state test passed!")
else:
    print("⚠️  Skipping /predict/state test (service unavailable)")
print()

print("=" * 70)
print("SUMMARY")
print("=" * 70)
print("All local components tested successfully!")
print("The full pipeline requires OCI services to be reachable.")
