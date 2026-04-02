import asyncio
import logging
import sys
import json
import base64
from copaw.app.channels.voice.vultr_relay_client import VultrRelayClient

logging.basicConfig(level=logging.ERROR) # Hush logs for cleaner output

async def test_model(model_name):
    relay_url = "ws://100.86.112.119:8765/ws/live"
    client = VultrRelayClient(relay_url)
    
    print(f"Testing model: {model_name}...")
    
    if not await client.connect():
        return False

    # Custom setup with specific model
    setup_msg = {
        "setup": {
            "model": model_name,
            "generationConfig": {"responseModalities": ["AUDIO"]}
        }
    }
    await client.ws.send(json.dumps(setup_msg))
    
    # Wait for setup rejection or audio
    try:
        # If we get any binary message in the first 3 seconds, it's alive!
        # Or if we get "serverContent"
        while True:
            msg = await asyncio.wait_for(client.ws.recv(), timeout=3.0)
            if isinstance(msg, bytes):
                print(f"  ✅ SUCCESS: Received binary audio for {model_name}")
                return True
            else:
                data = json.loads(msg)
                if "serverContent" in data or "setupComplete" in str(msg): # Some versions send setupComplete
                    print(f"  ✅ SUCCESS: Connection accepted for {model_name}")
                    return True
                if "error" in data:
                    print(f"  ❌ Error for {model_name}: {data['error']}")
                    return False
    except asyncio.TimeoutError:
        # No response? Try sending a prompt
        print(f"  ... No immediate response for {model_name}, sending test prompt...")
        prompt = {"realtimeInput": {"text": {"text": "Please say hello."}}}
        try:
            await client.ws.send(json.dumps(prompt))
            msg = await asyncio.wait_for(client.ws.recv(), timeout=5.0)
            print(f"  ✅ SUCCESS: Got response after prompt for {model_name}")
            return True
        except:
            print(f"  ❌ TIMEOUT/REJECTION for {model_name}")
            return False
    except Exception as e:
        print(f"  ❌ FAILED for {model_name}: {e}")
        return False
    finally:
        await client.close()

async def find_working_model():
    models = [
        "models/gemini-2.0-flash-exp",
        "models/gemini-2.0-flash-live-preview",
        "models/gemini-1.5-flash-8b-latest",
        "models/gemini-3.1-flash-live-preview", # The one the user wants
        "models/gemini-3.1-flash-8b-latest"
    ]
    
    for m in models:
        if await test_model(m):
            print(f"\n🎯 FOUND WORKING MODEL: {m}")
            return m
    return None

if __name__ == "__main__":
    src_path = "/Users/danexall/biomimetics/scripts/copaw/src"
    if src_path not in sys.path:
        sys.path.append(src_path)
    
    asyncio.run(find_working_model())
