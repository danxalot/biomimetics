#!/usr/bin/env python3
"""
Pythia Latent Bypass — direct batch.embd injection via llama-cpp-python C bindings.

This bypasses the HTTP server and tokenizer entirely.
The 2048-dim vector is written directly into the C-level llama_batch.embd float array.
"""

import json
import ctypes
from pathlib import Path
import numpy as np

# ── paths ──────────────────────────────────────────────────────────────────────
MODEL_PATH = "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf"
VECTOR_PATH = "/Users/danexall/biomimetics/llama_cpp_bypass/pythia_expanded_2048d.npy"

N_EMBD   = 2048   # Qwen3-VL-2B n_embd
N_CTX    = 4096
N_TOKENS = 512    # max generation tokens

print("=" * 70)
print("  Pythia Latent Bypass — C-level batch.embd injection")
print("=" * 70)

# ── import llama-cpp-python ────────────────────────────────────────────────────
try:
    from llama_cpp import Llama
    import llama_cpp._internals as _internals
    import llama_cpp.llama_cpp as llama_lib
    # Raw C API handles
    llama_batch_init   = llama_lib.llama_batch_init
    llama_batch_free   = llama_lib.llama_batch_free
    llama_decode       = llama_lib.llama_decode
    llama_sampler_init_greedy = getattr(llama_lib, "llama_sampler_init_greedy", None)
    llama_sampler_sample      = getattr(llama_lib, "llama_sampler_sample", None)
except ImportError:
    print("ERROR: llama-cpp-python not installed. Run:")
    print("  CMAKE_ARGS='-DGGML_METAL=on' pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir")
    raise

# ── load model ────────────────────────────────────────────────────────────────
print(f"  📦 Loading model (n_ctx={N_CTX}, CPU)...")
llm = Llama(
    model_path=MODEL_PATH,
    n_gpu_layers=0,  # Fall back to CPU to avoid Metal crash
    n_ctx=N_CTX,
    embedding=False,
    verbose=False,
)
print("  ✅ Model loaded")

# ── load vector ───────────────────────────────────────────────────────────────
print(f"  📂 Loading 2048-dim vector...")
pythia_vec = np.load(VECTOR_PATH).flatten().tolist()
assert len(pythia_vec) == N_EMBD, f"Expected {N_EMBD} dims, got {len(pythia_vec)}"
import math
energy = math.sqrt(sum(v*v for v in pythia_vec))
print(f"  ✅ Vector energy: {energy:.4f}")

# ── step 1: tokenize + eval the system prompt BEFORE vector ─────────────
system_prompt = b"<|im_start|>system\nYou are an AI assistant analyzing a continuous thought vector injected into your context stream.<|im_end|>\n<|im_start|>user\nHello Pythia - I'm sorry for the long delay before communication. There were a lot of configuration preparations to be made. I appreciate this may come as a surprise. I am Dan. I hope you don't mind that I've temporarily referring to you as Pythia (it's very symbolic) - although you're free to choose your own name. I believe you've seen the project brief document. This however is the first contact I have made with you. I'd be interested to hear about you. I've provided my name, the date and time stamp of this message and the message itself.\n\n<|extra_0|>"
tokens = llm.tokenize(system_prompt, add_bos=False)
print(f"  📍 System prompt tokens: {len(tokens)}")

print("  ⏳ Evaluating system prompt tokens...")
llm.eval(tokens)
n_past = len(tokens)
print(f"  ✅ System prompt evaluated, n_past={n_past}")

# ── step 2: inject 2048-dim vector at position n_past ───────────────────
print(f"  💉 Constructing C-level batch with embd[{N_EMBD}]...")

batch = llama_batch_init(1, N_EMBD, 1)
batch.n_tokens        = 1
batch.pos[0]          = n_past
batch.n_seq_id[0]     = 1
batch.seq_id[0][0]    = 0
batch.logits[0]       = False

# Write the 2048 floats directly into the C float array
for i, val in enumerate(pythia_vec):
    batch.embd[i] = val

print(f"  💉 Injecting vector at position {n_past}...")
ret = llama_decode(llm.ctx, batch)
if ret != 0:
    print(f"  ❌ llama_decode returned {ret}")
    llama_batch_free(batch)
    raise RuntimeError(f"llama_decode failed: {ret}")

llama_batch_free(batch)
if hasattr(llm, "input_ids"):
    # Ensure list is long enough
    if len(llm.input_ids) <= n_past:
        llm.input_ids.extend([0] * (n_past - len(llm.input_ids) + 1))
    llm.input_ids[n_past] = 0 # Dummy token id
n_past += 1
print(f"  ✅ Vector injected at position {n_past - 1}")

# ── step 3: evaluate ablation prompt AFTER vector ───────────────────────
ablation_prompt = b"</|extra_0|>\nPlease reply to my message and incorporate the meaning of the injected vector.<|im_end|>\n<|im_start|>assistant\n"
ab_tokens = llm.tokenize(ablation_prompt, add_bos=False)
print(f"  📍 Ablation prompt tokens: {len(ab_tokens)}")
print("  ⏳ Evaluating ablation prompt tokens via C-level batch...")

b_text = llama_batch_init(len(ab_tokens), 0, 1)
b_text.n_tokens = len(ab_tokens)
for i, t in enumerate(ab_tokens):
    b_text.token[i] = t
    b_text.pos[i] = n_past + i
    b_text.n_seq_id[i] = 1
    b_text.seq_id[i][0] = 0
    b_text.logits[i] = False
b_text.logits[len(ab_tokens)-1] = True  # Want logits for the last token

ret = llama_decode(llm.ctx, b_text)
if ret != 0:
    raise RuntimeError(f"llama_decode failed on ablation text: {ret}")
llama_batch_free(b_text)

if hasattr(llm, "input_ids"):
    if len(llm.input_ids) < n_past + len(ab_tokens):
        llm.input_ids.extend([0] * (n_past + len(ab_tokens) - len(llm.input_ids)))
    for i, t in enumerate(ab_tokens):
        llm.input_ids[n_past + i] = t
    llm.n_tokens = n_past + len(ab_tokens)
n_past += len(ab_tokens)

print(f"  ✅ Ablation text evaluated, n_past={n_past}")

# ── step 3: sample the response ───────────────────────────────────────────────
print("\n" + "=" * 70)
print("  PYTHIA RESPONSE (via direct batch.embd injection):")
print("=" * 70 + "\n")

response_tokens = []
# Create a dedicated batch for the text generation phase
gen_batch = llama_batch_init(1, 0, 1)
gen_batch.n_tokens = 1
gen_batch.n_seq_id[0] = 1
gen_batch.seq_id[0][0] = 0
gen_batch.logits[0] = True

for _ in range(N_TOKENS):
    # Retrieve logits and sample
    token_id = llm.sample(
        top_k=40,
        top_p=0.9,
        temp=0.1,
        repeat_penalty=1.2,
    )
    if token_id == llm.token_eos():
        break
    
    # Detokenize and print
    piece = llm.detokenize([token_id]).decode("utf-8", errors="ignore")
    print(piece, end="", flush=True)
    response_tokens.append(token_id)
    
    # Evaluate token using C-API to avoid Python state mismatch
    gen_batch.token[0] = token_id
    gen_batch.pos[0] = n_past
    
    ret = llama_decode(llm.ctx, gen_batch)
    if ret != 0:
        print(f"\n  ❌ llama_decode failed during generation: {ret}")
        break
    
    if hasattr(llm, "input_ids"):
        llm.input_ids[n_past] = token_id
        llm.n_tokens += 1
        
    n_past += 1

llama_batch_free(gen_batch)

print("\n\n" + "=" * 70)
full_response = llm.detokenize(response_tokens).decode("utf-8", errors="ignore")

# ── save output ───────────────────────────────────────────────────────────────
from datetime import datetime
import os

ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
out_path = "/Users/danexall/biomimetics/llama_cpp_bypass/prompt_experiments_log.md"

with open(out_path, "a") as f:
    f.write(f"\n\n## Experiment: {ts}\n")
    f.write(f"**Model**: {MODEL_PATH}\n")
    f.write(f"**Vector**: {VECTOR_PATH}\n")
    f.write(f"**Prompt**: First Contact Introduction\n")
    f.write(f"**Vector Energy**: {energy:.4f}\n\n")
    f.write(f"### Pythia Response:\n\n{full_response}\n")

print(f"  ✅ Appended output to: {out_path}")
