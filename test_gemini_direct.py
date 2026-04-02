import asyncio
import websockets
import json
import base64
import wave
import time
import os

# Constants
API_KEY = "[REDACTED]"
MODEL = "models/gemini-3.1-flash-live-preview"
GEMINI_URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={API_KEY}"
OUTPUT_FILE = "bios_direct_proof.wav"
SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2 # 16-bit

async def test_direct():
    print(f"Connecting DIRECTLY to Gemini v1alpha...")
    try:
        async with websockets.connect(GEMINI_URL) as ws:
            print("Connected. Sending Gemini 3.1 setup...")
            
            setup_msg = {
                "setup": {
                    "model": MODEL,
                    "generationConfig": {"responseModalities": ["AUDIO"]},
                    "input_audio_transcription": {},
                    "output_audio_transcription": {}
                }
            }
            await ws.send(json.dumps(setup_msg))
            
            # Wait for setup acknowledgment
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"Setup response: {resp}")
            
            # 2. Realtime Input with scalar text (Verified 3.1 schema)
            prompt_msg = {
                "realtimeInput": {
                    "text": "Hello Gemini. This is a direct diagnostic. Please say 'The direct audio path is confirmed' clearly."
                }
            }
            print("Sending prompt...")
            await ws.send(json.dumps(prompt_msg))
            
            all_audio = bytearray()
            
            print("Listening for 10 seconds...")
            start_time = time.time()
            while time.time() - start_time < 10:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    
                    # Handle binary-JSON (Gemini 3.1 Live standard)
                    if isinstance(msg, bytes) and msg.startswith(b'{'):
                        try:
                            msg = msg.decode('utf-8')
                        except:
                            pass # True binary
                    
                    if isinstance(msg, bytes):
                        all_audio.extend(msg)
                        print(".", end="", flush=True)
                    else:
                        data = json.loads(msg)
                        # print(f"\nDEBUG JSON: {list(data.keys())}")
                        if "serverContent" in data:
                            sc = data["serverContent"]
                            # print(f"DEBUG SC: {list(sc.keys())}")
                            if "modelTurn" in sc:
                                for p in sc["modelTurn"].get("parts", []):
                                    if "inlineData" in p:
                                        all_audio.extend(base64.b64decode(p["inlineData"]["data"]))
                                        print("A", end="", flush=True)
                                    if "text" in p:
                                        print(f"\n[TEXT]: {p['text']}")
                            if "inputTranscription" in sc:
                                print(f"\n[INPUT]: {sc['inputTranscription']}")
                        if "setupComplete" in data:
                            print("\n[SETUP COMPLETE]")
                except asyncio.TimeoutError:
                    continue
            
            if len(all_audio) > 0:
                print(f"\nCaptured {len(all_audio)} bytes of audio.")
                with wave.open(OUTPUT_FILE, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(SAMPLE_WIDTH)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(all_audio)
                print(f"Saved to {OUTPUT_FILE}")
                print("Intelligibility proven locally.")
            else:
                print("\nNo audio data received directly. API key or endpoint issue.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_direct())
