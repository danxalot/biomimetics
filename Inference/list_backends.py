import llama_cpp
import ctypes

# Accessing ggml via llama_cpp's ctypes
# We want to list backends. 
# ggml_backend_dev_count()
# ggml_backend_dev_get(i)
# ggml_backend_dev_name(dev)

try:
    llama = llama_cpp.llama_cpp
    count = llama.ggml_backend_device_count()
    print(f"Found {count} devices:")
    for i in range(count):
        dev = llama.ggml_backend_device_get(i)
        name = llama.ggml_backend_device_name(dev)
        description = llama.ggml_backend_device_description(dev)
        print(f"Device {i}: {name.decode()} ({description.decode()})")
except Exception as e:
    print(f"Error: {e}")
