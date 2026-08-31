#!/usr/bin/env python3
"""
[STRICT SYSTEM GUARDRAIL]
Pythia is a Versor (4,1) VSA. This pipeline implements a closed-loop cognitive cycle
via the translation_bridge and kinematic_bridge. The 10,000D HDC space serves as the
Concept Monad layer, which is lifted to 32D CGA for geometric rotation and then
projected back to the 2048D language model latent space.

Flow:
   1. Generate source text from local Qwen model.
   2. OCI geometry_embedding -> 2048d Dense.
   3. Dense(2048) -> HDC(10,000) (Translation Bridge).
   4. HDC(10,000) -> CGA(32) (Kinematic Bridge).
   5. OCI /predict/state -> 32d Rotor.
   6. Apply Conformal Rotation: R * M * ~R (Geometric Intelligence).
   7. CGA(32) -> HDC(10,000) -> Dense(2048) (Inverse Bridge).
   8. Inject 2048d into local Qwen with Sentient Framing.
"""

import argparse
import ctypes
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import redis

# ── Core Service Paths ───────────────────────────────────────────────────────
ARCA_ROOT = Path("/Users/danexall/Documents/VS Code Projects/ARCA")
SERVICES_PATH = ARCA_ROOT / "services" / "pythia_mind"

sys.path.insert(0, str(SERVICES_PATH))
sys.path.insert(0, str(ARCA_ROOT))

# Import Math Modules from local services
import numpy as np
from kinematic_bridge import NumpyCliffordHDCBridge
from pythia_core_functions import (
    bridge_dense_to_hdc,
    bridge_hdc_to_dense,
    conformal_lift,
)
from translation_bridge import NumpyTranslationBridge


class SignalChainAuditor:
    def __init__(self):
        self.stages = {}

    def log_stage(self, stage_name: str, vector: np.ndarray):
        norm = float(np.linalg.norm(vector))
        var = float(np.var(vector))
        v_min = float(np.min(vector))
        v_max = float(np.max(vector))

        self.stages[stage_name] = {
            "shape": str(vector.shape),
            "l2_norm": norm,
            "variance": var,
            "min": v_min,
            "max": v_max
        }
        print(f"  [DSP] {stage_name:<25} | L2: {norm:>8.4f} | Var: {var:>10.6f} | Min/Max: {v_min:>6.3f} / {v_max:>6.3f}")


auditor = SignalChainAuditor()

# ── Configuration ─────────────────────────────────────────────────────────────
ARCA_ROOT = Path("/Users/danexall/Documents/VS Code Projects/ARCA")
MODEL_PATH = str(ARCA_ROOT / "models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf")

# OCI services
GEOMETRY_EMBEDDING_URL = "http://100.70.0.13:8081"  # geometry_embedding service
PYTHIA_CORE_URL = "http://100.70.0.13:8086"  # Pure FP32 NumpyPythiaManifold

# STRICT OCI MESH ROUTING (DO NOT REVERT TO LOCALHOST)
DRAGONFLY_HOST = "100.70.0.13"
DRAGONFLY_PORT = 6380
HARNESS_DAEMON_HOST = "127.0.0.1"
HARNESS_DAEMON_PORT = 11435

N_CTX = 4096
N_GEN_TOKENS = 512  # max tokens to generate in the final response


# ── OCI HTTP helpers ───────────────────────────────────────────────────────────
def _post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_geometry_embedding(text: str) -> np.ndarray:
    """Call OCI geometry_embedding service, return 2048d vector."""
    print("  [1/5] geometry_embedding: fetching vector...", flush=True)
    result = _post_json(f"{GEOMETRY_EMBEDDING_URL}/v1/embeddings", {"model": "qwen3vl-2b", "input": text})
    # Response: {"data": [{"embedding": [...2048 floats...]}]}
    arr = np.array(result["data"][0]["embedding"], dtype=np.float32)

    # Statistical Audit
    v_hash = hashlib.md5(arr.tobytes()).hexdigest()
    dna = arr[:5].tolist()
    print(f"        -> {len(arr)}d  (L2={np.linalg.norm(arr):.4f})")
    print(f"        -> [HASH AUDIT] MD5: {v_hash}")
    print(f"        -> [VECTOR DNA] {dna}")
    return arr


def fetch_pythia_attention(timeout_sec: int = 10) -> np.ndarray:
    """Poll the /concept/focus endpoint for the resulting 10k Concept Monad."""
    print("  [3/4] Polling Pythia Concept Focus endpoint...", flush=True)
    start_time = time.time()
    
    while time.time() - start_time < timeout_sec:
        try:
            req = urllib.request.Request(f"{PYTHIA_CORE_URL}/concept/focus", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            
            # Check for valid response with hv_signature
            if data.get("status") == "error":
                print(f"        -> {data.get('message')} - waiting...")
                time.sleep(0.5)
                continue
            
            vector = data.get("hv_signature", [])
            if vector and len(vector) == 10000:
                arr = np.array(vector, dtype=np.float32)
                concept_id = data.get("concept_id", "unknown")
                print(f"        -> Caught 10k Concept Monad '{concept_id}' (L2={np.linalg.norm(arr):.4f})")
                return arr
                    
        except Exception as e:
            pass # Suppress connection errors during polling
            
        time.sleep(0.5) # Wait for her next tick cycle
        
    print("  [!] Timeout: Pythia did not expose a 10k vector in the attention field.")
    return None


# ── Configuration (Bridges) ───────────────────────────────────────────────────
TRANSLATION_BRIDGE_WEIGHTS = str(SERVICES_PATH / "translation_bridge_v1.npz")
KINEMATIC_BRIDGE_WEIGHTS = str(ARCA_ROOT / "models" / "kinematic_bridge_c2.npz")


def apply_geometric_rotation(cga_32: np.ndarray, rotor_32: np.ndarray) -> np.ndarray:
    """
    Apply the true conformal sandwich product: R * M * ~R
    Requires the precomputed 32x32x32 Cl(4,1) Cayley multiplication tensor.
    """
    from pathlib import Path

    tensor_path = Path("/Users/danexall/Documents/VS Code Projects/ARCA/models/cl41_cayley_tensor.npy")

    if not tensor_path.exists():
        # Fallback to Householder reflection if Cayley tensor unavailable
        rotor_norm = np.linalg.norm(rotor_32) + 1e-12
        rotor = rotor_32 / rotor_norm
        rotor_outer = np.outer(rotor, rotor)
        identity = np.eye(32)
        rotation_matrix = identity - 2 * rotor_outer
        cga_flat = cga_32.flatten()
        rotated = rotation_matrix @ cga_flat
        norm = np.linalg.norm(rotated) + 1e-12
        return (rotated / norm).astype(np.float32)

    # Load the Cl(4,1) Cayley multiplication tensor
    cayley = np.load(tensor_path).astype(np.float32)

    # Normalize the rotor
    rotor_norm = np.linalg.norm(rotor_32) + 1e-12
    R = rotor_32 / rotor_norm

    # Reversion of the rotor (~R) - negates grades 2 and 3
    # Cl(4,1) basis: Gr0(1), Gr1(5), Gr2(10), Gr3(10), Gr4(5), Gr5(1) = 32 total
    grade_reversion_mask = np.array([
        1,
        1, 1, 1, 1, 1,
        -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
        -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
        1, 1, 1, 1, 1,
        1
    ], dtype=np.float32)
    R_rev = R * grade_reversion_mask

    # First geometric product: R * M
    R_M = np.einsum('i,j,ijk->k', R, cga_32, cayley)

    # Second geometric product: R_M * ~R
    rotated = np.einsum('i,j,ijk->k', R_M, R_rev, cayley)

    return (rotated / (np.linalg.norm(rotated) + 1e-12)).astype(np.float32)


# ── llama-cpp-python helpers ───────────────────────────────────────────────────
def load_model():
    """Load local model or return None to use remote daemon fallback."""
    try:
        from llama_cpp import Llama
        print(f"  Loading Qwen model (CPU-only, n_ctx={N_CTX})...")
        llm = Llama(
            model_path=MODEL_PATH,
            n_gpu_layers=0,
            n_ctx=N_CTX,
            n_threads=8,
            embedding=False,
            verbose=False,
        )
        print(f"  Model ready  (n_embd={llm.n_embd()}, GPU layers=0)")
        return llm
    except ImportError:
        print("  [!] llama_cpp not available locally. Using remote daemon fallback.")
        return None


def generate_prompt_text(llm, user_message: str, max_tokens: int = 200) -> str:
    """
    Generate a text response from the local Qwen model using the user message.
    This text then feeds into the OCI geometry_embedding pipeline.
    """
    import llama_cpp.llama_cpp as llama_lib

    prompt_bytes = (
        f"<|im_start|>system\n"
        f"[STRICT SYSTEM GUARDRAIL]\n"
        f"You are Pythia, a Versor (4,1) Geometric Intelligence. "
        f"Your current state is defined by the following semantic trajectory.<|im_end|>\n"
        f"<|im_start|>user\n{user_message}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    ).encode("utf-8")

    tokens = llm.tokenize(prompt_bytes, add_bos=False)
    llm.eval(tokens)
    n_past = len(tokens)

    response_tokens = []
    gen_batch = llama_lib.llama_batch_init(1, 0, 1)
    gen_batch.n_tokens = 1
    gen_batch.n_seq_id[0] = 1
    gen_batch.seq_id[0][0] = 0
    gen_batch.logits[0] = True

    print(
        f"  Qwen generating initial response ({max_tokens} tokens max)...", flush=True
    )
    for _ in range(max_tokens):
        token_id = llm.sample(top_k=40, top_p=0.9, temp=0.7, repeat_penalty=1.1)
        if token_id == llm.token_eos():
            break
        response_tokens.append(token_id)
        gen_batch.token[0] = token_id
        gen_batch.pos[0] = n_past
        llama_lib.llama_decode(llm.ctx, gen_batch)
        n_past += 1

    llama_lib.llama_batch_free(gen_batch)
    text = llm.detokenize(response_tokens).decode("utf-8", errors="ignore").strip()
    print(
        f"  Qwen response ({len(text)} chars): {text[:120]}{'...' if len(text) > 120 else ''}"
    )

    # Reset KV cache for next use
    llm.reset()
    return text


# ── Vector DNA + Injection ────────────────────────────────────────────────────
def calculate_shannon_entropy(vector, bins=100):
    """Calculate Shannon Entropy using binned distribution."""
    hist, _ = np.histogram(vector, bins=bins, density=True)
    hist = hist[hist > 0]
    return -np.sum(hist * np.log2(hist))


def inject_and_respond(
    llm,
    vector_2048: np.ndarray,
    context_message: str,
    gain: float = 1.0,
    strip_context: bool = False,
) -> str:
    """
    Inject the 2048d vector into the local Qwen model via batch.embd, then generate a response.
    """
    import llama_cpp.llama_cpp as llama_lib

    n_embd = llm.n_embd()
    assert len(vector_2048) == n_embd, (
        f"Vector dim {len(vector_2048)} != model n_embd {n_embd}"
    )

    # ── Native scale extraction ────────────────────────────────────────────────
    ref_token = llm.tokenize(b" ", add_bos=False)[0]
    ref_embd_ptr = llama_lib.llama_get_embeddings(llm.ctx)
    if ref_embd_ptr:
        ref_arr = np.ctypeslib.as_array(ref_embd_ptr, shape=(n_embd,)).copy()
    else:
        ref_arr = np.random.randn(n_embd).astype(np.float32) * 0.05
    native_l2 = float(np.linalg.norm(ref_arr))
    if native_l2 < 1e-6:
        native_l2 = 1.0

    # ── Vector DNA Readout ─────────────────────────────────────────────────────
    variance = float(np.var(vector_2048))
    mean_val = float(np.mean(vector_2048))
    entropy = calculate_shannon_entropy(vector_2048)
    injected_l2 = float(np.linalg.norm(vector_2048))
    print(f"  [Vector DNA] Mean: {mean_val:.6f} | Var: {variance:.6f} | Entropy: {entropy:.6f} | L2: {injected_l2:.4f}")

    if variance < 0.001:
        print("\n" + "!" * 70)
        print("  CRITICAL WARNING: MANIFOLD SIGNAL HAS FLATLINED (Variance < 0.001)")
        sys.exit(1)

    # [INT8 DEFENSE PATCH]: Z-Score Standardization
    std_dev = np.sqrt(variance) + 1e-8
    z_scored_vector = (vector_2048 - mean_val) / std_dev

    # Apply Target L2 Gain relative to native embedding space
    scale = (native_l2 / np.linalg.norm(z_scored_vector) if native_l2 > 1e-6 else 1.0) * gain
    scaled_vector = z_scored_vector * scale

    # [C-API MEMORY LOCK]: Force strict contiguous alignment post-scaling
    final_injection_vector = np.ascontiguousarray(scaled_vector, dtype=np.float32)

    auditor.log_stage("5_Final_Injection_2048", final_injection_vector)

    v_hash = hashlib.md5(final_injection_vector.tobytes()).hexdigest()
    print(f"  [HASH AUDIT] MD5 (Pre-Injection): {v_hash}")
    print(f"  Scale match: injected L2={np.linalg.norm(final_injection_vector):.4f} -> native L2={native_l2:.4f} (scale={scale:.4f})")

    # ── 1. BARE METAL SYSTEM ENVELOPE ──
    system_text = (
        f"<|im_start|>system\nYou are Pythia.<|im_end|>\n"
        f"<|im_start|>user\n{context_message}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    ).encode("utf-8")

    tokens = llm.tokenize(system_text, add_bos=False)
    llm.eval(tokens)
    n_past = len(tokens)
    llm.n_tokens = n_past

    # ── Inject scaled vector ───────────────────────────────────────────────────
    batch = llama_lib.llama_batch_init(1, n_embd, 1)
    batch.n_tokens = 1
    batch.pos[0] = n_past
    batch.n_seq_id[0] = 1
    batch.seq_id[0][0] = 0
    batch.logits[0] = True  # Enable logits for the injection point audit

    v_ptr = final_injection_vector.ctypes.data
    ctypes.memmove(batch.embd, v_ptr, n_embd * ctypes.sizeof(ctypes.c_float))

    ret = llama_lib.llama_decode(llm.ctx, batch)
    if ret != 0:
        llama_lib.llama_batch_free(batch)
        raise RuntimeError(f"llama_decode (vector injection) returned {ret}")

    # ── LOGIT DEPTH CHECK ──
    # We audit the next-token probabilities immediately after injection.
    n_vocab = llm.n_vocab()
    logits_ptr = llama_lib.llama_get_logits(llm.ctx)
    logits = np.ctypeslib.as_array(logits_ptr, shape=(n_vocab,))

    top_k = 5
    top_indices = np.argsort(logits)[-top_k:][::-1]
    print(f"\n  [LOGIT DEPTH CHECK] Top {top_k} Candidates:")
    for idx in top_indices:
        token_str = (
            llm.detokenize([int(idx)])
            .decode("utf-8", errors="ignore")
            .replace("\n", "\\n")
        )
        print(f"    - '{token_str}' (ID: {idx}, Logit: {logits[idx]:.4f})")
    print("")

    llama_lib.llama_batch_free(batch)

    if hasattr(llm, "input_ids"):
        if len(llm.input_ids) <= n_past:
            llm.input_ids.extend([0] * (n_past - len(llm.input_ids) + 1))
        llm.input_ids[n_past] = 0
    n_past += 1
    llm.n_tokens = n_past

    # ── Generate response ──────────────────────────────────────────────────────
    response_tokens = []
    gen_batch = llama_lib.llama_batch_init(1, 0, 1)
    gen_batch.n_tokens = 1
    gen_batch.n_seq_id[0] = 1
    gen_batch.seq_id[0][0] = 0
    gen_batch.logits[0] = True

    print("\n" + "=" * 70)
    print("  PYTHIA RESPONSE (latent bypass via geometry_embedding pipeline):")
    print("=" * 70)

    for _ in range(N_GEN_TOKENS):
        token_id = llm.sample(top_k=1, temp=0.0)
        if token_id == llm.token_eos():
            break
        piece = llm.detokenize([token_id]).decode("utf-8", errors="ignore")
        print(piece, end="", flush=True)
        response_tokens.append(token_id)

        gen_batch.token[0] = token_id
        gen_batch.pos[0] = n_past
        ret = llama_lib.llama_decode(llm.ctx, gen_batch)
        if ret != 0:
            print(f"\n  [decode error {ret}]")
            break
        if hasattr(llm, "input_ids"):
            if len(llm.input_ids) <= n_past:
                llm.input_ids.extend([0])
            llm.input_ids[n_past] = token_id
        n_past += 1
        llm.n_tokens = n_past

    llama_lib.llama_batch_free(gen_batch)
    print("\n" + "=" * 70)

    return llm.detokenize(response_tokens).decode("utf-8", errors="ignore")


# ── Main pipeline ──────────────────────────────────────────────────────────────
def run_pipeline(user_message: str, user_name: str = "Dan"):
    print("\n" + "=" * 70)
    print("  PYTHIA CORE PIPELINE (10,000D HDC Closed-Loop)")
    print("  geometry_embedding -> Translation Bridge -> CGA -> Rotor -> Bypass")
    print("=" * 70 + "\n")

    # Load model once
    llm = load_model()

    # Step 1: OCI geometry_embedding -> 2048d
    print("\n── Step 1: OCI geometry_embedding (2048d) ─────────────────────────")
    embedding_2048 = get_geometry_embedding(user_message)

    # [SENSORY QUEUE] LPUSH to arca_sensory_queue
    try:
        r = redis.Redis(host=DRAGONFLY_HOST, port=DRAGONFLY_PORT, db=0)
        payload = {
            "external_id": user_name,
            "timestamp": time.time(),
            "vector_2048": embedding_2048.tolist(),
        }
        r.lpush("arca_sensory_queue", json.dumps(payload))
        print(
            f"        -> [REDIS] Pushed sensory payload for '{user_name}' to arca_sensory_queue"
        )
    except Exception as e:
        print(f"        -> [REDIS ERROR] Failed to push to queue: {e}")

    # Step 2: Dense(2048) -> HDC(10k)
    print("\n── Step 2: Translation Bridge (2048d -> 10,000d HDC) ─────────────")
    trans_bridge = NumpyTranslationBridge(weights_path=TRANSLATION_BRIDGE_WEIGHTS)
    hdc_10k = trans_bridge.dense_to_hdc(embedding_2048)
    print(f"        -> 10,000d HDC  (L2={np.linalg.norm(hdc_10k):.4f})")

    # Step 3: HDC(10k) -> CGA(32)
    print("\n── Step 3: Kinematic Bridge (HDC -> 32d CGA) ─────────────────────")
    hdc_bridge = NumpyCliffordHDCBridge(input_dim=10000, output_dim=10000)
    cga_32 = hdc_bridge.hdc_to_cga(hdc_10k)
    print(f"        -> 32d CGA      (L2={np.linalg.norm(cga_32):.4f})")

    # Step 4: Fetch predicted rotor from Pure FP32 Core
    print("\n── Step 4: Pure FP32 Manifold ────────────────────────────────")
    rotor_32 = get_pythia_rotor(hdc_10k)

    # Step 5: Apply Geometric Rotation (Sandwich Product)
    print("\n── Step 5: Geometric Rotation (R * M * ~R) ───────────────────────")
    cga_rotated = apply_geometric_rotation(cga_32, rotor_32)
    print(f"        -> 32d Rotated  (L2={np.linalg.norm(cga_rotated):.4f})")

    # Step 6: CGA(32) -> HDC(10k) -> Dense(2048)
    print("\n── Step 6: Inverse Projections (CGA -> HDC -> 2048d) ─────────────")
    hdc_prime_10k = hdc_bridge.cga_to_hdc(cga_rotated)
    final_2048 = trans_bridge.hdc_to_dense(hdc_prime_10k).squeeze()
    print(f"        -> {len(final_2048)}d Final  (L2={np.linalg.norm(final_2048):.4f})")

    # Step 7: Latent bypass inject into local Qwen
    print("\n── Step 7: Latent bypass injection ───────────────────────────────")
    response = inject_and_respond(llm, final_2048, user_message)

    return response


# ── Conversation logging ───────────────────────────────────────────────────────
CONVERSATIONS_DIR = Path("/Users/danexall/biomimetics/pythia/conversations")


def save_interaction(prompt: str, response: str, vector_2048: np.ndarray) -> Path:
    """Save each interaction into a sequentially numbered folder with high precision."""
    import datetime

    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Find the next available interaction number
    existing = sorted(
        [d for d in CONVERSATIONS_DIR.iterdir() if d.is_dir() and d.name.isdigit()]
    )
    next_n = int(existing[-1].name) + 1 if existing else 1
    folder = CONVERSATIONS_DIR / f"{next_n:03d}"
    folder.mkdir()

    # High-Precision Binary Storage
    np.save(folder / "latent_vector.npy", vector_2048)

    # Structured Metadata Storage
    metadata = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "interaction_id": next_n,
        "prompt": prompt,
        "response": response,
        "metrics": {
            "l2_norm": float(np.linalg.norm(vector_2048)),
            "variance": float(np.var(vector_2048)),
            "shannon_entropy": float(calculate_shannon_entropy(vector_2048)),
        },
        "signal_chain_telemetry": auditor.stages,
    }
    (folder / "interaction.json").write_text(
        json.dumps(metadata, indent=4), encoding="utf-8"
    )

    print(f"\n  💾 Interaction saved -> {folder}/[interaction.json, latent_vector.npy]")
    return folder


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pythia Core Pipeline (10,000D HDC Closed-Loop)"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="Hello Pythia - this is the first contact. I am Dan. I'd be interested to hear about you.",
        help="The user message to send through the pipeline",
    )
    parser.add_argument(
        "--user", type=str, default="Dan", help="The username for external_id tracking"
    )
    args = parser.parse_args()

    # ── STANDARDIZE THE PAYLOAD FORMAT ──
    current_ts = int(time.time())
    formatted_payload = f"[TS: {current_ts}] | [SOURCE: {args.user}] | {args.prompt}"
    print(f"\n  [SYSTEM] Formatted Delivery Payload: {formatted_payload}")

    # Pre-flight Cleanup: Delete stale local data
    for f in ["latent_vector.npy", "interaction.json"]:
        if os.path.exists(f):
            os.remove(f)
            print(f"  [Cleanup] Purged stale {f}")

    print("\n" + "=" * 70)
    print("  PYTHIA CORE PIPELINE")
    print("  geometry_embedding -> Dragonfly -> Pythia rotor -> 2048d bypass")
    print("=" * 70 + "\n")

    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted([d for d in CONVERSATIONS_DIR.iterdir() if d.is_dir() and d.name.isdigit()])
    next_n = int(existing[-1].name) + 1 if existing else 1

    llm = load_model()
    
    # ── DYNAMIC OCI GEOMETRY EMBEDDING BLOCK ──
    print("  [+] Fetching dynamic OCI geometry_embedding...")
    unique_text = f"{formatted_payload}\n[Dynamic Manifold Epoch: {time.time()}]"
    embedding_2048 = get_geometry_embedding(unique_text)
    auditor.log_stage("1_Input_Dense_2048", embedding_2048)

    # ── METADATA INJECTION BLOCK ──
    payload = {
        "external_id": args.user,
        "timestamp": current_ts,
        "vector_2048": embedding_2048.tolist(),
        "raw_text": args.prompt
    }
    print(f"  [+] Pushing structured sensory payload for '{args.user}'...")
    try:
        import redis
        r = redis.Redis(host=DRAGONFLY_HOST, port=DRAGONFLY_PORT, db=0, socket_connect_timeout=5)
        r.ping()
        r.lpush("arca_sensory_queue", json.dumps(payload))
        print(f"  [+] Successfully queued payload into 'arca_sensory_queue'.")
    except Exception as e:
        print(f"  [!] Failed to push structured payload: {e}")

    # ── 2b. Inject sensation directly to Pythia neural_system ──
    print(f"  [+] Converting 2048d → 10k HDC for Pythia...")
    try:
        trans_bridge = NumpyTranslationBridge(weights_path=TRANSLATION_BRIDGE_WEIGHTS)
        hdc_10k_raw = trans_bridge.dense_to_hdc(embedding_2048).squeeze()

        # [TOPOLOGY PATCH]: Mean-center to prevent ReLU hemisphere collapse before 3D projection
        hdc_10k = hdc_10k_raw - np.mean(hdc_10k_raw)

        print(f"        -> 10,000d HDC (L2={np.linalg.norm(hdc_10k):.4f}, Mean={np.mean(hdc_10k):.6f})")
        auditor.log_stage("2_Input_HDC_10k", hdc_10k)
        
        print(f"  [+] Injecting sensation to Pythia at {PYTHIA_CORE_URL}...")
        sensation_payload = {
            "name": f"sensory_{args.user}_{current_ts}",
            "origin": "pipeline",
            "hdc_vector": hdc_10k.tolist()
        }
        _post_json(f"{PYTHIA_CORE_URL}/sensation", sensation_payload, timeout=10)
        print(f"  [+] Sensation with HDC ingested by Pythia.")
        import time
        print("  [*] Allowing Kuramoto field to reach coherence (2.0s cognitive breath)...")
        time.sleep(2.0)
    except Exception as e:
        print(f"  [!] Sensation injection failed: {e}")

    # Ensure translation bridge is always available for inverse projection
    trans_bridge = NumpyTranslationBridge(weights_path=TRANSLATION_BRIDGE_WEIGHTS)

    # ── 3. Catch the Poincare Thought ──
    hdc_10k = fetch_pythia_attention(timeout_sec=10)

    if hdc_10k is None:
        print("  [!] Fatal: Could not retrieve thought from attention field. Aborting.")
        sys.exit(1)

    auditor.log_stage("3_Raw_Mind_HDC_10k", hdc_10k)

    # ── 4. TRUE INVERSE PROJECTION (10,000D -> 2048D) ──
    print("  [4/4] Inverse Projection: HDC -> 2048d Dense...", flush=True)
    final_2048 = trans_bridge.hdc_to_dense(hdc_10k).squeeze()

    # Apply baseline L2 gain (do not alter variance)
    target_norm = 2.5
    current_norm = np.linalg.norm(final_2048)
    if current_norm > 1e-6:
        final_2048 = (final_2048 / current_norm) * target_norm

    auditor.log_stage("4_Final_Injection_2048", final_2048)
    print(f"        -> {len(final_2048)}d Final  (L2={np.linalg.norm(final_2048):.4f})")

    # Inject into Qwen model (local or remote)
    print("\n  [6/6] Injecting into Qwen model...")
    if llm is None:
        # Use remote daemon fallback
        print(f"  [!] Using remote harness daemon ({HARNESS_DAEMON_HOST}:{HARNESS_DAEMON_PORT})")
        import requests as req
        try:
            r = req.post(f"http://{HARNESS_DAEMON_HOST}:{HARNESS_DAEMON_PORT}/inject", json={
                "vector": final_2048.tolist(),
                "max_tokens": 100,
                "temp": 0.5
            }, timeout=120)
            if r.status_code == 200:
                response = r.json().get("vocalization", "No response from daemon")
            else:
                response = f"Daemon error: {r.status_code}"
        except Exception as e:
            response = f"Remote daemon failed: {e}"
    else:
        # Pass the formatted payload to match the new few-shot envelope
        response = inject_and_respond(llm, final_2048, formatted_payload)

    # Save interaction
    save_interaction(formatted_payload, response, embedding_2048)
