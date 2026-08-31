"""
ARCA Geometry Ingestion Pipeline Test - NumPy Version
==============================================

End-to-end test that validates the full ingestion pipeline:

  1. Read the ARCA Project Brief from shared_storage/atomized/intake/
  2. Extract key concepts and convert to SolarSystem geometry format
  3. Send through geometry_onnx_interpreter (ONNX model inference)
  4. Run kinematic training assimilation diagnostic (rotor continuity)
  5. Store resulting ConceptMonads via the /store/concept endpoint

Services Required:
  - Pythia Server         (port 11435) — llama.cpp + Qwen3VL
  - Geometry ONNX Interp  (port 8096)  — ONNX model + oracle layer

Usage:
  python geometry_test.py                          # Full pipeline
  python geometry_test.py --offline                # Offline mode (no services)
  python geometry_test.py --doc /path/to/doc.md    # Custom document
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Resolve project root (two levels up from this script)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # .../ARCA

DEFAULT_DOC_PATH = (
    PROJECT_ROOT / "shared_storage" / "atomized" / "intake" / "ARCA Project Brief.md"
)

ONNX_MODEL_PATH = PROJECT_ROOT / "models" / "pythia_c2h_5000_int8.onnx"
RESULTS_DIR = PROJECT_ROOT / "shared_storage" / "tmp_dev_records"

GEOMETRY_INTERPRETER_URL = os.getenv("ONNX_INTERPRETER_URL", "http://localhost:8096")
PYTHIA_SERVER_URL = os.getenv("PYTHIA_SERVER_URL", "http://localhost:11435")


# ═══════════════════════════════════════════════════════════════════════════
# NUMPY CLIFFORD HDC BRIDGE (offline fallback — matches geometry_onnx_interpreter_v2)
# ═══════════════════════════════════════════════════════════════════════════


class NumpyCliffordHDCBridge:
    """
    Pure-numpy HDC → Cl(4,1) bridge for offline diagnostics.
    Seed-matched to the production bridge in geometry_onnx_interpreter_v2.py.
    """
    
    def __init__(self, hdc_dim: int = 10000):
        rng_a = np.random.RandomState(42)
        rng_b = np.random.RandomState(99)
        self.hdc_dim = hdc_dim
        self.hdc_proj = rng_a.randn(hdc_dim, 64).astype(np.float32) / math.sqrt(64)
        self.proj_3d = rng_b.randn(64, 3).astype(np.float32) / math.sqrt(3)
    
    @staticmethod
    def _conformal_lift(points: np.ndarray) -> np.ndarray:
        """Lift R^3 → Cl(4,1) null vectors."""
        B = points.shape[0]
        mv = np.zeros((B, 32), dtype=np.float32)
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        x_sq = x**2 + y**2 + z**2
        mv[:, 1] = x
        mv[:, 2] = y
        mv[:, 3] = z
        mv[:, 4] = 0.5 - 0.5 * x_sq
        mv[:, 5] = 0.5 + 0.5 * x_sq
        return mv
    
    def hdc_to_cga(self, hdc_vector: np.ndarray) -> np.ndarray:
        """HDC [B, 10000] → Cl(4,1) [B, 32]."""
        if hdc_vector.ndim == 1:
            hdc_vector = hdc_vector[np.newaxis, :]
        compressed = hdc_vector @ self.hdc_proj
        points_3d = np.tanh(compressed @ self.proj_3d) * 5.0
        return self._conformal_lift(points_3d)
    
    @staticmethod
    def normalize_rotor(r: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(r, axis=-1, keepdims=True).clip(min=1e-8)
        return r / norm
    
    def name_to_hdc(self, name: str) -> np.ndarray:
        """Deterministic HDC vector from a concept name (chaotic basis analogue)."""
        seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) % (2**31)
        rng = np.random.RandomState(seed)
        return np.sign(rng.randn(self.hdc_dim)).astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════════
# CONFORMAL LIFT (NumPy version — for kinematic diagnostic)
# ═══════════════════════════════════════════════════════════════════════════


def conformal_lift_numpy(points_3d: np.ndarray) -> np.ndarray:
    """
    Fixed mathematical mapping from R^3 to Cl(4,1) null cone.
    X = x + 0.5*x^2*e_inf + e_0
    """
    B, T, _ = points_3d.shape
    cga_vectors = np.zeros((B, T, 32), dtype=np.float32)
    cga_vectors[..., 1:4] = points_3d
    sq_norm = np.sum(points_3d**2, axis=-1)
    cga_vectors[..., 4] = 0.5 * sq_norm
    cga_vectors[..., 5] = 1.0
    return cga_vectors


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — DOCUMENT INGESTION & CONCEPT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════


def read_document(doc_path: Path) -> str:
    """Read a markdown/text document."""
    if not doc_path.exists():
        print(f"  ❌ Document not found: {doc_path}")
        sys.exit(1)
    with open(doc_path, "r", encoding="utf-8") as f:
        return f.read()


def extract_concepts(text: str, max_concepts: int = 32) -> List[Dict[str, Any]]:
    """
    Extract key concepts from document text and assign 3D positions.

    Uses a deterministic hashing approach so the same document always
    produces the same geometric layout.  Each concept is a 'gravitational
    object' in the SolarSystem schema.
    """
    # ── Sentence-level split ──
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    # ── Keyword extraction (TF-style) ──
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "we",
        "our",
        "you",
        "your",
        "they",
        "their",
        "them",
        "not",
        "all",
        "as",
        "if",
        "so",
        "than",
        "such",
        "also",
        "into",
        "through",
        "during",
        "about",
        "up",
        "out",
        "who",
        "whom",
        "what",
        "when",
        "where",
        "how",
        "each",
        "every",
        "both",
        "more",
        "most",
        "other",
        "some",
        "any",
        "no",
        "own",
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    freq: Dict[str, int] = {}
    for w in words:
        if w not in stop_words:
            freq[w] = freq.get(w, 0) + 1

    # Top keywords by frequency
    ranked = sorted(freq.items(), key=lambda x: -x[1])
    keywords = [kw for kw, _ in ranked[:max_concepts]]

    if not keywords:
        keywords = ["document", "concept", "analysis", "structure"]

    # ── Assign 3D positions using golden-angle spiral on a sphere ──
    concepts = []
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))

    for i, keyword in enumerate(keywords):
        # Fibonacci sphere distribution
        y = 1.0 - (i / max(len(keywords) - 1, 1)) * 2.0
        radius_at_y = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden_angle * i
        x = math.cos(theta) * radius_at_y
        z = math.sin(theta) * radius_at_y

        # Scale by "mass" (normalised frequency)
        mass = min(1.0, freq.get(keyword, 1) / max(ranked[0][1], 1))
        scale = 1.0 + mass * 4.0  # spread: [1, 5]
        position = [round(x * scale, 4), round(y * scale, 4), round(z * scale, 4)]

        # Pick a representative sentence containing this keyword
        desc = ""
        for s in sentences:
            if keyword in s.lower():
                desc = s[:120]
                break

        concepts.append(
            {
                "id": f"concept:{keyword}",
                "mass": round(mass, 4),
                "position": position,
                "desc": desc or f"Extracted concept: {keyword}",
            }
        )

    return concepts


def build_solar_system(
    doc_text: str, system_id: str = "arca_project_brief"
) -> Dict[str, Any]:
    """
    Convert document text into SolarSystem JSON for the geometry_onnx_interpreter.
    """
    concepts = extract_concepts(doc_text, max_concepts=32)

    # Gravity well = the strongest concept
    gravity_concept = concepts[0]["id"].replace("concept:", "") if concepts else "core"
    gravity_mass = concepts[0]["mass"] * 10 if concepts else 5.0

    # Trajectory = centroid of all concept positions
    if concepts:
        positions = np.array([c["position"] for c in concepts])
        centroid = positions.mean(axis=0).tolist()
    else:
        centroid = [0.0, 0.0, 0.0]

    solar_system = {
        "system_id": system_id,
        "gravity_well": {"concept": gravity_concept, "mass": round(gravity_mass, 4)},
        "objects": concepts,
        "trajectory": [round(c, 4) for c in centroid],
    }

    return solar_system


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — SEND TO GEOMETRY ONNX INTERPRETER (online mode)
# ═══════════════════════════════════════════════════════════════════════════


def check_service(url: str, label: str) -> bool:
    """Check if a service is reachable."""
    try:
        import requests

        r = requests.get(f"{url}/health", timeout=3)
        if r.status_code == 200:
            print(f"  ✅ {label} is healthy at {url}")
            return True
    except Exception:
        pass

    # Try /interpret/health alias (geometry_onnx_interpreter)
    try:
        import requests

        r = requests.get(f"{url}/interpret/health", timeout=3)
        if r.status_code == 200:
            print(f"  ✅ {label} is healthy at {url}")
            return True
    except Exception:
        pass

    print(f"  ⚠️  {label} not reachable at {url}")
    return False


def send_to_onnx_pipeline(solar_system: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Send SolarSystem JSON to geometry_onnx_interpreter full pipeline."""
    import requests

    url = f"{GEOMETRY_INTERPRETER_URL}/interpret/full_pipeline"
    try:
        print(f"  → POST {url}")
        r = requests.post(url, json=solar_system, timeout=60)
        if r.status_code == 200:
            result = r.json()
            print(
                f"  ✅ Pipeline complete in {result.get('processing_time_ms', '?')}ms"
            )
            return result
        else:
            print(f"  ❌ Pipeline returned {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"  ❌ Pipeline request failed: {e}")
        return None


def send_to_onnx_only(solar_system: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fallback: ONNX inference only (no Qdrant/Dragonfly)."""
    import requests

    url = f"{GEOMETRY_INTERPRETER_URL}/interpret/onnx_only"
    try:
        print(f"  → POST {url}")
        r = requests.post(url, json=solar_system, timeout=30)
        if r.status_code == 200:
            result = r.json()
            print(
                f"  ✅ ONNX-only complete in {result.get('inference_time_ms', '?')}ms"
            )
            return result
        else:
            print(f"  ❌ ONNX-only returned {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"  ❌ ONNX-only request failed: {e}")
        return None


def store_concepts_remotely(
    concepts: List[Dict[str, Any]], bridge: NumpyCliffordHDCBridge
) -> int:
    """
    Store extracted concepts as ConceptMonads via /store/concept.
    Returns the number successfully stored.
    """
    import requests

    stored = 0
    url = f"{GEOMETRY_INTERPRETER_URL}/store/concept"

    for concept in concepts:
        name = concept["id"].replace("concept:", "")
        hdc_vec = bridge.name_to_hdc(name).tolist()

        payload = {
            "concept_id": str(uuid.uuid4()),
            "name": name,
            "source_document": "ARCA Project Brief",
            "content": concept.get("desc", name),
            "hv_signature": hdc_vec,
            "hv_velocity": [0.0] * len(hdc_vec),
            "energy_potential": float(concept.get("mass", 0.5)),
            "uncertainty": 0.5,
            "phase": 0.0,
        }

        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                stored += 1
        except Exception:
            pass

    return stored


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — PREDICT STATE (HDC → ONNX → Rotor)
# ═══════════════════════════════════════════════════════════════════════════


def predict_state_remote(
    hdc_vector: List[float], entropy_threshold: float = 5.0
) -> Optional[Dict[str, Any]]:
    """Call the /predict/state endpoint with an HDC vector."""
    import requests

    url = f"{GEOMETRY_INTERPRETER_URL}/predict/state"
    payload = {"hdc_vector": hdc_vector, "entropy_threshold": entropy_threshold}

    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"  ⚠️  /predict/state returned {r.status_code}: {r.text[:120]}")
            return None
    except Exception as e:
        print(f"  ⚠️  /predict/state failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — KINEMATIC TRAINING ASSIMILATION DIAGNOSTIC
# ═══════════════════════════════════════════════════════════════════════════


def run_kinematic_diagnostic_offline(
    solar_system: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Offline kinematic diagnostic using ONNX Runtime directly.
    
    Tests whether the trained Mamba SSM recognises sequential narrative
    trajectory vs. a randomised bag of concepts.
    """
    try:
        import onnxruntime as ort
    except ImportError:
        print("  ⚠️  onnxruntime not available — skipping kinematic diagnostic")
        return {"status": "skipped", "reason": "onnxruntime not installed"}

    positions = [
        obj.get("position", [0.0, 0.0, 0.0]) for obj in solar_system.get("objects", [])
    ]
    if len(positions) < 4:
        return {
            "status": "skipped",
            "reason": f"Need >= 4 objects, got {len(positions)}",
        }

    model_path = str(ONNX_MODEL_PATH)
    if not ONNX_MODEL_PATH.exists():
        return {"status": "skipped", "reason": f"ONNX model not found: {model_path}"}

    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    # Build sequential CGA input [1, 32, 32] (pad to seq_len=32)
    seq_len = 32
    np_positions = np.array(positions, dtype=np.float32)

    def np_conformal_lift(pts: np.ndarray) -> np.ndarray:
        N = pts.shape[0]
        mv = np.zeros((N, 32), dtype=np.float32)
        mv[:, 1:4] = pts
        sq = np.sum(pts**2, axis=-1)
        mv[:, 4] = 0.5 * sq
        mv[:, 5] = 1.0
        return mv

    cga = np_conformal_lift(np_positions)  # [T, 32]
    padded = np.zeros((1, seq_len, 32), dtype=np.float32)
    T = min(cga.shape[0], seq_len)
    padded[0, :T, :] = cga[:T]

    # Sequential
    out_seq = session.run(None, {input_name: padded})
    seq_rotors = out_seq[0]  # [1, 32, 32]

    # Randomised
    idx = np.random.permutation(T)
    padded_shuf = np.zeros_like(padded)
    padded_shuf[0, :T, :] = cga[idx]
    out_shuf = session.run(None, {input_name: padded_shuf})
    shuf_rotors = out_shuf[0]

    # Cosine similarity of consecutive rotors
    def cosine_continuity(rotors: np.ndarray) -> float:
        r = rotors[0]  # [32, 32]
        a = r[:-1]
        b = r[1:]
        dot = np.sum(a * b, axis=-1)
        na = np.linalg.norm(a, axis=-1).clip(1e-8)
        nb = np.linalg.norm(b, axis=-1).clip(1e-8)
        return float(np.mean(dot / (na * nb)))

    seq_cont = cosine_continuity(seq_rotors)
    shuf_cont = cosine_continuity(shuf_rotors)

    seq_h = float(out_seq[1].mean()) if len(out_seq) > 1 else 0.0
    shuf_h = float(out_shuf[1].mean()) if len(out_shuf) > 1 else 0.0

    return {
        "status": "complete",
        "backend": "ONNX Runtime (int8)",
        "num_concepts": len(positions),
        "sequential_continuity": round(seq_cont, 6),
        "randomised_continuity": round(shuf_cont, 6),
        "delta": round(seq_cont - shuf_cont, 6),
        "sequential_hamiltonian": round(seq_h, 6),
        "randomised_hamiltonian": round(shuf_h, 6),
        "trajectory_recognised": seq_cont > shuf_cont + 0.05,
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — REMOTE ROTOR PREDICTION PER CONCEPT (online only)
# ═══════════════════════════════════════════════════════════════════════════


def predict_rotors_for_concepts(
    concepts: List[Dict[str, Any]], bridge: NumpyCliffordHDCBridge
) -> List[Dict[str, Any]]:
    """
    For each concept, generate an HDC vector, call /predict/state, and
    collect the predicted rotor + Hamiltonian energy.
    """
    results = []
    for concept in concepts[:8]:  # Limit to first 8 to avoid hammering the server
        name = concept["id"].replace("concept:", "")
        hdc = bridge.name_to_hdc(name)

        pred = predict_state_remote(hdc.tolist())
        if pred is not None:
            results.append(
                {
                    "concept": name,
                    "rotor_norm": float(
                        np.linalg.norm(pred.get("predicted_rotor", []))
                    ),
                    "hamiltonian": pred.get("hamiltonian", 0.0),
                    "hopfield_energy": pred.get("hopfield_energy"),
                    "is_anomaly": pred.get("is_anomaly", False),
                    "inference_ms": pred.get("inference_time_ms", 0.0),
                }
            )
        else:
            results.append({"concept": name, "status": "failed"})

    return results


# ═══════════════════════════════════════════════════════════════════════════
# RESULTS OUTPUT
# ═══════════════════════════════════════════════════════════════════════════


def save_results(results: Dict[str, Any], label: str = "geometry_test") -> Path:
    """Save results JSON to shared_storage/tmp_dev_records/."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{label}_{timestamp}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  📄 Results saved to: {out_path}")
    return out_path


def print_kinematic_results(diag: Dict[str, Any]):
    """Pretty-print kinematic diagnostic results."""
    print("\n" + "=" * 60)
    print("  KINEMATIC TRAINING ASSIMILATION DIAGNOSTIC")
    print("=" * 60)

    if diag.get("status") == "skipped":
        print(f"  ⏭️  Skipped: {diag.get('reason', 'unknown')}")
        return

    print(f"  Backend:           {diag.get('backend', 'unknown')}")
    print(f"  Concepts tested:   {diag.get('num_concepts', '?')}")

    print()
    print(f"  Sequential Rotor Continuity:   {diag.get('sequential_continuity', '?')}")
    print(f"  Randomised Rotor Continuity:   {diag.get('randomised_continuity', '?')}")
    print(f"  Delta (seq - rand):            {diag.get('delta', '?')}")

    print()

    if "sequential_hamiltonian" in diag:
        print(f"  Sequential Hamiltonian:        {diag['sequential_hamiltonian']}")
        print(f"  Randomised Hamiltonian:        {diag['randomised_hamiltonian']}")

    print()

    if diag.get("trajectory_recognised"):
        print(
            "  ✅ SUCCESS: The engine's Mamba SSM natively recognises the "
            "narrative trajectory."
        )
        print(
            "     Sequential data can be safely routed into the PhenomenologicalCore."
        )
    else:
        print(
            "  ⚠️  WARNING: The engine treats the sequential narrative the "
            "same as a random bag of words."
        )
        print(
            "     Phase C3 (GPA Attention) may be required to learn true "
            "sequential geometric dependency."
        )


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="ARCA Geometry Ingestion Pipeline Test"
    )
    parser.add_argument(
        "--doc",
        type=str,
        default=str(DEFAULT_DOC_PATH),
        help="Path to the document to ingest",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run in offline mode (no service calls)",
    )
    parser.add_argument(
        "--skip-kinematic",
        action="store_true",
        help="Skip the kinematic diagnostic (faster)",
    )
    args = parser.parse_args()

    doc_path = Path(args.doc)
    offline = args.offline

    all_results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "document": str(doc_path),
        "mode": "offline" if offline else "online",
    }

    print()
    print("=" * 60)
    print("  ARCA GEOMETRY INGESTION PIPELINE TEST")
    print("=" * 60)

    # ── Step 1: Read document ──
    print("\n[1/5] Reading document...")
    doc_text = read_document(doc_path)
    print(f"  ✅ Read {len(doc_text)} chars from {doc_path.name}")
    all_results["document_chars"] = len(doc_text)

    # ── Step 2: Extract concepts & build SolarSystem ──
    print("\n[2/5] Extracting concepts → SolarSystem geometry...")
    solar_system = build_solar_system(doc_text)
    num_concepts = len(solar_system["objects"])
    print(f"  ✅ Extracted {num_concepts} concepts")
    print(f"  ✅ Gravity well: {solar_system['gravity_well']}")
    print(f"  ✅ Trajectory centroid: {solar_system['trajectory']}")

    # Show top 5 concepts
    for obj in solar_system["objects"][:5]:
        print(f"     • {obj['id']} (mass={obj['mass']}) @ {obj['position']}")
    if num_concepts > 5:
        print(f"     ... and {num_concepts - 5} more")

    all_results["solar_system"] = solar_system
    bridge = NumpyCliffordHDCBridge()

    # ── Step 3: Service checks + ONNX pipeline (online mode) ──
    print("\n[3/5] Geometry ONNX Interpreter pipeline...")
    if offline:
        print("  ⏭️  Offline mode — skipping service calls")
        all_results["onnx_pipeline"] = {"status": "skipped", "mode": "offline"}
    else:
        geom_ok = check_service(GEOMETRY_INTERPRETER_URL, "Geometry ONNX Interpreter")
        pythia_ok = check_service(PYTHIA_SERVER_URL, "Pythia Server")
        if not pythia_ok:
            print("  ⚠️  Pythia Server not available — Qwen3VL interpretation may fail")

        if geom_ok:
            # Try full pipeline first, fall back to onnx_only
            pipeline_result = send_to_onnx_pipeline(solar_system)
            if pipeline_result is None:
                print("  → Falling back to ONNX-only mode...")
                pipeline_result = send_to_onnx_only(solar_system)

            if pipeline_result is not None:
                vec_2048 = pipeline_result.get("vector_2048", [])
                print(f"  ✅ Output vector dims: {len(vec_2048)}")
                vec_norm = np.linalg.norm(vec_2048) if vec_2048 else 0
                print(f"  ✅ Output vector L2 norm: {vec_norm:.4f}")

            all_results["onnx_pipeline"] = pipeline_result or {"status": "failed"}

            # Store concepts
            print("\n  Storing concepts via /store/concept...")
            stored = store_concepts_remotely(solar_system["objects"], bridge)
            print(f"  ✅ Stored {stored}/{num_concepts} concepts")
            all_results["concepts_stored"] = stored
        else:
            print("  ⚠️  Geometry interpreter not available — skipping pipeline")
            all_results["onnx_pipeline"] = {"status": "service_unavailable"}

    # ── Step 4: Per-concept rotor prediction (online mode) ──
    print("\n[4/5] Per-concept rotor prediction...")
    if offline:
        print("  ⏭️  Offline mode — skipping")
        all_results["rotor_predictions"] = {"status": "skipped", "mode": "offline"}
    else:
        if check_service(GEOMETRY_INTERPRETER_URL, "Geometry ONNX Interpreter"):
            rotor_preds = predict_rotors_for_concepts(solar_system["objects"], bridge)
            for rp in rotor_preds:
                if "status" in rp and rp["status"] == "failed":
                    print(f"     ❌ {rp['concept']}: failed")
                else:
                    anomaly_flag = " ⚡ANOMALY" if rp.get("is_anomaly") else ""
                    print(
                        f"     • {rp['concept']}: "
                        f"H={rp.get('hamiltonian', 0):.4f}, "
                        f"‖R‖={rp.get('rotor_norm', 0):.4f}"
                        f"{anomaly_flag}"
                    )
            all_results["rotor_predictions"] = rotor_preds
        else:
            print("  ⚠️  Skipping — service not available")
            all_results["rotor_predictions"] = {"status": "service_unavailable"}

    # ── Step 5: Kinematic diagnostic ──
    if args.skip_kinematic:
        print("\n[5/5] Kinematic diagnostic: skipped (--skip-kinematic)")
        all_results["kinematic_diagnostic"] = {"status": "skipped", "reason": "flag"}
    else:
        print("\n[5/5] Kinematic training assimilation diagnostic...")
        diag = run_kinematic_diagnostic_offline(solar_system)
        print_kinematic_results(diag)
        all_results["kinematic_diagnostic"] = diag

    # ── Save results ──
    out_path = save_results(all_results)

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Document:   {doc_path.name}")
    print(f"  Concepts:   {num_concepts}")
    print(f"  Mode:       {'offline' if offline else 'online'}")
    print(f"  Results:    {out_path}")

    print()

    return all_results


if __name__ == "__main__":
    main()
