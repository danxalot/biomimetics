import asyncio
import json
import websockets
import base64
import struct
import math
import sys
import wave
import os

# Vultr Relay Configuration
RELAY_URL = "ws://127.0.0.1:8765/ws/live"
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

async def run_reconstructed_test():
    print(f"--- 🛑 RECONSTRUCTED PROTOCOL TEST ---")
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
                    # Send header-less chunks
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
                        await asyncio.sleep(0.04) # Simulating real-time
                print("✓ Audio stream finished.")
                await asyncio.sleep(2) # Wait for Gemini to process
            else:
                print("⚠ verified_audio.wav not found, sending text fallback...")
                msg = {"realtimeInput": {"text": "Please say 'Test'."}}
                await ws.send(json.dumps(msg))
            
            # 3. Add a text prompt to force a response (always)
            print("✓ Sending prompt to force response...")
            prompt_msg = {
                "realtimeInput": {
                    "text": "Say the words 'RESTORATION SUCCESSFUL' clearly."
                }
            }
            await ws.send(json.dumps(prompt_msg))
            
            # 4. Listen
            print("-" * 75)
            
            timeout = 30.0
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    print("\n--- TIMEOUT ---")
                    break
                    
                try:
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    
                    # Ensure we have a JSON string even if delivered as bytes
                    if isinstance(raw_msg, bytes):
                        try:
                            json_str = raw_msg.decode('utf-8')
                            data = json.loads(json_str)
                        except:
                            # True binary
                            rms = calculate_rms(raw_msg)
                            print(f"{'RAW BINARY':<15} | {len(raw_msg):<40} | {rms}")
                            audio_buffer.append(raw_msg)
                            continue
                    else:
                        data = json.loads(raw_msg)
                    
                    # LOG ALL KEYS for discovery
                    keys = list(data.keys())
                    
                    # 3. Process JSON
                    if "serverContent" in data:
                        sc = data["serverContent"]
                        
                        # Check for inputTranscription (new schema)
                        if "inputTranscription" in sc:
                            it = sc["inputTranscription"]
                            print(f"{'INPUT TRANS':<15} | {it.get('text', '')[:40]:<40} | -")
                        
                        # Extract Audio/Text from modelTurn
                        if "modelTurn" in sc:
                            for part in sc["modelTurn"].get("parts", []):
                                b64_audio = None
                                if "inlineData" in part:
                                    b64_audio = part["inlineData"].get("data")
                                elif "audio" in part:
                                    b64_audio = part.get("audio")
                                
                                if b64_audio:
                                    audio_bytes = base64.b64decode(b64_audio)
                                    rms = calculate_rms(audio_bytes)
                                    print(f"{'AUDIO CHUNK':<15} | {len(audio_bytes):<40} | {rms}")
                                    audio_buffer.append(audio_bytes)
                                
                                # Extract Transcript from part
                                if "text" in part:
                                    txt = part["text"]
                                    found_transcripts.append(txt)
                                    print(f"{'PART TEXT':<15} | {txt[:40]:<40} | -")
                                    
                        if sc.get("turnComplete"):
                            print(f"{'TURN':<15} | {'COMPLETE':<40} | -")
                            break
                    
                    # Top level fields
                    if "transcript" in data:
                        txt = data["transcript"]
                        found_transcripts.append(txt)
                        print(f"{'TOP TRANSCRIPT':<15} | {txt[:40]:<40} | -")
                        
                    if "usageMetadata" in data:
                        # Skip verbose usage log
                        pass
                    
                    # Discover unknown fields
                    for k in data:
                        if k not in ["serverContent", "usageMetadata", "transcript"]:
                            print(f"{'DISC: ' + k:<15} | {str(data[k])[:40]:<40} | -")

                except asyncio.TimeoutError:
                    if audio_buffer:
                        break
                    continue
                    
            if audio_buffer:
                print(f"\n✅ SUCCESS: Reconstructed {len(b''.join(audio_buffer))} bytes of audio.")
                with wave.open("verified_audio.wav", "wb") as f:
                    f.setnchannels(1)
                    f.setsampwidth(2)
                    f.setframerate(24000)
                    f.writeframes(b"".join(audio_buffer))
                print(f"✓ WAV saved to: {os.path.abspath('verified_audio.wav')}")
            else:
                print("\n❌ FAILED: No audio extracted from JSON.")
                
            if found_transcripts:
                print(f"✅ TRANSCRIPT DATA FOUND: {' '.join(found_transcripts)}")
            else:
                print("❌ FAILED: No transcript extracted from JSON.")
                
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(run_reconstructed_test())
