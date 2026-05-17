import llama_cpp
import llama_cpp.mtmd_cpp as mtmd_cpp
import ctypes

# Accessing ggml backends via llama_cpp if possible, or just trying names
backends = ["Vulkan", "Vulkan0", "Metal", "CPU"]
for b in backends:
    print(f"Testing backend: {b}")
    # We don't have a direct list_backends in mtmd_cpp yet but we can see if it initializes
