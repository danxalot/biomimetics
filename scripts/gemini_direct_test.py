import asyncio
import json
import ssl
import certifi
import websockets
from websockets.asyncio.client import connect as ws_connect

# DIRECT BYPASS TEST: Targeting Google Upstream Directly
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.creds import get_first  # noqa: E402

API_KEY = get_first("google-ai-studio") or get_first("gemini")
if not API_KEY:
    raise SystemExit("gemini/google-ai-studio key missing from credentials server")
URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={API_KEY}"

async def test_direct_bypass():
    print(f"--- [DIAGNOSTIC] DIRECT GEMINI HANDSHAKE TEST ---")
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        async with ws_connect(URL, ssl=ssl_context) as ws:
            print("✅ TCP/TLS Handshake to Google: SUCCESS.")
            setup_payload = {
                "setup": {
                    "model": "models/gemini-2.0-flash-exp",
                    "generationConfig": {
                        "responseModalities": ["AUDIO"]
                    }
                }
            }
            print(f"📤 Sending Setup Frame: {json.dumps(setup_payload)}")
            await ws.send(json.dumps(setup_payload))
            print("🕒 Waiting for Google response...")
            try:
                # Wait for any incoming messages
                async for message in ws:
                    print(f"📥 Received from Google: {message}")
                    if "setupComplete" in message:
                        print("🎉 [RESULT] Handshake STABILIZED. The 1006 is definitely the Vultr Relay Server.")
                        break
                    # Catch and log JSON error frames
                    try:
                        data = json.loads(message)
                        if "error" in data:
                            print(f"❌ [TRANSIT] Error Frame Received: {data['error']}")
                    except:
                        pass
            except websockets.exceptions.ConnectionClosed as e:
                print(f"❌ [RESULT] Connection Closed by Google: Code {e.code} ({e.reason})")
                if e.code == 1006:
                    print("🔍 [ANALYSIS] 1006 Reproduced Locally. The Payload/Model string is the failure point.")
    except Exception as e:
        print(f"❌ [CRITICAL] Handshake execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_direct_bypass())
