import sys
import os
import asyncio
from tools import geometry_vae, vigor_grounding, local_vision

async def test_tools():
    model_dir = "/app/models"
    print(f"--- Verifying Local Vision Tool (GLM-4.6V) [Models Dir: {model_dir}] ---")
    try:
        local_vision.initialize_tool(model_dir)
        print("✅ Local Vision Tool initialized (Model loaded).")
        # Optional: Run a small inference if you want to be sure
        # res = await local_vision.query_local_vision_model("test", "Hello", "chat_model")
        # print(f"Inference result: {res}")
    except Exception as e:
        print(f"❌ Local Vision Tool failed: {e}")

    print("\n--- Verifying Vigor Grounding Tool (Validation) ---")
    try:
        vigor_grounding.initialize_tool()
        # This will fail if LLM Gateway is not up, but tool load should work
        print("✅ Vigor Grounding Tool initialized.")
    except Exception as e:
        print(f"❌ Vigor Grounding Tool failed: {e}")

    print("\n--- Verifying Geometry VAE Tool (Geometry) ---")
    try:
        geometry_vae.initialize_tool(model_dir)
        print("✅ Geometry VAE Tool initialized.")
    except Exception as e:
        print(f"⚠️ Geometry VAE Tool failed (Expected if weights missing): {e}")

if __name__ == "__main__":
    asyncio.run(test_tools())
