#!/usr/bin/env python3
"""
Pythia Resubmission Pipeline
=============================
Re-processes a document through the OCI Geometry Kernel (the ONLY authoritative
processor — real embedding-derived 3D positions, semantic chunking, full RLM walk).
Saves the resulting solar_system.json, then continues through the full Pythia
transformation chain: 2048d → 512d crop → CGA lift → HDC → Translation Bridge
→ 1536d truncation + Gaussian pad → LLM latent bypass.
"""

import json
import math
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ─── Project paths ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "services" / "translation_bridge"))
sys.path.insert(0, str(PROJECT_ROOT / "services" / "geometry_onnx_interpreter"))

INGEST_OUTPUT_DIR = PROJECT_ROOT / "shared_storage" / "ingest" / "output"
INGESTION_OUTPUT_DIR = PROJECT_ROOT / "shared_storage" / "ingestion" / "output"

# ─── Service endpoints ────────────────────────────────────────────────────────
# geometry_kernel runs exclusively on OCI — this is the ONLY processor for Stage 1
GEOMETRY_KERNEL_URL = "http://100.70.0.13:8087"



# ─── Stage 1: Recursive Ingestion via OCI Geometry Kernel (SOLE PROCESSOR) ───
def recursive_ingest(file_path, objective):
    print(f"\n{'='*72}")
    print(f"  STAGE 1: Recursive Ingestion via OCI Geometry Kernel")
    print(f"  🌐 URL: {GEOMETRY_KERNEL_URL}/geometry/ingest_recursive")
    print(f"{'='*72}")

    # The geometry_kernel resolves paths relative to /app/shared_storage on OCI.
    # Send the path relative to shared_storage so the kernel can find the file.
    doc_name = Path(file_path).name
    oci_path = f"ingest/output/{doc_name}"  # → /app/shared_storage/ingest/output/<doc>

    print(f"  📄 Document: {doc_name}")
    print(f"  📂 OCI path: /app/shared_storage/{oci_path}")
    print(f"  🎯 Objective: {objective}")

    payload = json.dumps({
        "file_path": oci_path,
        "objective": objective,
        "content_type": "AUTO",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{GEOMETRY_KERNEL_URL}/geometry/ingest_recursive",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(f"  ⏳ Sending to geometry_kernel (this may take several minutes)...", flush=True)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            solar_system = json.loads(resp.read().decode("utf-8"))
        duration = time.time() - t0
    except Exception as e:
        print(f"  ❌ geometry_kernel call failed: {e}")
        raise

    n_objects = len(solar_system.get("objects", []))
    trajectory = solar_system.get("trajectory", [0, 0, 0])
    print(f"  ✅ Solar System received ({duration:.1f}s): {n_objects} objects")
    print(f"  🚀 Trajectory: {[round(v, 4) for v in trajectory]}")

    # Spot-check positions — log the first 3
    for obj in solar_system.get("objects", [])[:3]:
        pos = obj.get("position", [0, 0, 0])
        print(f"     • {obj.get('id','?'):30s}  pos={[round(p, 4) for p in pos]}")

    # ── OVERWRITE the previously broken solar_system.json ────────────────────
    doc_stem = Path(file_path).stem
    ss_path = INGEST_OUTPUT_DIR / f"{doc_stem}_solar_system.json"
    INGEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(ss_path, "w") as f:
        json.dump(solar_system, f, indent=2)
    print(f"  💾 Saved (overwrites stale file): {ss_path}")

    return solar_system


# ─── Stage 2: ONNX-style preprocessing → 2048d vector ───────────────────────
def solar_system_to_2048d(solar_system):
    print(f"\n{'='*72}")
    print(f"  STAGE 2: Geometry → 2048d Vector")
    print(f"{'='*72}")

    objects = solar_system.get("objects", [])
    trajectory = solar_system.get("trajectory", [0.0, 0.0, 0.0])

    object_features = []
    for obj in objects:
        pos = obj.get("position", [0.0, 0.0, 0.0])
        if not isinstance(pos, list) or len(pos) < 3:
            pos = [0.0, 0.0, 0.0]
        features = [
            float(obj.get("mass", 0.5)),
            float(pos[0]), float(pos[1]), float(pos[2]),
            float(trajectory[0]), float(trajectory[1]), float(trajectory[2]),
        ]
        features.extend([0.0] * 25)  
        object_features.append(features)

    seq_len = 32
    while len(object_features) < seq_len:
        object_features.append([0.0] * 32)
    object_features = object_features[:seq_len]

    flat = []
    for feat in object_features:
        flat.extend(feat)

    vector_2048 = flat[:2048]
    while len(vector_2048) < 2048:
        idx = len(vector_2048)
        val = math.sin(trajectory[0] * idx) * math.cos(trajectory[1] * idx) * 0.01
        vector_2048.append(val)

    arr = np.array(vector_2048, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = (arr / norm) * 2.0  # Force to exactly 2.0 energy for downstream padding
    vector_2048 = arr.tolist()

    energy = float(np.linalg.norm(arr))
    print(f"  ✅ 2048d vector generated (energy: {energy:.4f}, {len(objects)} objects encoded)")
    return vector_2048


# ─── Stage 3: Qdrant / Dragonfly (512d crop) ─────────────────────────────
def push_to_dragonfly_and_qdrant(vector_2048, metadata):
    print(f"\n{'='*72}")
    print(f"  STAGE 3: 512d Vector Crop → Dragonfly Cache & Qdrant")
    print(f"{'='*72}")

    # Truncate to exactly 512 dimensions for Dragonfly requirement
    vector_512 = vector_2048[:512]
    
    # Re-normalise the truncated vector
    arr_512 = np.array(vector_512, dtype=np.float32)
    norm_512 = np.linalg.norm(arr_512)
    if norm_512 > 0:
        arr_512 = arr_512 / norm_512
    vector_512 = arr_512.tolist()
    print(f"  ✂️ Cropped exactly 512 dimensions for Dragonfly (energy: {float(np.linalg.norm(arr_512)):.4f})")

    # Qdrant store (2048d)
    try:
        from qdrant_integration import store_vector_2048
        qdrant_id = store_vector_2048(vector_2048, metadata)
        print(f"  ✅ Qdrant: stored vector {qdrant_id}")
    except Exception as e:
        print(f"  ⚠ Qdrant unavailable (non-fatal): {e}")

    # Dragonfly cache (512d)
    dragonfly_key = f"pythia_resubmit_{int(time.time())}"
    try:
        from dragonfly_cache import cache_vector_512
        cache_vector_512(vector_512, dragonfly_key, metadata)
        print(f"  ✅ Dragonfly: cached 512-dim vector as {dragonfly_key}")
    except Exception as e:
        print(f"  ⚠ Dragonfly unavailable (non-fatal): {e}")

    return vector_512, dragonfly_key


# ─── Stage 4: CGA Conformal Lift → HDC ──────────────────────────────────────
def cga_lift_and_hdc(vector_512):
    print(f"\n{'='*72}")
    print(f"  STAGE 4: CGA Conformal Lift → HDC 10,000d")
    print(f"{'='*72}")

    arr = np.array(vector_512, dtype=np.float32)
    rng_a = np.random.RandomState(42)
    rng_b = np.random.RandomState(99)

    proj_64 = rng_a.randn(512, 64).astype(np.float32) / math.sqrt(64)
    compressed = arr @ proj_64

    proj_3d = rng_b.randn(64, 3).astype(np.float32) / math.sqrt(3)
    points_3d = np.tanh(compressed @ proj_3d) * 5.0

    print(f"  📐 3D coordinates: [{points_3d[0]:.4f}, {points_3d[1]:.4f}, {points_3d[2]:.4f}]")

    x, y, z = points_3d[0], points_3d[1], points_3d[2]
    x_sq = x**2 + y**2 + z**2
    mv = np.zeros(32, dtype=np.float32)
    mv[1] = x
    mv[2] = y
    mv[3] = z
    mv[4] = 0.5 - 0.5 * x_sq
    mv[5] = 0.5 + 0.5 * x_sq

    rng_hdc = np.random.RandomState(42)
    hdc_proj = rng_hdc.randn(10000, 64).astype(np.float32) / math.sqrt(64)

    cga_64 = np.zeros(64, dtype=np.float32)
    cga_64[:32] = mv
    hdc_vector = hdc_proj @ cga_64
    hdc_vector = np.maximum(hdc_vector, 0.0)

    active_dims = int(np.sum(hdc_vector > 0))
    energy = float(np.linalg.norm(hdc_vector))
    print(f"  ✅ HDC 10,000d vector (active dims: {active_dims}, energy: {energy:.4f})")
    return mv, hdc_vector


# ─── Stage 5: Translation Bridge (HDC 10,000d → Dense 2048d) ────────────────
def translation_bridge_forward(hdc_vector):
    print(f"\n{'='*72}")
    print(f"  STAGE 5: Translation Bridge (HDC 10,000d → Dense 2048d)")
    print(f"{'='*72}")

    try:
        from translation_bridge import get_translation_bridge, hdc_to_dense
        bridge = get_translation_bridge()
        print(f"  🔧 Bridge: {bridge!r}")

        t0 = time.perf_counter()
        dense_2048 = hdc_to_dense(hdc_vector)
        bridge_ms = (time.perf_counter() - t0) * 1000

        energy = float(np.linalg.norm(dense_2048))
        print(f"  ✅ Dense 2048d vector (energy: {energy:.4f}, {bridge_ms:.1f}ms)")
        return dense_2048
    except Exception as e:
        print(f"  ❌ Translation bridge error: {e}")
        raise


# ─── Stage 6: Output Truncation & Payload Correction Protocol ─────────────
def pad_and_save_vector(dense_2048, doc_title, output_dir):
    print(f"\n{'='*72}")
    print(f"  STAGE 6: Payload Correction (1536d + Gaussian Pad + L2 Norm)")
    print(f"{'='*72}")

    arr = np.array(dense_2048) if not isinstance(dense_2048, np.ndarray) else dense_2048
    
    # 1. Truncate to 1536
    truncated_1536 = arr[:1536]
    
    # 2. Append 512 gaussian noise values (ϵ∼N(0,0.01)) to prevent mathematical vacuum
    rng = np.random.RandomState(42)
    gaussian_pad_512 = rng.normal(loc=0.0, scale=0.01, size=512).astype(np.float32)
    padded_2048 = np.concatenate((truncated_1536, gaussian_pad_512))
    
    # 3. L2-Normalize the entire 2048d vector to prevent thermodynamic spike (LayerNorm blowout)
    norm = np.linalg.norm(padded_2048)
    if norm > 0:
        normalized_2048 = padded_2048 / norm
    else:
        normalized_2048 = padded_2048
    
    print(f"  ✂️ Truncated dense representation to 1536 dimensions.")
    print(f"  ➕ Appended 512 Gaussian Noise values (mean 0.0, std 0.01).")
    print(f"  ⚖️ L2-Normalized to total energy 1.0.")
    assert len(normalized_2048) == 2048, "Padding length assert failed"
    print(f"  ✅ Final vector length is 2048 dimensions.")
    print(f"  ✅ Final vector energy is {float(np.linalg.norm(normalized_2048)):.4f}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r'[^\w\-]', '_', doc_title)
    filename = f"{safe_title}_resubmission_padded_{timestamp}.json"
    filepath = output_dir / filename

    vector_data = {
        "document_title": doc_title,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vector_dim": len(padded_2048),
        "vector_energy": float(np.linalg.norm(padded_2048)),
        "vector": padded_2048.tolist(),
        "source": "translation_bridge_v1_padded",
        "pipeline_stage": "zero_pad_512"
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(vector_data, f, indent=2)

    print(f"  💾 Saved resubmission JSON: {filepath}")
    return filepath


# ─── Main Pipeline ───────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 72)
    print("  ARCA — Pythia Resubmission Pipeline")
    print("  " + datetime.now(timezone.utc).isoformat())
    print("=" * 72)

    try:
        req = urllib.request.Request(f"{GEOMETRY_KERNEL_URL}/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            health = json.loads(resp.read().decode("utf-8"))
        print(f"\n  ✅ Geometry Kernel healthy: {health}")
    except Exception as e:
        print(f"\n  ⚠️  Geometry Kernel not responding on {GEOMETRY_KERNEL_URL}: {e}")
        print(f"  ❌ Cannot proceed without geometry_kernel. Aborting.")
        sys.exit(1)

    # Document target for resubmission
    doc_path = INGEST_OUTPUT_DIR / "ARCA Project Brief.md"
    if not doc_path.exists():
        print(f"  ❌ Document not found at {doc_path} for resubmission.")
        sys.exit(1)

    doc_title = doc_path.stem
    print(f"  📄 Document: {doc_title}")

    pipeline_start = time.time()

    solar_system = recursive_ingest(str(doc_path), objective="Analyse the ARCA project brief — extract core themes, goals, ethical principles, and development stages")

    vector_2048 = solar_system_to_2048d(solar_system)

    metadata = {
        "document": doc_title,
        "timestamp": time.time(),
        "pipeline": "pythia_resubmit"
    }
    
    vector_512, dragonfly_key = push_to_dragonfly_and_qdrant(vector_2048, metadata)

    cga_multivector, hdc_vector = cga_lift_and_hdc(vector_512)

    dense_2048 = translation_bridge_forward(hdc_vector)

    vector_path = pad_and_save_vector(dense_2048, doc_title, INGEST_OUTPUT_DIR)

    total_time = time.time() - pipeline_start

    print(f"\n{'='*72}")
    print(f"  ✅ RESUBMISSION COMPLETE")
    print(f"  ⏱ Total time: {total_time:.1f}s")
    print(f"  📄 Document: {doc_title}")
    print(f"  ☀️ Solar System saved explicitly")
    print(f"  🧮 1536-truncate/512-pad Response vector: {vector_path}")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    main()
