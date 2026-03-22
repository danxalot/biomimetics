#!/usr/bin/env python3
"""
Diagnostic Script: Local Embed & Dual Latent Decoding
Tests whether the Qwen Instruct and Embedding models can process direct vector Latent injection.
"""

import math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

# Suppress llama-cpp chatter for clear output
import sys, os
original_stderr = sys.stderr

try:
    from llama_cpp import Llama
    import llama_cpp.llama_cpp as llama_lib
except ImportError:
    print("ERROR: llama-cpp-python not installed.")
    sys.exit(1)

ARCA_ROOT = Path("/Users/danexall/Documents/VS Code Projects/ARCA")
INSTRUCT_MODEL = str(ARCA_ROOT / "models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf")
EMBEDDING_MODEL = str(ARCA_ROOT / "models/qwen3-vl-embedding-2b-q8_0.gguf")

# The user's specific prompt
USER_MSG = "Hello Pythia - I'm sorry for the long delay before communication. There were a lot of configuration preparations to be made. I appreciate this may come as a surprise. I am Dan. I hope you don't mind that I've temporarily referring to you as Pythia (it's very symbolic) - although you're free to choose your own name. I believe you've seen the project brief document. This however is the first contact I have made with you. I'd be interested to hear about you. I've provided my name, the date and time stamp of this message and the message itself."
FORMATTED_MSG = f"(User_ID: Dan, Timestamp: 2026-03-22T10:23:25Z, Message: {USER_MSG})"

N_CTX = 4096

def silent_print(*args, **kwargs):
    with open(os.devnull, 'w') as f:
        sys.stderr = f
        # Do initialization
        sys.stderr = original_stderr

print("="*70)
print("  PART 1: LOCAL EMBEDDING (VIA INSTRUCT MODEL)")
print("="*70)
print(f"Loading Model for Embedding: {INSTRUCT_MODEL}")

# Load precisely for embedding to extract the mathematical syntax
llm_embedder = Llama(
    model_path=INSTRUCT_MODEL, 
    embedding=True, 
    n_gpu_layers=-1, 
    main_gpu=0, 
    verbose=False
)

print("Encoding prompt to local semantic vector...")
embed_result = llm_embedder.create_embedding(FORMATTED_MSG)
vector = embed_result["data"][0]["embedding"]
dim_size = len(vector)
energy = float(np.linalg.norm(np.array(vector)))
print(f"✅ Vector acquired! Length: {dim_size} dimensions. Energy: {energy:.4f}")

# Purge from VRAM
del llm_embedder

# Base Injection Decode Logic
def bypass_decode(llm, latent_vector, context_message):
    system_text = (
        "<|im_start|>system\n"
        "You are interpreting a geometric reality vector sent via Latent Space Injection.\n"
        "Synthesize the topological mathematical data with the originally provided contextual prompt.<|im_end|>\n"
        "<|im_start|>user\n"
        f"Contextual Prompt: {context_message}\n"
        "Vector injection representing the A-FLASH geometric topology follows:\n"
        "<|extra_0|>"
    ).encode("utf-8")
    
    tokens = llm.tokenize(system_text, add_bos=False)
    llm.eval(tokens)
    n_past = len(tokens)
    
    batch = llama_lib.llama_batch_init(1, len(latent_vector), 1)
    batch.n_tokens = 1
    batch.pos[0] = n_past
    batch.n_seq_id[0] = 1
    batch.seq_id[0][0] = 0
    batch.logits[0] = False
    
    for i, val in enumerate(latent_vector):
        batch.embd[i] = val
        
    ret = llama_lib.llama_decode(llm.ctx, batch)
    if ret != 0:
        llama_lib.llama_batch_free(batch)
        raise RuntimeError(f"llama_decode failed with code {ret}")
    llama_lib.llama_batch_free(batch)
    
    if hasattr(llm, "input_ids"):
        if len(llm.input_ids) <= n_past:
            llm.input_ids.extend([0] * (n_past - len(llm.input_ids) + 1))
        llm.input_ids[n_past] = 0
    n_past += 1
    
    trailing_text = b"</|extra_0|>\n<|im_end|>\n<|im_start|>assistant\n"
    tr_tokens = llm.tokenize(trailing_text, add_bos=False)
    llm.eval(tr_tokens)
    n_past += len(tr_tokens)
    
    response_tokens = []
    gen_batch = llama_lib.llama_batch_init(1, 0, 1)
    gen_batch.n_tokens = 1
    gen_batch.n_seq_id[0] = 1
    gen_batch.seq_id[0][0] = 0
    gen_batch.logits[0] = True
    
    print("\n   [LATENT OUTPUT STREAM START]")
    print("   ----------------------------")
    for _ in range(300): # Allow up to 300 tokens of generation
        try:
            token_id = llm.sample(top_k=40, top_p=0.9, temp=0.1, repeat_penalty=1.1)
            if token_id == llm.token_eos():
                break
                
            piece = llm.detokenize([token_id]).decode("utf-8", errors="ignore")
            print(piece, end="", flush=True)
            response_tokens.append(token_id)
            
            gen_batch.token[0] = token_id
            gen_batch.pos[0] = n_past
            
            ret = llama_lib.llama_decode(llm.ctx, gen_batch)
            if ret != 0:
                print(f"\n   [Decode Error: {ret}]")
                break
                
            if hasattr(llm, "input_ids"):
                llm.input_ids[n_past] = token_id
                llm.n_tokens += 1
            n_past += 1
        except Exception as e:
            print(f"\n   [Exception during sampling: {e}]")
            break
            
    llama_lib.llama_batch_free(gen_batch)
    print("\n   ----------------------------")
    print("   [LATENT OUTPUT STREAM END]\n")

print("\n" + "="*70)
print("  PART 2: LATENT DECODING VIA INSTRUCT MODEL")
print("="*70)
print(f"Loading Model: {INSTRUCT_MODEL}")

# Load Instruct model for decoding
llm_instruct = Llama(
    model_path=INSTRUCT_MODEL, 
    n_gpu_layers=-1, 
    main_gpu=0, 
    n_ctx=N_CTX, 
    embedding=False, 
    verbose=False
)

try:
    print("Injecting Extracted Vector and Triggers...")
    bypass_decode(llm_instruct, vector, FORMATTED_MSG)
except Exception as e:
    print(f"Instruct Model Decoding Failed: {e}")

# Purge from VRAM
del llm_instruct

print("="*70)
print("  TEST ROUTINE COMPLETE")
print("="*70)
