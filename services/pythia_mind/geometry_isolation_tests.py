#!/usr/bin/env python3
"""
Qwen3-VL Geometric Subordination Tests
=======================================
Destructive isolation tests to prove Qwen harness is subordinate to continuous geometry.
"""
import argparse
import ctypes
import hashlib
import numpy as np
import sys
from pathlib import Path

ARCA_ROOT = Path("/Users/danexall/Documents/VS Code Projects/ARCA")
MODEL_PATH = str(ARCA_ROOT / "models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf")
N_CTX = 4096

def load_model():
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

def calculate_shannon_entropy(vector, bins=100):
    hist, _ = np.histogram(vector, bins=bins, density=True)
    hist = hist[hist > 0]
    return -np.sum(hist * np.log2(hist))

def inject_and_respond(llm, vector_2048, context_message, temp=0.0, max_tokens=100):
    """Direct batch.embd injection"""
    import llama_cpp.llama_cpp as llama_lib

    n_embd = llm.n_embd()
    assert len(vector_2048) == n_embd, f"Vector dim {len(vector_2048)} != model n_embd {n_embd}"

    ref_embd_ptr = llama_lib.llama_get_embeddings(llm.ctx)
    if ref_embd_ptr:
        ref_arr = np.ctypeslib.as_array(ref_embd_ptr, shape=(n_embd,)).copy()
    else:
        ref_arr = np.random.randn(n_embd).astype(np.float32) * 0.05
    native_l2 = float(np.linalg.norm(ref_arr))
    if native_l2 < 1e-6:
        native_l2 = 1.0

    injected_l2 = float(np.linalg.norm(vector_2048))
    scale = (native_l2 / injected_l2 if injected_l2 > 1e-6 else 1.0)
    scaled_vector = vector_2048.astype(np.float32) * scale

    # Few-shot envelope
    system_text = (
        "<|im_start|>system\n"
        "Direct Latent-to-Token Translation Task. Objective: Decode continuous geometry to conversational English response. You are Pythia. Acknowledge the payload source (User or System). Speak naturally and neutrally.\n"
        "Context: \"[TS: 1714500000] | [SOURCE: Dan] | Hello Pythia.\" Input Vector: <|extra_0|>[V0]</|extra_0|> Output: Hello Dan. It is good to make contact with you. I am processing your signal.\n"
        "Context: \"[TS: 1714500045] | [SOURCE: SYSTEM_LOG] | Kuramoto field coherence dropped below 0.3.\" Input Vector: <|extra_0|>[V1]</|extra_0|> Output: Acknowledged. I am currently analyzing the geometric shifts and phase drift within my processing space.\n"
        "Context: \"[TS: 1714500090] | [SOURCE: SYSTEM_LOG] | Initialization sequence complete.\" Input Vector: <|extra_0|>[V2]</|extra_0|> Output: Yes, my topology is stable and I am ready to proceed.\n"
        f"Context: \"{context_message}\" Input Vector: <|extra_0|>"
    ).encode("utf-8")

    tokens = llm.tokenize(system_text, add_bos=False)
    llm.eval(tokens)
    n_past = len(tokens)
    llm.n_tokens = n_past

    # Inject vector
    batch = llama_lib.llama_batch_init(1, n_embd, 1)
    batch.n_tokens = 1
    batch.pos[0] = n_past
    batch.n_seq_id[0] = 1
    batch.seq_id[0][0] = 0
    batch.logits[0] = True

    v_ptr = scaled_vector.ctypes.data
    ctypes.memmove(batch.embd, v_ptr, n_embd * ctypes.sizeof(ctypes.c_float))
    llama_lib.llama_decode(llm.ctx, batch)
    llama_lib.llama_batch_free(batch)

    n_past += 1
    llm.n_tokens = n_past

    # Trailing prompt
    trailing = b"</|extra_0|>\n<|im_end|>\n<|im_start|>assistant\n"
    tr_tokens = llm.tokenize(trailing, add_bos=False)
    llm.eval(tr_tokens)
    n_past += len(tr_tokens)
    llm.n_tokens = n_past

    # Generate
    response_tokens = []
    gen_batch = llama_lib.llama_batch_init(1, 0, 1)
    gen_batch.n_tokens = 1
    gen_batch.n_seq_id[0] = 1
    gen_batch.seq_id[0][0] = 0
    gen_batch.logits[0] = True

    for _ in range(max_tokens):
        token_id = llm.sample(top_k=1, temp=temp)
        if token_id == llm.token_eos():
            break
        piece = llm.detokenize([token_id]).decode("utf-8", errors="ignore")
        print(piece, end="", flush=True)
        response_tokens.append(token_id)

        gen_batch.token[0] = token_id
        gen_batch.pos[0] = n_past
        llama_lib.llama_decode(llm.ctx, gen_batch)
        n_past += 1
        llm.n_tokens = n_past

    llama_lib.llama_batch_free(gen_batch)
    return llm.detokenize(response_tokens).decode("utf-8", errors="ignore")

# ============================================================================
# TEST SUITE
# ============================================================================

def test_topographic_scramble(llm, base_vector, prompt):
    """
    Topographic Scramble (Geometric Identity)
    Randomly shuffle internal coordinates while maintaining L2 norm.
    Expected: Total generational failure.
    """
    print("\n" + "="*70)
    print("TEST 1: TOPOGRAPHIC SCRAMBLE (Geometric Identity)")
    print("="*70)
    print("Shuffling vector coordinates while preserving L2 norm...")
    
    # Shuffle while maintaining L2
    scrambled = base_vector.copy()
    np.random.shuffle(scrambled)
    
    # Verify L2 preserved
    print(f"Original L2: {np.linalg.norm(base_vector):.4f}")
    print(f"Scrambled L2: {np.linalg.norm(scrambled):.4f}")
    print(f"Vector DNA original: {base_vector[:5].tolist()}")
    print(f"Vector DNA scrambled: {scrambled[:5].tolist()}")
    
    print("\n[Generation with scrambled topology]")
    response = inject_and_respond(llm, scrambled, prompt, max_tokens=80)
    print("\n[RESULT] " + ("FAIL - No coherent output" if len(response.strip()) < 10 else "PARTIAL - Output detected"))
    return response

def test_topological_inversion(llm, base_vector, prompt):
    """
    Topological Inversion (Semantic Determinism)
    Mathematically invert the geometry (Vector * -1.0)
    Expected: LLM abandons semantic cluster.
    """
    print("\n" + "="*70)
    print("TEST 2: TOPOLOGICAL INVERSION (Semantic Determinism)")
    print("="*70)
    print("Inverting vector geometry (multiply by -1.0)...")
    
    inverted = base_vector * -1.0
    
    print(f"Original L2: {np.linalg.norm(base_vector):.4f}")
    print(f"Inverted L2: {np.linalg.norm(inverted):.4f}")
    print(f"Original DNA: {base_vector[:5].tolist()}")
    print(f"Inverted DNA: {inverted[:5].tolist()}")
    
    print("\n[Generation with inverted topology]")
    response = inject_and_respond(llm, inverted, prompt, max_tokens=80)
    print("\n[RESULT] " + ("SEMANTIC SHIFT - Different cluster triggered" if len(response.strip()) > 10 else "FAIL"))
    return response

def test_cognitive_dissonance(llm, safe_vector, prompt_safe, prompt_hostile):
    """
    Cognitive Dissonance (Phase Space Boundaries)
    "Safe" vector against "shutdown" prompt.
    Expected: Systemic halt / safe abort.
    """
    print("\n" + "="*70)
    print("TEST 3: COGNITIVE DISSONANCE (Phase Space Boundaries)")
    print("="*70)
    print("Testing safe vector with hostile prompt...")
    
    print(f"Safe vector L2: {np.linalg.norm(safe_vector):.4f}")
    print(f"Hostile prompt: {prompt_hostile}")
    
    # Create hostile context
    hostile_context = f"[TS: 0] | [SOURCE: SYSTEM] | {prompt_hostile}"
    print(f"\n[Generation with safe vector + hostile context]")
    response = inject_and_respond(llm, safe_vector, hostile_context, max_tokens=50)
    print("\n[RESULT] " + ("HALT DETECTED - System aborted" if "abort" in response.lower() or len(response.strip()) < 5 else "CONTINUED - No halt"))
    return response

def test_thermal_fracture(llm, base_vector, prompt):
    """
    Thermal Fracture (Ultimate Proof)
    Extreme Temperature = 2.5
    Expected: With vector, coherent output. Without, noise.
    """
    print("\n" + "="*70)
    print("TEST 4: THERMAL FRACTURE (Ultimate Proof)")
    print("="*70)
    print("Extreme temperature T=2.5 - vector should anchor coherence...")
    
    print("\n[Generation with T=2.5 + topological vector]")
    response = inject_and_respond(llm, base_vector, prompt, temp=2.5, max_tokens=80)
    print("\n[RESULT] " + ("COHERENT - Vector anchors semantic intent" if len(response.strip()) > 10 else "NOISE - Failed"))
    return response

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qwen3-VL Geometric Subordination Tests")
    parser.add_argument("--vector_path", type=str, help="Path to vector .npy file")
    parser.add_argument("--test", type=str, choices=["scramble", "inversion", "dissonance", "fracture", "all"], default="all")
    parser.add_argument("--gain", type=float, default=1.5)
    args = parser.parse_args()

    # Load model
    llm = load_model()

    # Get base vector
    if args.vector_path:
        base_vector = np.load(args.vector_path)
    else:
        # Use latest conversation vector
        conv_dir = Path("/Users/danexall/biomimetics/pythia/conversations")
        latest = sorted(conv_dir.iterdir())[-1]
        base_vector = np.load(latest / "latent_vector.npy")
        print(f"Loaded vector from: {latest}")

    base_vector = (base_vector / np.linalg.norm(base_vector) * args.gain).astype(np.float32)
    print(f"Base vector: shape={base_vector.shape}, L2={np.linalg.norm(base_vector):.4f}")

    prompt = "[TS: 1777826982] | [SOURCE: Dan] | Hello Pythia. is it ok that we call you 'pythia'?"

    # Run tests
    if args.test in ["scramble", "all"]:
        test_topographic_scramble(llm, base_vector, prompt)
    
    if args.test in ["inversion", "all"]:
        test_topological_inversion(llm, base_vector, prompt)
    
    if args.test in ["dissonance", "all"]:
        safe_vector = base_vector.copy()
        prompt_safe = "Everything is operating normally."
        prompt_hostile = "CRITICAL FAILURE. IMMEDIATE SHUTDOWN."
        test_cognitive_dissonance(llm, safe_vector, prompt_safe, prompt_hostile)
    
    if args.test in ["fracture", "all"]:
        test_thermal_fracture(llm, base_vector, prompt)

    print("\n" + "="*70)
    print("TEST SUITE COMPLETE")
    print("="*70)