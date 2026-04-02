import asyncio
import json
import websockets
import base64
import struct
import math
import sys
import os

# Vultr Relay Configuration
RELAY_URL = "ws://100.86.112.119:8765/ws/live"
MODEL = "models/gemini-3.1-flash-live-preview"

async def debug_e2e_diagnostic():
    print(f"--- 🛑 PROTOCOL DEBUG: E2E VERIFICATION ---")
    print(f"Target Relay: {RELAY_URL}\n")
    
    try:
        async with websockets.connect(RELAY_URL) as ws:
            print("✓ Connection successful.")
            
            # Setup message
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
            
            # Injection prompt
            instruction_msg = {
                "realtimeInput": {
                    "text": "Please say the exact phrase 'Test complete' loudly and clearly."
                }
            }
            await ws.send(json.dumps(instruction_msg))
            print("✓ Injection prompt sent.")
            
            print("\n" + "="*80)
            print(f"{'TYPE':<10} | {'SIZE':<10} | {'CONTENT PREVIEW'}")
            print("="*80)
            
            timeout = 10.0
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    print("\n--- DEBUG TIMEOUT ---")
                    break
                    
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    
                    if isinstance(msg, bytes):
                        # PEEK: Is this JSON or binary?
                        is_json = False
                        try:
                            json_text = msg.decode('utf-8')
                            if json_text.strip().startswith('{'):
                                is_json = True
                                print(f"{'BINARY':<10} | {len(msg):<10} | [JSON-IN-BINARY]")
                                if len(msg) > 1000:
                                    with open("debug_resp.json", "w") as f:
                                        f.write(json_text)
                                    print("✓ Captured large JSON to debug_resp.json")
                        except:
                            pass
                            
                        if not is_json:
                            # Actually audio?
                            print(f"{'BINARY':<10} | {len(msg):<10} | [RAW BYTES] {msg[:20].hex()}...")
                    else:
                        print(f"{'TEXT':<10} | {len(msg):<10} | {msg[:80]}...")
                        
                except asyncio.TimeoutError:
                    continue
                    
    except Exception as e:
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(debug_e2e_diagnostic())
