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
RELAY_URL = "ws://100.86.112.119:8765/ws/live"
MODEL = "models/gemini-3.1-flash-live-preview"

def calculate_rms(audio_data):
    """Manual RMS calculation for 16-bit PCM (little-endian) to support Python 3.13+."""
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

async def run_e2e_diagnostic():
    print(f"--- 🛑 CRITICAL DIRECTIVE: E2E AUDIO VERIFICATION ---")
    print(f"Target Relay: {RELAY_URL}")
    print(f"Model: {MODEL}\n")
    
    captured_audio = []
    transcripts = []
    
    try:
        async with websockets.connect(RELAY_URL) as ws:
            print("✓ Connection successful.")
            
            # Phase 1: Setup
            setup_msg = {
                "setup": {
                    "model": MODEL,
                    "generationConfig": {
                        "responseModalities": ["AUDIO"]
                    }
                }
            }
            await ws.send(json.dumps(setup_msg))
            print("✓ Setup sent.")
            
            # Give relay a moment
            await asyncio.sleep(1)
            
            # Phase 2: Instruction prompt
            # According to User Summary, it should be a scalar text field.
            instruction_msg = {
                "realtimeInput": {
                    "text": "Please say the exact phrase 'Test complete' loudly and clearly."
                }
            }
            await ws.send(json.dumps(instruction_msg))
            print("✓ Injection prompt sent (SCALAR): 'Please say the exact phrase 'Test complete' loudly and clearly.'")
            
            print("\n" + "="*60)
            print(f"{'CHUNK SIZE':<15} | {'AUDIOOP.RMS (EQUIV)':<20} | {'EVENT'}")
            print("="*60)
            
            audio_count = 0
            timeout = 15.0
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    print("\n--- TIMEOUT (15s) REACHED ---")
                    break
                    
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    
                    if isinstance(msg, bytes):
                        # Raw binary audio from relay
                        rms = calculate_rms(msg)
                        print(f"{len(msg):<15} | {rms:<20} | [🔊 AUDIO CHUNK]")
                        captured_audio.append(msg)
                        audio_count += len(msg)
                    else:
                        data = json.loads(msg)
                        
                        # Handle serverContent (Embedded Audio in JSON)
                        if "serverContent" in data:
                            sc = data["serverContent"]
                            if "modelTurn" in sc:
                                for part in sc["modelTurn"].get("parts", []):
                                    audio_bytes = None
                                    if "inlineData" in part:
                                        audio_bytes = base64.b64decode(part["inlineData"]["data"])
                                    elif "audio" in part:
                                        audio_bytes = base64.b64decode(part["audio"]["data"])
                                    
                                    if audio_bytes:
                                        rms = calculate_rms(audio_bytes)
                                        print(f"{len(audio_bytes):<15} | {rms:<20} | [🔊 SERVER CONTENT AUDIO]")
                                        captured_audio.append(audio_bytes)
                                        audio_count += len(audio_bytes)
                            
                            if sc.get("turnComplete"):
                                print(f"{'-'*15:<15} | {'-'*20:<20} | [✓ TURN COMPLETE]")
                                break
                        
                        # Handle Side-channel Transcript (Relay-specific metadata)
                        if data.get("type") == "voice_events" and data.get("event_type") == "transcript":
                            text = data.get("text", "")
                            transcripts.append(text)
                            print(f"{'-'*15:<15} | {'-'*20:<20} | [📝 TRANSCRIPT: {text}]")

                        # Handle Errors
                        if "error" in data:
                            print(f"\n❌ RELAY-REPORTED ERROR: {data['error']}")
                            break
                            
                except asyncio.TimeoutError:
                    if audio_count > 0:
                        print("\nStream idle. Verification complete.")
                        break
                    continue
                    
            print("="*60)
            
            if audio_count > 0:
                print(f"\n✅ SUCCESS: Captured {audio_count} total bytes of audio data.")
                if transcripts:
                    print(f"✅ INTELLIGIBILITY VERIFICATION: Relay side-channel transcript confirmed model response: '{' '.join(transcripts)}'")
                else:
                    print("⚠️ WARNING: Audio data detected, but no transcript found. Manual listening required.")
                
                # Save to WAV
                output_file = "captured_proof_audio.wav"
                with wave.open(output_file, "wb") as f:
                    f.setnchannels(1)
                    f.setsampwidth(2)
                    f.setframerate(24000)
                    f.writeframes(b"".join(captured_audio))
                print(f"✓ Audio verification file saved to: {os.path.abspath(output_file)}")
            else:
                print("\n❌ CRITICAL FAILURE: ZERO data returned from server.")
                
    except Exception as e:
        print(f"\n❌ E2E TEST FAILED TO EXECUTE: {e}")

if __name__ == "__main__":
    asyncio.run(run_e2e_diagnostic())
