#!/usr/bin/env python3
import json
import math
import time
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
import re
import sys

# Import functions from the existing pipeline without triggering its main block
from pythia_ingest_resubmit import (
    solar_system_to_2048d,
    cga_lift_and_hdc,
    translation_bridge_forward
)

ARCA_ROOT = Path("/Users/danexall/Documents/VS Code Projects/ARCA")
OUTPUT_DIR = ARCA_ROOT / "shared_storage/ingest/output"
INPUT_JSON = OUTPUT_DIR / "ARCA Project Brief_solar_system.json"

print("=" * 72)
print("  ARCA — Payload Conditioner (Solar System -> Bypass Payload)")
print("=" * 72)

# ─── Load Solar System ──────────────────────────────────────────────────
with open(INPUT_JSON, "r") as f:
    geometric_data = json.load(f)

print(f"  📥 Loaded geometric graph: {INPUT_JSON.name}")

# ─── Step 1: Base Extraction (to 2048d) ──────────────────────────────────
vector_2048 = solar_system_to_2048d(geometric_data)

# ─── Step 2: Protocol Requirement 1 - Normalize to 3.0 ──────────────────
arr_2048 = np.array(vector_2048, dtype=np.float32)
norm = np.linalg.norm(arr_2048)
if norm > 0:
    arr_2048 = (arr_2048 / norm) * 3.0  # Force to exactly 3.0 energy

print(f"  ⚖️ Normalized baseline 2048d geometry to explicit energy of 3.0")
print(f"     Actual energy: {float(np.linalg.norm(arr_2048)):.4f}")

# ─── Step 3: Truncate to 512d & Inject into Dragonfly ─────────────────────
vector_512 = arr_2048[:512].tolist()
print(f"  ✂️ Cropped baseline to exactly 512 dimensions for the pipeline")

dragonfly_key = f"pythia_resubmit_{int(time.time())}"
try:
    from dragonfly_cache import cache_vector_512
    # mock metadata from the solar system json
    metadata = {
        "document_title": "ARCA Project Brief",
        "system_id": geometric_data.get("system_id", "Unknown"),
        "chunk_index": 0,
        "total_chunks": 1,
        "vector_dim": 512,
        "source": "solar_system_conditioner",
    }
    cache_vector_512(vector_512, dragonfly_key, metadata)
    print(f"  ✅ Dragonfly: cached 512-dim intermediate vector as {dragonfly_key}")
except Exception as e:
    print(f"  ⚠ Dragonfly unavailable (non-fatal): {e}")

# ─── Step 4: CGA Lift & Translation Bridge ──────────────────────────────
_, hdc_vector = cga_lift_and_hdc(vector_512)
dense_2048 = translation_bridge_forward(hdc_vector)

# ─── Step 5: Protocol Requirement 2 & 3 - Truncate, Noise Pad, L2 Norm(1.0) 
print(f"\n{'='*72}")
print(f"  FINAL CONDITIONING: Truncate 1536d + Gaussian Pad + L2 Norm(1.0)")
print(f"{'='*72}")

arr_dense = np.array(dense_2048, dtype=np.float32)
truncated_1536 = arr_dense[:1536]

rng = np.random.RandomState(42)
gaussian_pad_512 = rng.normal(loc=0.0, scale=0.01, size=512).astype(np.float32)

padded_2048 = np.concatenate((truncated_1536, gaussian_pad_512))

final_norm = np.linalg.norm(padded_2048)
if final_norm > 0:
    conditioned_2048 = padded_2048 / final_norm
else:
    conditioned_2048 = padded_2048

print(f"  ✂️ Truncated dense representation to 1536 dimensions.")
print(f"  ➕ Appended 512 Gaussian Noise values (mean 0.0, std 0.01).")
print(f"  ⚖️ L2-Normalized final tensor to total energy 1.0.")
assert len(conditioned_2048) == 2048, "Padding length assert failed"
print(f"  ✅ Final vector length: {len(conditioned_2048)}")
print(f"  ✅ Final vector energy: {float(np.linalg.norm(conditioned_2048)):.4f}")

# ─── Step 6: Save Result ────────────────────────────────────────────────
doc_title = "ARCA Project Brief"
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
safe_title = re.sub(r'[^\w\-]', '_', doc_title)
filename = f"{safe_title}_conditioned_payload_{timestamp}.json"
filepath = OUTPUT_DIR / filename

vector_data = {
    "document_title": doc_title,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "vector_dim": len(conditioned_2048),
    "vector_energy": float(np.linalg.norm(conditioned_2048)),
    "vector": conditioned_2048.tolist(),
    "source": "payload_conditioner_v1",
    "pipeline_stage": "l2_norm_1_gaussian_pad"
}

with open(filepath, "w") as f:
    json.dump(vector_data, f, indent=2)

print(f"  💾 Saved conditioned bypass payload: {filepath}")
