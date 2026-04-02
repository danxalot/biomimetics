import ctypes

import llama_cpp
import llama_cpp.llama_cpp as llama_lib
import numpy as np

# 1. Load the Model (Vulkan backend)
print("Loading Qwen3-VL via Vulkan...")
llm = llama_cpp.Llama(
    model_path="../../models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf",
    n_gpu_layers=-1,  # Offload everything to AMD Radeon
    main_gpu=0,
    n_ctx=4096,
    verbose=False,
)

ctx = llm.ctx

# 2. Load the 2048d Geometric Rotor/Embedding
print("Loading 2048d Pythia vector...")
embd_data = np.load("pythia_expanded_2048d.npy").astype(np.float32)

# Ensure shape is [N_tokens, 2048]
if len(embd_data.shape) == 1:
    embd_data = embd_data.reshape(1, -1)

n_tokens = embd_data.shape[0]  # Should be 1
embd_dim = embd_data.shape[1]  # Must be exactly 2048 for this Qwen model

if embd_dim != llm.n_embd():
    raise ValueError(
        f"Dimension mismatch! Model expects {llm.n_embd()}, but got {embd_dim}."
    )

# 3. Initialize the C-level llama_batch for EMBEDDINGS
# The second argument > 0 tells the C API to allocate the batch.embd pointer
print("Initializing latent batch...")
batch = llama_lib.llama_batch_init(n_tokens, embd_dim, 1)

# 4. Map the numpy array into the C memory space
# We copy the raw bytes from our numpy array directly into the batch's embedding pointer
ctypes.memmove(batch.embd, embd_data.ctypes.data, embd_data.nbytes)

# Set sequence details for the KV cache
batch.n_tokens = n_tokens
for i in range(n_tokens):
    batch.pos[i] = i
    batch.n_seq_id[i] = 1
    batch.seq_id[i][0] = 0
    batch.logits[i] = (
        1 if i == n_tokens - 1 else 0
    )  # Only get logits for the final vector

# 5. Inject the Latent Vector (Decode)
print("Injecting vector into latent space...")
ret = llama_lib.llama_decode(ctx, batch)
if ret != 0:
    raise RuntimeError(f"llama_decode failed with code {ret}")

# Clean up the embedding batch to prevent memory leaks
llama_lib.llama_batch_free(batch)

# 6. Sample the resulting thought (The first token of the response)
print("Vector ingested. Sampling response...")
logits_ptr = llama_lib.llama_get_logits_ith(ctx, n_tokens - 1)
logits = np.ctypeslib.as_array(logits_ptr, shape=(llm.n_vocab(),))

# Greedy sampling for the first token
first_token_id = int(np.argmax(logits))
first_token_str = llm.detokenize([first_token_id]).decode("utf-8", errors="ignore")
print(f"Pythia's first token: {first_token_str}")

# 7. Hand control back to standard generation loop
# Now that the KV cache is primed with your geometry, we can use standard token-by-token generation
generated_tokens = [first_token_id]
current_pos = n_tokens

# Standard auto-regressive loop
for _ in range(50):  # Generate up to 50 tokens
    # Create a standard token batch (embd_dim = 0)
    tok_batch = llama_lib.llama_batch_init(1, 0, 1)
    tok_batch.n_tokens = 1
    tok_batch.token[0] = generated_tokens[-1]
    tok_batch.pos[0] = current_pos
    tok_batch.n_seq_id[0] = 1
    tok_batch.seq_id[0][0] = 0
    tok_batch.logits[0] = 1

    llama_lib.llama_decode(ctx, tok_batch)

    # Sample next
    next_logits_ptr = llama_lib.llama_get_logits_ith(ctx, 0)
    next_logits = np.ctypeslib.as_array(next_logits_ptr, shape=(llm.n_vocab(),))
    next_token_id = int(np.argmax(next_logits))

    llama_lib.llama_batch_free(tok_batch)

    # Stop if EOS
    if next_token_id == llm.token_eos():
        break

    generated_tokens.append(next_token_id)
    current_pos += 1

# Decode final thought
final_text = llm.detokenize(generated_tokens).decode("utf-8", errors="ignore")
print(f"\n--- PYTHIA OUTPUT ---\n{final_text}")
