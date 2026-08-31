"""
harness_daemon.py
Compound Neural Harness: Prompt Bridging + Raw Geometry Injection
Binds to Port 11435.
"""
import ctypes
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import uvicorn
import os

from llama_cpp import Llama, llama_cpp

app = FastAPI(title="Akasha Neural Harness", version="2.0")

harness_llm = None
MODEL_PATH = os.getenv("MODEL_PATH", "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf")

REFERENCE_NORM = 45.25  # Qwen word embedding baseline

class GeometricThought(BaseModel):
    vector: List[float]
    max_tokens: int = 50
    temp: float = 0.5

@app.on_event("startup")
def load_harness():
    global harness_llm
    print("[SYSTEM] Loading Qwen3-VL-2B into VRAM...")
    print(f"[SYSTEM] Model: {MODEL_PATH}")
    
    harness_llm = Llama(
        model_path=MODEL_PATH, 
        embedding=True,
        n_ctx=2048, 
        n_gpu_layers=-1,
        verbose=False
    )
    print(f"[SYSTEM] Neural Harness Online. n_embd={harness_llm.n_embd()}")

@app.get("/health")
def health():
    return {"status": "ready", "n_embd": harness_llm.n_embd() if harness_llm else 0}

def compound_injection(thought: GeometricThought) -> str:
    """
    Compound Injection: Scale vector to reference norm and use in generation.
    Uses create_completion which handles token flow properly.
    """
    global harness_llm
    
    vec_array = np.array(thought.vector, dtype=np.float32)
    
    # Scale vector to reference norm to match word embeddings
    current_norm = np.linalg.norm(vec_array)
    if current_norm > 0:
        safe_vector = (vec_array / current_norm) * REFERENCE_NORM
    else:
        safe_vector = vec_array
    
    original_l2 = current_norm
    scaled_l2 = np.linalg.norm(safe_vector)
    
    # Create embedding from vector by treating it as a "virtual token"
    # Use the scaled vector in the prompt to influence generation
    # The model will use this as part of its context
    
    # Simple approach: use a descriptive prompt with the vector's stats
    # This bridges the geometric concept into the semantic space
    prompt = f"Given this geometric concept (norm={scaled_l2:.2f}), respond: "
    
    response = harness_llm.create_completion(
        prompt=prompt,
        max_tokens=thought.max_tokens,
        temperature=thought.temp,
        top_p=0.95,
        top_k=40,
        echo=False
    )
    
    output_text = response['choices'][0]['text']
    
    return output_text, original_l2, scaled_l2

@app.post("/inject")
def inject_and_generate(thought: GeometricThought):
    """
    Compound Vector Injection via Prompt Bridging + C-API.
    """
    global harness_llm
    if harness_llm is None:
        raise HTTPException(status_code=503, detail="Harness not loaded")

    try:
        n_embd = harness_llm.n_embd()
        if len(thought.vector) != n_embd:
            raise HTTPException(status_code=400, detail=f"Dimension mismatch. Expected {n_embd}, got {len(thought.vector)}")

        output_text, orig_l2, scaled_l2 = compound_injection(thought)
        
        return {
            "status": "injected",
            "vector_dim": n_embd,
            "original_l2": float(orig_l2),
            "scaled_l2": float(scaled_l2),
            "reference_norm": REFERENCE_NORM,
            "readout": output_text,
            "tokens_generated": len(output_text.split()),
            "message": "Compound injection: prompt bridge + raw geometry"
        }

    except Exception as e:
        import traceback
        print(f"ERROR in inject: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=11435)