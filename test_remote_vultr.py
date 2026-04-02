import asyncio
import json
import websockets
import base64
import struct
import math
import sys
import wave
import os

# Vultr Remote Configuration
RELAY_URL = "ws://149.248.32.53:8765/ws/live"
MODEL = "models/gemini-3.1-flash-live-preview"

def calculate_rms(audio_data):
    if not audio_data: return 0
    if len(audio_data) % 2 != 0: audio_data = audio_data[:-1]
    count = len(audio_data) // 2
    if count == 0: return 0
    try:
        samples = struct.unpack(f'<{count}h', audio_data)
        sum_squares = sum(s * s for s in samples)
        return int(math.sqrt(sum_squares / count))
    except Exception:
        return 0

async def run_remote_test():
    print(f"--- 🛑 REMOTE VULTR PROTOCOL TEST ---")
    print(f"Target: {RELAY_URL}\n")
    
    audio_buffer = []
    found_transcripts = []
    
    try:
        print(f"Connecting to {RELAY_URL}...")
        async with websockets.connect(RELAY_URL, open_timeout=30) as ws:
            print("✓ Handshake successful.")
            
            # 1. Setup
            setup_msg = {
                "setup": {
                    "model": MODEL,
                    "generation_config": {"response_modalities": ["AUDIO"]},
                    "input_audio_transcription": {},
                    "output_audio_transcription": {}
                }
            }
            await ws.send(json.dumps(setup_msg))
            print("✓ Setup sent.")
            
            await asyncio.sleep(1)
            
            # 2. Injection: Stream real audio from file
            WAV_PATH = "/Users/danexall/biomimetics/verified_audio.wav"
            if os.path.exists(WAV_PATH):
                print(f"✓ Streaming audio from {WAV_PATH}...")
                with wave.open(WAV_PATH, 'rb') as wf:
                    while True:
                        data = wf.readframes(1024)
                        if not data: break
                        b64_data = base64.b64encode(data).decode('utf-8')
                        msg = {
                            "realtimeInput": {
                                "audio": {
                                    "mime_type": "audio/pcm;rate=16000",
                                    "data": b64_data
                                }
                            }
                        }
                        await ws.send(json.dumps(msg))
                        await asyncio.sleep(0.04)
                print("✓ Audio stream finished.")
                await asyncio.sleep(2)
            else:
                print("⚠ verified_audio.wav not found, sending text fallback...")
                msg = {"realtimeInput": {"text": "Please say 'Test connection'."}}
                await ws.send(json.dumps(msg))
            
            print("✓ Sending prompt to force response...")
            prompt_msg = {
                "realtimeInput": {
                    "text": "Say the words 'REMOTE VULTR RESTORATION SUCCESSFUL' clearly."
                }
            }
            await ws.send(json.dumps(prompt_msg))
            
            print("-" * 75)
            
            timeout = 60.0
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    print("\n--- TIMEOUT ---")
                    break
                    
                try:
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    
                    if isinstance(raw_msg, bytes):
                        # Should be raw audio binary as per our relay patch
                        rms = calculate_rms(raw_msg)
                        audio_buffer.append(raw_msg)
                        # Minimal logging for binary to avoid spam
                        if len(audio_buffer) % 10 == 0:
                            print(f"{'RAW BINARY':<15} | chunk {len(audio_buffer):<34} | rms: {rms}")
                        continue
                    else:
                        data = json.loads(raw_msg)
                    
                    if "serverContent" in data:
                        sc = data["serverContent"]
                        if "modelTurn" in sc:
                            for part in sc["modelTurn"].get("parts", []):
                                if "text" in part:
                                    txt = part["text"]
                                    found_transcripts.append(txt)
                                    print(f"{'PART TEXT':<15} | {txt[:40]:<40} | -")
                                    
                        if sc.get("turnComplete"):
                            print(f"{'TURN':<15} | {'COMPLETE':<40} | -")
                            break
                    
                    if "transcript" in data:
                        txt = data["transcript"]
                        found_transcripts.append(txt)
                        print(f"{'TOP TRANSCRIPT':<15} | {txt[:40]:<40} | -")
                        
                    if "type" in data and data["type"] == "connected":
                        print(f"✓ Relay acknowledged connection: {data.get('message')}")

                except asyncio.TimeoutError:
                    if audio_buffer:
                        break
                    continue
                    
            if audio_buffer:
                print(f"\n✅ SUCCESS: Received {len(b''.join(audio_buffer))} bytes of audio remotely.")
            else:
                print("\n❌ FAILED: No audio received from remote relay.")
                
            if found_transcripts:
                print(f"✅ TRANSCRIPT DATA FOUND: {' '.join(found_transcripts)}")
            else:
                print("❌ FAILED: No transcript received.")
                
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(run_remote_test())
