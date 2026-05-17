import base64
import os
import sys
import traceback

# Add local llama_cpp to path if needed (safety measure)
sys.path.insert(0, "/Users/danexall/biomimetics/llama_cpp_bypass/llama-cpp-python")

try:
    import llama_cpp
    print(f"DEBUG: llama_cpp loaded from {llama_cpp.__file__}")
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Qwen25VLChatHandler
except ImportError as e:
    print(f"ERROR: llama_cpp not found: {e}")
    print(f"PYTHONPATH: {sys.path}")
    sys.exit(1)

# Paths
model_path = os.path.join(os.path.dirname(__file__), "models/Huihui-Qwen3-VL-2B-Instruct-abliterated-Q8_0.gguf")
mmproj_path = os.path.join(os.path.dirname(__file__), "models/mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf")

def run_test():
    if not os.path.exists(model_path):
        print(f"CRITICAL: Model not found at {model_path}")
        return
    if not os.path.exists(mmproj_path):
        print(f"CRITICAL: Projector not found at {mmproj_path}")
        return

    print("="*60)
    print("  Qwen3-VL Vulkan Inference Test")
    print("="*60)

    # Initialize Chat Handler for VL
    # This handler manages the vision projector (CLIP/ViT)
    try:
        print(f"Loading projector: {os.path.basename(mmproj_path)}")
        chat_handler = Qwen25VLChatHandler(clip_model_path=mmproj_path, verbose=True)
    except Exception as e:
        print(f"Failed to initialize Chat Handler: {e}")
        return

    # Force Vulkan only, disable Metal to avoid multi-backend conflict
    os.environ['GGML_METAL'] = 'off'
    # os.environ['MTMD_BACKEND_DEVICE'] = 'CPU'

    # Load Model with GPU offloading
    print("\nInitializing Llama engine...")
    try:
        # GPU MODE: Use n_gpu_layers=-1 for AMD 5500M Vulkan acceleration
        # n_batch is set to 512, but vision tokens will trickle at 64 via mtmd-helper.cpp
        llm = Llama(
            model_path=model_path,
            chat_handler=chat_handler,
            n_gpu_layers=-1, 
            n_ctx=2048,
            n_batch=512,
            n_threads=8,
            verbose=True
        )

        print("\n" + "-"*30)
        print("  Executing Chat Completion")
        print("-"*30)
        
        # Use a local image to verify vision pipeline (bypassing SSL issues)
        image_path = "/Users/danexall/biomimetics/llama_cpp_bypass/llama-cpp-python/vendor/llama.cpp/media/llama0-banner.png"
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
        
        response = llm.create_chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is depicted in this image?"},
                        {"type": "image_url", "image_url": f"data:image/png;base64,{base64_image}"}
                    ]
                }
            ],
            max_tokens=256
        )

        print("\n[MODEL RESPONSE]:")
        print(response["choices"][0]["message"]["content"])
        print("\n[METADATA]:")
        print(f"Usage: {response['usage']}")

    except Exception as e:
        print(f"\nCRITICAL ENGINE FAILURE: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
