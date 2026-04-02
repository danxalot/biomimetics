#!/usr/bin/env python3
"""
Isolated Geometry Kernel Ingestion Script
=========================================
Submits a document to the OCI Geometry Kernel for parsing and semantic chunking.
The Geometry Kernel communicates locally via the ARCA mesh network to complete
the extraction. The resulting solar_system.json is explicitly saved back
into the exact same directory as the original document.

Usage:
    python isolated_geometry_ingest.py [path/to/document.md] [objective_string]
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

# --- Configuration ---
GEOMETRY_KERNEL_URL = "http://100.70.0.13:8087"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_STORAGE_PATH = PROJECT_ROOT / "shared_storage"

def get_oci_path(local_path: Path) -> str:
    """
    Converts a local path inside shared_storage to the equivalent path
    expected by the OCI Geometry Kernel. The kernel mounts `shared_storage` 
    at `/app/shared_storage`, but the paths in its API usually expect
    the relative segment under `shared_storage/`.
    """
    try:
        # e.g.: /.../ARCA/shared_storage/ingest/output/ARCA Project Brief.md
        # relative_to shared_storage -> ingest/output/ARCA Project Brief.md
        rel_path = local_path.relative_to(SHARED_STORAGE_PATH)
        return str(rel_path)
    except ValueError:
        print(f"❌ Error: The file must reside inside the ARCA 'shared_storage' directory to be visible to OCI.")
        print(f"   File provided: {local_path}")
        sys.exit(1)

def main():
    if len(sys.argv) > 1:
        target_file = Path(sys.argv[1]).resolve()
    else:
        # Default fallback for convenience
        target_file = SHARED_STORAGE_PATH / "ingest" / "output" / "ARCA Project Brief.md"

    if len(sys.argv) > 2:
        objective = sys.argv[2]
    else:
        objective = "Analyse the document — extract core themes, goals, ethical principles, and development stages"

    if not target_file.exists():
        print(f"❌ Error: Cannot find document at {target_file}")
        sys.exit(1)

    print("\n" + "=" * 72)
    print("  ARCA — Isolated Geometry Kernel Ingestion")
    print("=" * 72)

    # Health check
    try:
        req = urllib.request.Request(f"{GEOMETRY_KERNEL_URL}/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            health = json.loads(resp.read().decode("utf-8"))
        print(f"\n  ✅ Geometry Kernel healthy: {health}")
    except Exception as e:
        print(f"\n  ⚠️  Geometry Kernel not responding on {GEOMETRY_KERNEL_URL}: {e}")
        print(f"  ❌ Cannot proceed without geometry_kernel. Aborting.")
        sys.exit(1)

    # Resolve OCI path
    oci_path = get_oci_path(target_file)
    print(f"  📄 Document: {target_file.name}")
    print(f"  📂 Local Path: {target_file}")
    print(f"  📂 OCI Relative Path: {oci_path}")
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

    print(f"  ⏳ Submitting to OCI geometry_kernel (this could take several minutes)...", flush=True)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            solar_system = json.loads(resp.read().decode("utf-8"))
        duration = time.time() - t0
    except Exception as e:
        print(f"  ❌ geometry_kernel call failed: {e}")
        sys.exit(1)

    n_objects = len(solar_system.get("objects", []))
    trajectory = solar_system.get("trajectory", [0, 0, 0])
    print(f"\n  ✅ Solar System received ({duration:.1f}s): {n_objects} objects extracted")
    print(f"  🚀 Global Trajectory: {[round(v, 4) for v in trajectory]}")

    # Spot-check positions
    for obj in solar_system.get("objects", [])[:3]:
        pos = obj.get("position", [0, 0, 0])
        print(f"     • {obj.get('id','?'):30s}  pos={[round(p, 4) for p in pos]}")

    # Determine final output path (same dir as source)
    out_dir = target_file.parent
    out_filename = f"{target_file.stem}_solar_system.json"
    out_path = out_dir / out_filename

    # Save
    with open(out_path, "w") as f:
        json.dump(solar_system, f, indent=2)
    
    print(f"\n  💾 Solary System data successfully saved to:")
    print(f"     {out_path}")
    print("=" * 72 + "\n")

if __name__ == "__main__":
    main()
