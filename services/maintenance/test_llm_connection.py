import asyncio
import os
import logging
from main import LLMClient

# Configure logging to see output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test-llm")

async def test_generation():
    print("Initializing LLMClient...")
    # Force the URL to be what we think it is, just in case env var issue
    os.environ["PRIMARY_MODEL_URL"] = "http://llm_gateway:8080/v1"
    
    client = LLMClient()
    print(f"Client initialized. URL: {client.primary_url}")
    
    print("Sending test request...")
    try:
        response, model = await client.generate("Hello, are you working?", system="You represent the system status.")
        print(f"✅ Success!")
        print(f"Model: {model}")
        print(f"Response: {response}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_generation())
