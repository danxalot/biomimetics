import os
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from llama_cpp import Llama
from llama_cpp import llama_cpp as llama_lib
import numpy as np
import ctypes

app = FastAPI()

MODEL_PATH = "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf"
MMPROJ_PATH = "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf"
VECTOR_PATH = "/Users/danexall/biomimetics/llama_cpp_bypass/pythia_expanded_2048d.npy"
N_CTX = 4096

print(f"📦 Loading Qwen3VL with mmproj (Vulkan)...")
# Note: mmproj requires llama-cpp-python vision support, but for typical use we can pass chat_handler or load basic if available
# The standard llama_cpp.Llama does not take mmproj directly unless using LlamaVision/chat_handler
# However, we are making a direct latent injection, so we can just load the LLM normally.
llm = Llama(
    model_path=MODEL_PATH,
    chat_format="chatml",
    n_gpu_layers=0, # CPU-only to avoid Metal ggml_metal_synchronize crash
    n_ctx=N_CTX,
    embedding=False,
    verbose=True
)
print("✅ Model loaded")

@app.post("/latent_bypass")
def latent_bypass():
    vector = np.load(VECTOR_PATH).astype(np.float32)
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
    system_tokens = llm.tokenize(system_prompt, add_bos=False, special=True)
    msg_tokens = llm.tokenize(msg.encode("utf-8"), add_bos=False, special=True)
    
    # We want the vector at index 2048.
    # Total prefix length before vector = 2048
    target_length = 2048
    current_length = len(system_tokens) + len(msg_tokens)
    pad_len = target_length - current_length
    
    if pad_len < 0:
        return {"error": "Message too long"}
        
    pad_token = llm.tokenize(b" ", add_bos=False)[0]
    padding = [pad_token] * pad_len
    
    final_prompt_tokens = system_tokens + padding + msg_tokens
    
    print(f"📍 Prompt tokenized perfectly to {len(final_prompt_tokens)} tokens.")
    
    # Ensure length is exactly 2048
    assert len(final_prompt_tokens) == 2048
    
    # 1. Evaluate prefix
    print("⏳ Evaluating prefix prompt...")
    llm.reset()
    llm.eval(final_prompt_tokens)
    
    # 2. Inject vector at index 2048
    print("💉 Injecting latent vector...")
    batch = llama_lib.llama_batch_init(1, 0, 1)
    batch.n_tokens = 1
    # MUST be NULL when using embd
    batch.token = ctypes.cast(None, ctypes.POINTER(llama_lib.llama_token))
    batch.pos[0] = 2048
    batch.n_seq_id[0] = 1
    batch.seq_id[0][0] = 0
    batch.logits[0] = True
    
    # Apply vector
    array_type = ctypes.c_float * dim_size
    embd_array = array_type(*vector.tolist())
    batch.embd = ctypes.cast(embd_array, ctypes.POINTER(ctypes.c_float))
    
    llama_lib.llama_decode(llm.ctx, batch)
    llama_lib.llama_batch_free(batch)
    
    # 3. Add closing tokens
    print("⏳ Evaluating closing tokens...")
    close_prompt = b"<|im_end|>\n<|im_start|>assistant\n"
    close_tokens = llm.tokenize(close_prompt, add_bos=False, special=True)
    
    # 4. Generate response
    print("💬 Generating response...")
    response = ""
    for token in llm.generate(close_tokens):
        if token == llm.token_eos():
            break
        text = llm.detokenize([token]).decode("utf-8", errors="ignore")
        response += text
        if "<|im_end|>" in text or "<|im_end|>" in response:
            break
            
    print(f"\nResponse:\n{response}")
    return {"status": "success", "response": response.replace("<|im_end|>", "").strip()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=11435)
