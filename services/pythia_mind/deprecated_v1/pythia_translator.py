#!/usr/bin/env python3
import argparse
import ctypes
import json
import math
import os
import sys
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
import numpy as np

# ── Path Configuration ────────────────────────────────────────────────────────
PYTHIA_ROOT = Path("/Users/danexall/biomimetics/pythia")
ARCA_ROOT   = Path("/Users/danexall/Documents/VS Code Projects/ARCA")
MODEL_PATH  = str(ARCA_ROOT / "models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf")
N_CTX       = 4096

# OCI Service Endpoints
GEOMETRY_EMBEDDING_URL = "http://100.70.0.13:8081"
GEOMETRY_ONNX_URL      = "http://100.70.0.13:8096"

# Import Math Modules
try:
    from kinematic_bridge import NumpyCliffordHDCBridge
    from translation_bridge import NumpyTranslationBridge
except ImportError:
    print("  [!] Error: Math modules (kinematic_bridge, translation_bridge) not found.")
    raise

# ── Core Functions ────────────────────────────────────────────────────────────

def load_model():
    from llama_cpp import Llama
    print(f"  [0/4] LLM: Loading Qwen-2B (CPU/Metal)...", flush=True)
    llm = Llama(
        model_path=MODEL_PATH,
        n_gpu_layers=0, 
        n_ctx=2048,
        n_threads=8,
        verbose=False
    )
    return llm

def calculate_shannon_entropy(vector, bins=100):
    hist, _ = np.histogram(vector, bins=bins, density=True)
    hist = hist[hist > 0]
    return -np.sum(hist * np.log2(hist))

def _post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"        [DEBUG] HTTP Error Body: {body}")
        raise e

def get_geometry_embedding(text: str) -> np.ndarray:
    print(f"  [1/4] OCI Embeddings: '{text[:40]}...'", flush=True)
    try:
        result = _post_json(f"{GEOMETRY_EMBEDDING_URL}/embeddings", {"input": text})
        arr = np.array(result[0]["embedding"][0], dtype=np.float32)
        print(f"        -> L2: {np.linalg.norm(arr):.4f} | MD5: {hashlib.md5(arr.tobytes()).hexdigest()}")
        return arr
    except Exception as e:
        print(f"        [!] Embedding Service Error: {e}")
        return np.zeros(1024, dtype=np.float32) # Fallback to zero

def get_pythia_rotor(hdc_10k: np.ndarray) -> np.ndarray:
    print("  [2/4] OCI ONNX: Predicting rotor...", flush=True)
    try:
        # Ensure it's a flat list of 10k floats
        hdc_flat = hdc_10k.flatten().tolist()
        result = _post_json(f"{GEOMETRY_ONNX_URL}/predict/state", {"hdc_vector": hdc_flat})
        return np.array(result["predicted_rotor"], dtype=np.float32)
    except Exception as e:
        print(f"        [!] ONNX Service Error: {e}", flush=True)
        return np.zeros(32, dtype=np.float32)

def tokenize_robustly(llm, text):
    if isinstance(text, str): text = text.encode("utf-8")
    tokens = llm.tokenize(text, add_bos=False)
    return tokens

def _eval_tokens(llm, tokens):
    print(f"        [Eval] {len(tokens)} tokens...", flush=True)
    llm.eval(tokens)

# ── Injection Logic ───────────────────────────────────────────────────────────

def inject_and_respond(llm, vector, tokens_tail, max_new_tokens=512):
    try:
        import llama_cpp
    except ImportError:
        # Fallback to local bypass path
        import llama_cpp
    llama_lib = llama_cpp.llama_cpp
    
    n_inject = 8
    n_embd = 2048
    
    print(f"  [4/4] LLM: Injecting into cognitive stream...", flush=True)
    print(f"  [Vector DNA] Variance: {np.var(vector):.6f} | Entropy: {calculate_shannon_entropy(vector):.6f} | L2: {np.linalg.norm(vector):.4f}", flush=True)

    # Initialize batch with embeddings
    batch = llama_lib.llama_batch_init(n_inject, n_embd, 1)
    
    # Fill the batch
    batch.n_tokens = n_inject
    
    # Copy vector to batch.embd
    v_ptr = vector.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    ctypes.memmove(batch.embd, v_ptr, n_inject * n_embd * ctypes.sizeof(ctypes.c_float))

    # Set metadata for injection
    # Protocol: If batch.token is NULL (default when embd != 0), llama.cpp assumes all are embeddings.
    for i in range(n_inject):
        if batch.token:
            batch.token[i] = -1  # Signals to use batch.embd if token array exists
        batch.pos[i] = llm.n_tokens + i
        batch.n_seq_id[i] = 1
        batch.seq_id[i][0] = 0
        batch.logits[i] = (i == n_inject - 1)

    # Decode injection
    if llama_lib.llama_decode(llm.ctx, batch) != 0:
        llama_lib.llama_batch_free(batch)
        raise RuntimeError("llama_decode failed during injection")
    
    llm.n_tokens += n_inject
    llama_lib.llama_batch_free(batch)

    # Step 5: Eval Tail
    print(f"  [Step 3] Eval Prompt Tail...", flush=True)
    _eval_tokens(llm, tokens_tail)

    # Step 6: Autoregressive Loop
    print(f"  [Step 4] Igniting AR Loop...", flush=True)
    generated_ids = []
    generated_tokens = 0
    eos_id = llm.token_eos()
    
    print(f"  [Step 4] Igniting AR Loop (EOS: {eos_id})...", flush=True)
    
    while True:
        # Sample with temp=0.0 (Greedy)
        token_id = llm.sample(temp=0.0)
        
        # Stream output
        text = llm.detokenize([token_id]).decode('utf-8', errors='ignore')
        print(text, end='', flush=True)
        
        # Break on EOS or safety limit
        if token_id == eos_id:
            print("\n[EOS Detected]", flush=True)
            break
        if generated_tokens >= 512:
            print("\n[SAFETY BREAK: 512 TOKENS REACHED]", flush=True)
            break
            
        generated_ids.append(token_id)
        llm.eval([token_id])
        generated_tokens += 1
        
    print("\n\n[IGNITION COMPLETE]")

# ── Main Entry ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, default="System status.")
    parser.add_argument("--vector_path", type=str, help="Offline: Path to .npy vector")
    parser.add_argument("--live", action="store_true", help="Online: Fetch live CGA from OCI")
    parser.add_argument("--gain", type=float, default=1.5)
    args = parser.parse_args()

    llm = load_model()

    # Pre-tokenize prompt segments
    system_prompt = (
        "<|im_start|>system\n"
        "You are Pythia. Translate the following latent manifold signal into a status report.\n"
        "<|im_end|>\n"
    )
    
    prompt_head_str = (
        system_prompt + "<|im_start|>user\n"
        "Signal: "
    )
    prompt_tail_str = "\n<|im_end|>\n<|im_start|>assistant\nReport:"

    print(f"  [1/4] Tokenizing framing protocols...", flush=True)
    tokens_head = tokenize_robustly(llm, prompt_head_str)
    tokens_tail = tokenize_robustly(llm, prompt_tail_str)

    # Step 1: Eval Prompt Head
    print(f"  [Step 1] Eval Prompt Head...", flush=True)
    _eval_tokens(llm, tokens_head)

    if args.live:
        print(f"\n{'='*80}\n{'LIVE MANIFOLD IGNITION':^80}\n{'='*80}")
        # 1. Get Base Embedding
        print(f"  [1/4] OCI Embeddings: '{args.prompt}'", flush=True)
        emb = get_geometry_embedding(args.prompt)
        # 2. Lift to CGA & Encode to HDC
        print(f"  [2/4] OCI ONNX: Predicting rotor...", flush=True)
        vec_512 = emb[:512]
        norm = np.linalg.norm(vec_512)
        if norm > 0: vec_512 /= norm
        
        hdc_bridge = NumpyCliffordHDCBridge()
        cga_32 = hdc_bridge.hdc_to_cga(vec_512[np.newaxis, :]) 
        hdc_10k = hdc_bridge.cga_to_hdc(cga_32)
        
        # 3. Get Rotor from OCI ONNX
        rotor_32 = get_pythia_rotor(hdc_10k)
        
        # 4. Project to 2048D
        print("  [3/4] Local: Grade Preserving Projection...", flush=True)
        proj = GradePreservingProjection(seed=42)
        vector_2048 = proj.forward(rotor_32).squeeze()
        
        # Apply Gain
        l2 = np.linalg.norm(vector_2048)
        vector_2048 = (vector_2048 / l2 if l2 > 1e-6 else vector_2048).astype(np.float32) * args.gain
        
        # 5. Inject
        inject_and_respond(llm, vector_2048, tokens_tail)
        
    elif args.vector_path:
        v = np.load(args.vector_path)
        # Apply Gain
        l2 = np.linalg.norm(v)
        v = (v / l2 if l2 > 1e-6 else v).astype(np.float32) * args.gain
        inject_and_respond(llm, v, tokens_tail)
    else:
        print("Error: Specify either --live or --vector_path")

if __name__ == "__main__":
    main()
