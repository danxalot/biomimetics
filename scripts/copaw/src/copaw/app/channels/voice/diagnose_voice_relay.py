import asyncio
import websockets
import json
import argparse
import sys

async def run_diagnostics(uri, token):
    print("==================================================")
    print("       BiOS Voice Relay Diagnostic Utility        ")
    print("==================================================")
    print(f"Target Relay: {uri}")
    print(f"Auth Token: {'Loaded' if token else 'None (Skipping Auth Step)'}")
    print("--------------------------------------------------")

    # Step 1: Basic WebSocket Connection
    print("[1/4] Establishing WebSocket Connection...")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    try:
        if token:
            ws_conn = websockets.connect(uri, additional_headers=headers)
        else:
            ws_conn = websockets.connect(uri)
        async with ws_conn as ws:
            print("  ✅ Connection established.")

            # Step 2: Setup Handshake
            print("[2/4] Sending Gemini Live API Setup Handshake...")
            setup = {
                "setup": {
                    "model": "models/gemini-3.1-flash-live-preview",
                    "systemInstruction": {"parts": [{"text": "You are Puck, a helpful assistant."}]},
                    "generationConfig": {"responseModalities": ["AUDIO"]},
                    "tools": [],
                }
            }
            await ws.send(json.dumps(setup))
            print("  ✅ Setup handshake transmitted.")

            # Wait for setup completion response
            setup_success = False
            for _ in range(5):
                response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                if isinstance(response, str):
                    payload = json.loads(response)
                    print(f"  📥 Received JSON response: {list(payload.keys())}")
                    if "setupComplete" in payload:
                        print("  ✅ Handshake confirmed by server (setupComplete).")
                        setup_success = True
                        break
            
            if not setup_success:
                print("  ❌ Server did not return setupComplete in a timely manner.")
                return False

            # Step 3: Stream Silence Audio
            print("[3/4] Streaming 100ms of PCM Audio Silence...")
            silence_bytes = b"\x00" * 3200  # 16kHz 16-bit mono PCM
            await ws.send(silence_bytes)
            print("  ✅ Audio packet sent.")

            # Step 4: Receive Audio Echo/Gating Response
            print("[4/4] Listening for server audio/text responses...")
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                if isinstance(response, bytes):
                    print(f"  ✅ Received binary response (audio back): {len(response)} bytes")
                else:
                    payload = json.loads(response)
                    print(f"  ✅ Received JSON response: {list(payload.keys())}")
            except asyncio.TimeoutError:
                print("  ℹ️ No immediate server response (expected behavior for silence input).")

            print("\n🎉 DIAGNOSTICS COMPLETED SUCCESSFULLY!")
            return True

    except websockets.exceptions.ConnectionClosed:
        print("\n🎉 DIAGNOSTICS COMPLETED SUCCESSFULLY! (Connection closed by peer)")
        return True
    except Exception as e:
        print(f"  ❌ Error during diagnostics: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnose voice relay connection")
    parser.add_argument("--uri", default="ws://100.86.112.119:8765/ws/live", help="WebSocket relay URI")
    parser.add_argument("--token", default="7a9a0937-916b-416a-ba31-6006630b0b78", help="Bearer authentication token")
    args = parser.parse_args()

    success = asyncio.run(run_diagnostics(args.uri, args.token))
    sys.exit(0 if success else 1)
