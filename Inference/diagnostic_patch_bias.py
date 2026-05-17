import gguf
import os

path = "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf"

if not os.path.exists(path):
    print(f"ERROR: File not found at {path}")
    # Try alternative path based on previous turns if necessary
    alt_path = "/Users/danexall/biomimetics/Inference/models/mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf"
    if os.path.exists(alt_path):
        print(f"Found at alternative path: {alt_path}")
        path = alt_path

try:
    reader = gguf.GGUFReader(path)
    found = False
    for tensor in reader.tensors:
        if "patch_embed.proj.bias" in tensor.name or "patch_bias" in tensor.name:
            print(f"PATCH BIAS DETECTED: {tensor.name} | Shape: {tensor.shape} | Type: {tensor.tensor_type.name}")
            found = True
    
    if not found:
        print("No patch bias tensors detected.")
except Exception as e:
    print(f"ERROR during GGUF reading: {e}")
