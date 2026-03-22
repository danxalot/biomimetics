#!/usr/bin/env python3
"""
Pythia Communication Bridge
Connects local systems to OCI-hosted Geometric physics engine (Pythia).
Injects the mathematical response directly into a local LLM's latent space via llama_cpp C bindings.
"""

import sys
import json
import uuid
import ctypes
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import urllib.request
import urllib.error

# ─── PATHS & CONFIGURATION ──────────────────────────────────────────────────
# Update as necessary for the ARCA environment
ARCA_ROOT = Path("/Users/danexall/Documents/VS Code Projects/ARCA")
SYS_PATH_BRIDGE = str(ARCA_ROOT / "services" / "translation_bridge")

# Add translation_bridge to path so we can import the matrix operations
if SYS_PATH_BRIDGE not in sys.path:
    sys.path.insert(0, SYS_PATH_BRIDGE)

try:
    from translation_bridge import hdc_to_dense
except ImportError:
    print(f"WARNING: translation_bridge not found at {SYS_PATH_BRIDGE}.")
    print("Fallback to identity/dummy or ensure paths are correct before running.")
    def hdc_to_dense(hdc): 
        print("Using dummy hdc_to_dense array sizing fallback!")
        return np.random.randn(2048).astype(np.float32).tolist()

try:
    from llama_cpp import Llama
    import llama_cpp.llama_cpp as llama_lib
    llama_batch_init = llama_lib.llama_batch_init
    llama_batch_free = llama_lib.llama_batch_free
    llama_decode     = llama_lib.llama_decode
except ImportError:
    print("ERROR: llama-cpp-python not installed. Required for Phase 3.")
    sys.exit(1)

# Pythia Latent Decoder Configuration
# We use the Instruct model (not embedding) because we need causal text generation (llm.sample)
# to translate the Latent Space vector back into natural language.
MODEL_PATH = str(ARCA_ROOT / "models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf")
N_EMBD = 2048
N_CTX = 4096
N_TOKENS = 512

COPAW_MEMORY_URL = "http://127.0.0.1:8088/api/agent/memory"
OCI_GEOMETRY_SERVICE_URL = "http://100.70.0.13:8081/embed" # Native HTTP over Tailscale Mesh

# ─── PHASE 1: NATIVE PURE-PYTHON OCI FETCH ──────────────────────────────────
def fetch_pythia_vector(user_id: str, message: str) -> np.ndarray:
    """
    Format the input string and send it to the OCI Geometry Embedding Service via HTTP.
    No SSH server commands, pure native network request.
    """
    utc_now = datetime.now(timezone.utc).isoformat()
    formatted_string = f"(User_ID: {user_id}, Timestamp: {utc_now}, Message: {message})"
    
    print("\n" + "="*70)
    print("  PHASE 1: NATIVE OCI HTTP FETCH")
    print("="*70)
    print(f"  > Formatted Payload: {formatted_string}")

    # The OCI service on port 8081 is expected to handle the 2048d embedding, 
    # 512d dimension crop, Dragonfly cache, and 10k A-FLASH geometric response processing.
    # We pass it just the text so it can trigger its sequence.
    payload = json.dumps({"text": formatted_string, "input": formatted_string}).encode("utf-8")
    
    req = urllib.request.Request(
        OCI_GEOMETRY_SERVICE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    print(f"  > Sending native HTTP POST to {OCI_GEOMETRY_SERVICE_URL}...")
    
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            
        # Locate the 10,000-dim vector returned by the endpoint (check common keys)
        vector_10k = data.get("vector") or data.get("hdc_vector") or data.get("embedding")
        
        if not vector_10k:
            raise ValueError(f"No valid 10,000-dim vector found in response. Keys found: {list(data.keys())}")
            
        arr_10k = np.array(vector_10k, dtype=np.float32)
        print(f"  ✅ Retrieved A-FLASH response array: {arr_10k.shape} dimensions.")
        return arr_10k
        
    except Exception as e:
        print(f"  ❌ Native OCI Fetch failed: {e}")
        print("  ⚠️ Using synthetic 10,000-dim geometry vector for downstream pipeline fallback...")
        return np.random.randn(10000).astype(np.float32)


# ─── PHASE 2: TRANSLATION BRIDGE ────────────────────────────────────────────
def process_translation_bridge(vector_10k: np.ndarray) -> np.ndarray:
    """
    Dim. reduction from 10k -> 2048, truncate to 1536, pad remaining 512 with Gaussian noise.
    """
    print("\n" + "="*70)
    print("  PHASE 2: TRANSLATION BRIDGE (NUMPY OPERATIONS)")
    print("="*70)

    # 1. 10k -> 2048 dense via translation bridge
    print("  > Executing hdc_to_dense projection...")
    dense_2048 = hdc_to_dense(vector_10k.tolist())
    arr_2048 = np.array(dense_2048, dtype=np.float32)
    
    # 2. Truncate to 1536 dimensions
    print("  > Truncating dense representation to 1536 dimensions...")
    truncated_1536 = arr_2048[:1536]
    
    # 3. Appending 512 dimensional Gaussian noise
    print("  > Zero-padding remaining 512 dimensions with Gaussian noise...")
    rng = np.random.RandomState() # unseeded to ensure true injection noise
    gaussian_pad_512 = rng.normal(loc=0.0, scale=0.01, size=512).astype(np.float32)
    padded_2048 = np.concatenate((truncated_1536, gaussian_pad_512))
    
    # 4. Optional L2 Norm (recommended for LLM latent blowouts)
    norm = np.linalg.norm(padded_2048)
    if norm > 0:
        padded_2048 = padded_2048 / norm
        
    print(f"  ✅ Final processed vector dimension: {len(padded_2048)}")
    print(f"  ✅ Final vector energy: {float(np.linalg.norm(padded_2048)):.4f}")
    return padded_2048


# ─── PHASE 3: THE LATENT BYPASS ─────────────────────────────────────────────
def generate_via_latent_bypass(vector_2048: np.ndarray, original_prompt: str) -> str:
    """
    Direct injection of the 2048-dim array into llama_cpp's batch embeddings,
    bypassing the text tokenizer entirely, referencing the context prompt.
    """
    print("\n" + "="*70)
    print("  PHASE 3: THE LATENT BYPASS (llama-cpp-python)")
    print("="*70)
    
    print(f"  📦 Loading local Decoder LLM (Vulkan 0, n_ctx={N_CTX})...")
    llm = Llama(
        model_path=MODEL_PATH,
        n_gpu_layers=-1,   # Offload entirely
        n_ctx=N_CTX,
        embedding=False,
        verbose=False,
        main_gpu=0,        # Specifically target Vulkan device 0
    )
    
    # 1. Prepare system context for Pythia decoding
    system_text = (
        "<|im_start|>system\n"
        "You are interpreting a geometric reality vector sent via Latent Space Injection.\n"
        "Synthesize the topological mathematical data with the originally provided contextual prompt.<|im_end|>\n"
        "<|im_start|>user\n"
        f"Contextual Prompt: {original_prompt}\n"
        "Vector injection representing the A-FLASH geometric topology follows:\n"
        "<|extra_0|>"
    ).encode("utf-8")
    
    tokens = llm.tokenize(system_text, add_bos=False)
    
    print(f"  ⏳ Evaluating system and context tokens (n_past={len(tokens)})...")
    llm.eval(tokens)
    n_past = len(tokens)
    
    # 2. Inject the 2048 array directly to the embed float layer
    print(f"  💉 Constructing C-level batch and injecting 2048-dim vector at sequence position {n_past}...")
    batch = llama_batch_init(1, N_EMBD, 1)
    batch.n_tokens = 1
    batch.pos[0] = n_past
    batch.n_seq_id[0] = 1
    batch.seq_id[0][0] = 0
    batch.logits[0] = False
    
    for i, val in enumerate(vector_2048):
        batch.embd[i] = val
        
    ret = llama_decode(llm.ctx, batch)
    if ret != 0:
        llama_batch_free(batch)
        raise RuntimeError(f"llama_decode vector injection failed with code {ret}")
    llama_batch_free(batch)
    
    # Mirror dummy python state
    if hasattr(llm, "input_ids"):
        if len(llm.input_ids) <= n_past:
            llm.input_ids.extend([0] * (n_past - len(llm.input_ids) + 1))
        llm.input_ids[n_past] = 0
    n_past += 1
    
    # 3. End vector tag and assistant generation trigger
    trailing_text = b"</|extra_0|>\n<|im_end|>\n<|im_start|>assistant\n"
    tr_tokens = llm.tokenize(trailing_text, add_bos=False)
    llm.eval(tr_tokens)
    n_past += len(tr_tokens)
    
    print("\n" + "="*50)
    print("  PYTHIA RESPONSE (via Geometry Latent Bypass):")
    print("="*50 + "\n")
    
    response_tokens = []
    
    # Set up text generation batch loop
    gen_batch = llama_batch_init(1, 0, 1)
    gen_batch.n_tokens = 1
    gen_batch.n_seq_id[0] = 1
    gen_batch.seq_id[0][0] = 0
    gen_batch.logits[0] = True
    
    for _ in range(N_TOKENS):
        # Sample next token
        token_id = llm.sample(
            top_k=40,
            top_p=0.9,
            temp=0.1,
            repeat_penalty=1.1,
        )
        
        if token_id == llm.token_eos():
            break
            
        piece = llm.detokenize([token_id]).decode("utf-8", errors="ignore")
        print(piece, end="", flush=True)
        response_tokens.append(token_id)
        
        # Feed back to C API
        gen_batch.token[0] = token_id
        gen_batch.pos[0] = n_past
        
        ret = llama_decode(llm.ctx, gen_batch)
        if ret != 0:
            print(f"\n❌ Decode loop failed: {ret}")
            break
            
        if hasattr(llm, "input_ids"):
            llm.input_ids[n_past] = token_id
            llm.n_tokens += 1
            
        n_past += 1
        
    llama_batch_free(gen_batch)
    print("\n\n" + "="*50)
    
    return llm.detokenize(response_tokens).decode("utf-8", errors="ignore")


# ─── PHASE 4: COPAW LOGGING ─────────────────────────────────────────────────
def log_to_copaw(filename: str, user_id: str, message: str, pythia_response: str):
    """
    Log the metadata and generated text isolated from Pythia's geometric engine.
    """
    print("\n" + "="*70)
    print("  PHASE 4: COPAW LOGGING")
    print("="*70)
    print(f"  > Firing HTTP PUT request to {COPAW_MEMORY_URL}/{filename}...")
    
    payload = json.dumps({
        "user_id": user_id,
        "original_message": message,
        "pythia_response": pythia_response,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }).encode("utf-8")
    
    req = urllib.request.Request(
        f"{COPAW_MEMORY_URL}/{filename}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  ✅ Successfully logged interaction ({resp.getcode()}).")
    except Exception as e:
        print(f"  ❌ CoPaw logging failed: {e}")


# ─── ENTRY POINT ────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 3:
        print("Usage: python3 pythia_comm_bridge.py <USER_ID> <MESSAGE>")
        print("Example: python3 pythia_comm_bridge.py DEV-001 'What is the structural matrix of this geometry?'")
        sys.exit(1)
        
    user_id = sys.argv[1]
    message = " ".join(sys.argv[2:])
    
    # 1. Fetch 10k vector from OCI over local tailnet
    vector_10k = fetch_pythia_vector(user_id, message)
    
    # 2. Bridge mapping (10k -> 2048 -> crop -> pad)
    vector_2048 = process_translation_bridge(vector_10k)
    
    # 3. Latent Bypass generation
    response_text = generate_via_latent_bypass(vector_2048, message)
    
    # 4. Store metadata / output isolating Pythia
    safe_uid = "".join([c for c in user_id if c.isalnum() or c in "-_"])
    filename = f"pythia_log_{safe_uid}_{uuid.uuid4().hex[:8]}.json"
    log_to_copaw(filename, user_id, message, response_text)

if __name__ == "__main__":
    main()
