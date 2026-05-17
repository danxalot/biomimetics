import gguf
import os

path = "/Users/danexall/Documents/VS Code Projects/ARCA/models_optimized/mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf"

if not os.path.exists(path):
    # Try the alternative path used in the run script
    path = "/Users/danexall/biomimetics/Inference/models/mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf"

print(f"Analyzing: {path}")
try:
    reader = gguf.GGUFReader(path)
    print(f"Total tensors: {len(reader.tensors)}")
    found = False
    for tensor in reader.tensors:
        # Search for any bias or patch related tensors
        name_lower = tensor.name.lower()
        if "bias" in name_lower or "patch" in name_lower:
            print(f"MATCH: {tensor.name} | Shape: {tensor.shape} | Type: {tensor.tensor_type.name}")
            found = True
    
    if not found:
        print("No 'bias' or 'patch' tensors found in this file.")
        # Print first 10 tensors to see naming convention
        print("\nFirst 10 tensors:")
        for i, tensor in enumerate(reader.tensors[:10]):
            print(f"{i}: {tensor.name}")
except Exception as e:
    print(f"Error: {e}")
