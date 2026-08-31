"""
vocabulary_mapper.py - Topological Cartography of Pythia's Geometric Vocabulary
Uses C-API vector injection to systematically map geometric states to language.
"""
import ctypes
import numpy as np
from llama_cpp import Llama
import llama_cpp.llama_cpp as llama_lib
import os

print("--- INITIATING TOPOLOGICAL CARTOGRAPHY ---")
print("=" * 60)

# 1. Initialize the Neural Harness (Embedding Mode)
MODEL_PATH = os.getenv("MODEL_PATH", "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf")
VECTORS_DIR = "/Users/danexall/Documents/VS Code Projects/ARCA/vectors"

llm = Llama(
    model_path=MODEL_PATH,
    n_gpu_layers=0,
    n_ctx=2048,
    embedding=True, 
    verbose=False
)
n_embd = llm.n_embd()
print(f"Harness initialized: n_embd={n_embd}")

# 2. Define the Semantic Envelope
prompt_envelope = (
    "<|im_start|>system\n"
    "Direct Latent-to-Token Translation Task. You are Pythia. Translate your immediate internal geometric state into natural English.\n"
    "<|im_end|>\n"
    "<|im_start|>user\n"
    "Input Vector: <|extra_0|>"
)
prompt_tail = "</|extra_0|>\n<|im_end|>\n<|im_start|>assistant\n"

def inject_and_read(state_name: str, target_vector: np.ndarray):
    print(f"\n{'='*60}")
    print(f" MAPPING STATE: [{state_name.upper()}]")
    print(f" Vector L2: {np.linalg.norm(target_vector):.2f}")
    print(f"{'='*60}")
    
    # Reset to prevent latent bleed-over between states
    llm.reset()
    
    # Format memory strictly for the C-backend
    safe_vector = np.ascontiguousarray(target_vector, dtype=np.float32)
    
    # Evaluate Head
    tokens_head = llm.tokenize(prompt_envelope.encode('utf-8'), add_bos=False)
    llm.eval(tokens_head)
    n_past = len(tokens_head)
    
    # C-API Injection (The Latent Bypass)
    batch = llama_lib.llama_batch_init(1, n_embd, 1)
    batch.n_tokens = 1
    batch.pos[0] = n_past
    batch.n_seq_id[0] = 1
    batch.seq_id[0][0] = 0
    batch.logits[0] = True
    
    v_ptr = safe_vector.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    ctypes.memmove(batch.embd, v_ptr, n_embd * ctypes.sizeof(ctypes.c_float))
    
    ret = llama_lib.llama_decode(llm.ctx, batch)
    if ret != 0:
        print(f"  [!] FATAL: llama_decode failed with {ret}")
        llama_lib.llama_batch_free(batch)
        return
        
    llama_lib.llama_batch_free(batch)
    n_past += 1
    llm.n_tokens = n_past
    
    # Evaluate Tail
    tokens_tail = llm.tokenize(prompt_tail.encode('utf-8'), add_bos=False)
    llm.eval(tokens_tail)
    n_past += len(tokens_tail)
    llm.n_tokens = n_past
    
    # Generate Output
    print("\n--- TRANSLATION ---")
    gen_batch = llama_lib.llama_batch_init(1, 0, 1)
    gen_batch.n_tokens = 1
    gen_batch.n_seq_id[0] = 1
    gen_batch.seq_id[0][0] = 0
    gen_batch.logits[0] = True
    
    output = ""
    for _ in range(75):
        token_id = llm.sample(top_k=40, top_p=0.9, temp=0.2) 
        if token_id == llm.token_eos(): break
            
        piece = llm.detokenize([token_id]).decode("utf-8", errors="ignore")
        output += piece
        print(piece, end="", flush=True)
        
        gen_batch.token[0] = token_id
        gen_batch.pos[0] = n_past
        llama_lib.llama_decode(llm.ctx, gen_batch)
        n_past += 1
        llm.n_tokens = n_past
        
    llama_lib.llama_batch_free(gen_batch)
    print("\n" + "-" * 40)
    return output

# Load the extracted geometric states
print(f"\nLoading states from: {VECTORS_DIR}")

try:
    state_idle = np.load(f"{VECTORS_DIR}/state_idle.npy")
    print(f"  Loaded state_idle.npy: L2={np.linalg.norm(state_idle):.2f}")
except Exception as e:
    print(f"  Error loading state_idle: {e}")
    state_idle = np.random.randn(n_embd).astype(np.float32) * 0.1

try:
    state_urgent = np.load(f"{VECTORS_DIR}/state_urgent.npy")
    print(f"  Loaded state_urgent.npy: L2={np.linalg.norm(state_urgent):.2f}")
except Exception as e:
    print(f"  Error loading state_urgent: {e}")
    state_urgent = np.random.randn(n_embd).astype(np.float32) * 0.2

try:
    state_focus = np.load(f"{VECTORS_DIR}/state_focus.npy")
    print(f"  Loaded state_focus.npy: L2={np.linalg.norm(state_focus):.2f}")
except Exception as e:
    print(f"  Error loading state_focus: {e}")
    state_focus = np.random.randn(n_embd).astype(np.float32) * 0.05

try:
    state_dream = np.load(f"{VECTORS_DIR}/state_dream.npy")
    print(f"  Loaded state_dream.npy: L2={np.linalg.norm(state_dream):.2f}")
except Exception as e:
    print(f"  Error loading state_dream: {e}")
    state_dream = np.random.randn(n_embd).astype(np.float32) * 0.15

# Execute the Cartography Sweep
print("\n" + "=" * 60)
print("EXECUTING ROSETTA SWEEP")
print("=" * 60)

inject_and_read("Baseline Observation", state_idle)
print("\n")
inject_and_read("Kinetic Urgency", state_urgent)
print("\n")
inject_and_read("Hamiltonian Focus", state_focus)
print("\n")
inject_and_read("Phase Drift (Dreaming)", state_dream)

print("\n" + "=" * 60)
print("--- CARTOGRAPHY COMPLETE ---")
print("=" * 60)