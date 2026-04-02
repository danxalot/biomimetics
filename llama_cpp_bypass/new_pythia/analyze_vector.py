import numpy as np
from llama_cpp import Llama
import ctypes

MODEL_PATH = "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf"
VECTOR_PATH = "/Users/danexall/biomimetics/llama_cpp_bypass/pythia_expanded_2048d.npy"

llm = Llama(
    model_path=MODEL_PATH,
    vocab_only=False,
    n_gpu_layers=0,
    verbose=False
)

pythia_vec = np.load(VECTOR_PATH).astype(np.float32)

print(f"Pythia Vector - Mean: {np.mean(pythia_vec):.4f}, Std: {np.std(pythia_vec):.4f}, Min: {np.min(pythia_vec):.4f}, Max: {np.max(pythia_vec):.4f}, L2 Norm: {np.linalg.norm(pythia_vec):.4f}")

# Let's get the embedding of a normal token
token = llm.tokenize(b" Hello")[0]
# To get the embedding, we can just look at the embedding matrix layer if it's exposed,
# or we can evaluate and get the logits, but Llama python binding has metadata.
# We can't easily extract embeddings using llama-cpp-python without embedding=True, but 
# let's just evaluate it and see the output states if possible, or just generate a random unit vector for comparison
try:
    print("\nFetching token embedding...")
    llm = Llama(model_path=MODEL_PATH, embedding=True, n_gpu_layers=0, verbose=False)
    normal_embd = np.array(llm.embed("Hello"))
    print(f"Normal Token - Mean: {np.mean(normal_embd):.4f}, Std: {np.std(normal_embd):.4f}, Min: {np.min(normal_embd):.4f}, Max: {np.max(normal_embd):.4f}, L2 Norm: {np.linalg.norm(normal_embd):.4f}")
except Exception as e:
    print(f"Could not get normal token embedding: {e}")

