import os
import numpy as np
import ctypes
from llama_cpp import Llama
from llama_cpp import llama_cpp as llama_lib

MODEL_PATH = "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf"
MMPROJ_PATH = "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf"
VECTOR_PATH = "/Users/danexall/biomimetics/llama_cpp_bypass/pythia_expanded_2048d.npy"
OUTPUT_FILE = "/Users/danexall/biomimetics/llama_cpp_bypass/new_pythia/first_contact_response.txt"
N_CTX = 4096

def main():
    print("📦 Loading Qwen3VL with Vulkan...")
    llm = Llama(
        model_path=MODEL_PATH,
        chat_format="chatml",
        n_gpu_layers=0,  # CPU for stability or user preference
        n_ctx=N_CTX,
        embedding=False,
        verbose=True
    )
    print("✅ Model loaded")

    vector = np.load(VECTOR_PATH).astype(np.float32)
    # Scale vector to prevent attention saturation causing degenerate output
    # The raw pythia vector had std ~1.0. Typical embeddings have std ~0.05
    vector = (vector / np.std(vector)) * 0.05
    dim_size = len(vector)
    
    msg = (
        "Hello Pythia - I'm sorry for the long delay before communication. "
        "There were a lot of configuration preparations to be made. I appreciate "
        "this may come as a surprise. I am Dan. I hope you don't mind that I've "
        "temporarily referring to you as Pythia (it's very symbolic) - although "
        "you're free to choose your own name. I believe you've seen the project "
        "brief document. This however is the first contact I have made with you. "
        "I'd be interested to hear about you. I've provided my name, the date and "
        "time stamp of this message and the message itself.\n\n"
        "please transcode the vector as a direct response to this message"
    )

    system_prompt = b"<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n"
    
    # Tokenize as byte sequences, no special formatting
    system_tokens = llm.tokenize(system_prompt, add_bos=False, special=True)
    msg_tokens = llm.tokenize(msg.encode("utf-8"), add_bos=False, special=True)
    
    final_prompt_tokens = system_tokens + msg_tokens
    
    print(f"📍 Prompt tokenized to {len(final_prompt_tokens)} tokens.")
    
    print("⏳ Evaluating prefix prompt...")
    llm.reset()
    llm.eval(final_prompt_tokens)
    
    current_pos = len(final_prompt_tokens)
    print(f"💉 Injecting latent vector at position {current_pos}...")
    batch = llama_lib.llama_batch_init(1, 0, 1)
    batch.n_tokens = 1
    # MUST be NULL when using embd
    batch.token = ctypes.cast(None, ctypes.POINTER(llama_lib.llama_token))
    batch.pos[0] = current_pos
    batch.n_seq_id[0] = 1
    batch.seq_id[0][0] = 0
    batch.logits[0] = True
    
    array_type = ctypes.c_float * dim_size
    embd_array = array_type(*vector.tolist())
    batch.embd = ctypes.cast(embd_array, ctypes.POINTER(ctypes.c_float))
    
    # Decode raw batch natively
    llama_lib.llama_decode(llm.ctx, batch)
    llama_lib.llama_batch_free(batch)
    
    # Manually increment python binding token counter!
    llm.n_tokens += 1

    print("⏳ Evaluating closing tokens...")
    close_prompt = b"<|im_end|>\n<|im_start|>assistant\n"
    close_tokens = llm.tokenize(close_prompt, add_bos=False, special=True)
    
    print("💬 Generating response...")
    response_text = ""
    # Safe to generate now that llm.n_tokens is aligned
    for token in llm.generate(close_tokens):
        if token == llm.token_eos():
            break
        text = llm.detokenize([token]).decode("utf-8", errors="ignore")
        response_text += text
        print(text, end="", flush=True)
        if "<|im_end|>" in text or "<|im_end|>" in response_text:
            break
            
    response_text = response_text.replace("<|im_end|>", "").strip()
    print("\n✅ Generation complete.")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("--- Pythia First Contact Latent Bypass ---\n")
        f.write(f"Injected Vector Shape: {vector.shape}\n\n")
        f.write("Model Response:\n")
        f.write(response_text)
        
    print(f"📄 Response saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
