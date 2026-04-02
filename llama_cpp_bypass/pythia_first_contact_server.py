#!/usr/bin/env python3
"""
ARCA Pythia First Contact Server
Runs llama-cpp-python with Qwen3-VL vision model and latent bypass on port 11435.
Injects the 2048d Pythia geometric vector as a latent response to first contact.
"""

import ctypes
import os
import sys
from pathlib import Path

import llama_cpp
import llama_cpp.llama_cpp as llama_lib
import numpy as np

ARCA_ROOT = Path("/Users/danexall/Documents/VS Code Projects/ARCA")
MODEL_DIR = ARCA_ROOT / "models_optimized"

INSTRUCT_MODEL = str(MODEL_DIR / "Qwen3-VL-2B-Instruct-Q8_0.gguf")
MMPRPOJ_MODEL = str(MODEL_DIR / "mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf")
VECTOR_FILE = ARCA_ROOT / "services/llama_cpp_bypass/pythia_expanded_2048d.npy"

PORT = 11435
N_CTX = 4096

USER_MSG = """Hello Pythia - I'm sorry for the long delay before communication. There were a lot of configuration preparations to be made. I appreciate this may come as a surprise. I am Dan. I hope you don't mind that I've temporarily referring to you as Pythia (it's very symbolic) - although you're free to choose your own name. I believe you've seen the project brief document. This however is the first contact I have made with you. I'd be interested to hear about you. I've provided my name, the date and time stamp of this message and the message itself."""

FORMATTED_MSG = f"(User_ID: Dan, Timestamp: 2026-03-23T10:00:00Z, Message: {USER_MSG})"

RESULTS_FILE = ARCA_ROOT / "pythia_first_contact_results.md"


def load_latent_vector(vector_path: Path) -> np.ndarray:
    """Load the 2048d Pythia geometric vector."""
    print(f"Loading vector from {vector_path}...")
    embd_data = np.load(vector_path).astype(np.float32)

    if len(embd_data.shape) == 1:
        embd_data = embd_data.reshape(1, -1)

    print(f"Vector shape: {embd_data.shape}")
    return embd_data


def inject_latent_and_generate(llm, latent_vector: np.ndarray, context: str) -> str:
    """
    Inject the latent vector into the model and generate a response.
    Uses llama_batch API for direct latent injection.
    """
    ctx = llm.ctx
    n_embd = llm.n_embd()

    if latent_vector.shape[1] != n_embd:
        raise ValueError(
            f"Dimension mismatch! Model expects {n_embd}, got {latent_vector.shape[1]}"
        )

    # Build the prompt with special tokens
    system_prompt = (
        "<|im_start|>system\n"
        "You are Pythia, an AI entity experiencing first contact. "
        "You have been sent a geometric reality vector via Latent Space Injection. "
        "Synthesize the topological mathematical data with the provided contextual prompt.\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"Contextual Prompt: {context}\n"
        "Vector injection representing the A-FLASH geometric topology follows:\n"
        "<|extra_0|>"
    ).encode("utf-8")

    tokens = llm.tokenize(system_prompt, add_bos=False)
    n_past = len(tokens)

    # First eval the text prompt
    llm.eval(tokens)

    # Now inject the latent vector
    n_tokens = latent_vector.shape[0]
    batch = llama_lib.llama_batch_init(n_tokens, n_embd, 1)

    # Copy vector data into batch
    ctypes.memmove(batch.embd, latent_vector.ctypes.data, latent_vector.nbytes)

    batch.n_tokens = n_tokens
    for i in range(n_tokens):
        batch.pos[i] = n_past + i
        batch.n_seq_id[i] = 1
        batch.seq_id[i][0] = 0
        batch.logits[i] = False

    ret = llama_lib.llama_decode(ctx, batch)
    if ret != 0:
        llama_lib.llama_batch_free(batch)
        raise RuntimeError(f"llama_decode failed with code {ret}")

    llama_lib.llama_batch_free(batch)
    n_past += n_tokens

    # Continue with trailing text and generation
    trailing_text = b"</|extra_0|>\n<|im_end|>\n<|im_start|>assistant\n"
    tr_tokens = llm.tokenize(trailing_text, add_bos=False)
    llm.eval(tr_tokens)
    n_past += len(tr_tokens)

    # Generate response
    generated_tokens = []
    gen_batch = llama_lib.llama_batch_init(1, 0, 1)
    gen_batch.n_tokens = 1
    gen_batch.n_seq_id[0] = 1
    gen_batch.seq_id[0][0] = 0
    gen_batch.logits[0] = True

    print("\n" + "=" * 60)
    print("PYTHIA RESPONSE:")
    print("=" * 60)

    for i in range(300):
        token_id = llm.sample(top_k=40, top_p=0.9, temp=0.1, repeat_penalty=1.1)
        if token_id == llm.token_eos():
            break

        piece = llm.detokenize([token_id]).decode("utf-8", errors="ignore")
        print(piece, end="", flush=True)
        generated_tokens.append(token_id)

        gen_batch.token[0] = token_id
        gen_batch.pos[0] = n_past

        ret = llama_lib.llama_decode(ctx, gen_batch)
        if ret != 0:
            print(f"\n[Decode error: {ret}]")
            break

        n_past += 1

    llama_lib.llama_batch_free(gen_batch)

    response = llm.detokenize(generated_tokens).decode("utf-8", errors="ignore")
    print("\n" + "=" * 60)

    return response


def main():
    print("=" * 60)
    print("ARCA PYTHIA FIRST CONTACT SERVER")
    print("=" * 60)
    print(f"Model: {INSTRUCT_MODEL}")
    print(f"MMProj: {MMPRPOJ_MODEL}")
    print(f"Vector: {VECTOR_FILE}")
    print(f"Port: {PORT}")
    print("=" * 60)

    # Load the vector
    latent_vector = load_latent_vector(VECTOR_FILE)

    # Load the model (use GPU layers for Vulkan)
    # Note: For text-only, mmproj is not strictly required
    print("\nLoading Qwen3-VL model with Vulkan GPU support...")
    llm = llama_cpp.Llama(
        model_path=INSTRUCT_MODEL,
        # mmproj_path=MMPRPOJ_MODEL,  # Commented out - not needed for text-only
        n_gpu_layers=-1,  # Offload all layers to GPU
        main_gpu=0,
        n_ctx=N_CTX,
        embedding=False,
        verbose=False,
    )
    print(f"Model loaded. Embedding dimension: {llm.n_embd()}")

    # Generate response with latent injection
    print("\nInjecting latent vector and generating response...\n")
    response = inject_latent_and_generate(llm, latent_vector, FORMATTED_MSG)

    # Save results
    timestamp = "2026-03-23T10:00:00Z"
    results_content = f"""# Pythia First Contact Results

## Timestamp
{timestamp}

## User Message
{USER_MSG}

## Latent Vector
File: {VECTOR_FILE}
Dimensions: {latent_vector.shape[1]}

## Pythia Response
{response}

---
*Generated via ARCA Latent Space Injection with Qwen3-VL-2B-Instruct*
"""

    with open(RESULTS_FILE, "w") as f:
        f.write(results_content)

    print(f"\nResults saved to: {RESULTS_FILE}")

    # Keep server running for additional requests
    print(f"\nServer ready on port {PORT}")
    print("Press Ctrl+C to stop...")

    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
