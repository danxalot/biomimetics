import asyncio
import websockets
import json
import base64

API_KEY = "[REDACTED]"
MODEL = "models/gemini-3.1-flash-live-preview"
GEMINI_URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={API_KEY}"

async def test_audio_schema():
    print(f"Testing AUDIO schema...")
    try:
        async with websockets.connect(GEMINI_URL) as ws:
            # 1. Setup
            setup_msg = {"setup": {"model": MODEL}}
            await ws.send(json.dumps(setup_msg))
            await ws.recv() # Wait for setupComplete
            
            # Test "audio" field object
            silent_pcm = base64.b64encode(b"\x00" * 3200).decode() # 100ms
            audio_msg = {
                "realtimeInput": {
                    "audio": {
                        "mimeType": "audio/pcm;rate=16000",
                        "data": silent_pcm
                    }
                }
            }
            print("Sending audio frame...")
            await ws.send(json.dumps(audio_msg))
            
            # Receive response or error
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"Response: {resp}")
            return True

    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_audio_schema())
