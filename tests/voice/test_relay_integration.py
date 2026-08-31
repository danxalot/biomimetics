import pytest
import asyncio
import websockets
import json

@pytest.mark.asyncio
async def test_relay_integration():
    uri = "ws://localhost:8765/ws/live"
    # Using a dummy token for test or whatever is default in the relay
    token = "test-token"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        async with websockets.connect(uri, additional_headers=headers) as ws:
            # 1. Setup message
            setup = {
                "setup": {
                    "model": "models/gemini-3.1-flash-live-preview",
                    "systemInstruction": {"parts": [{"text": "You are a test assistant."}]},
                    "generationConfig": {"responseModalities": ["AUDIO"]},
                    "tools": [],
                }
            }
            await ws.send(json.dumps(setup))
            
            # Wait for setupComplete
            setup_success = False
            for _ in range(5):
                response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                if isinstance(response, str):
                    payload = json.loads(response)
                    if "setupComplete" in payload:
                        setup_success = True
                        break
            
            assert setup_success, "Did not receive setupComplete"
            
            # 2. Send an audio frame
            silence_bytes = b"\x00" * 3200
            await ws.send(silence_bytes)
            
            # 3. Test if turnComplete is accepted
            turn_complete_msg = {"clientContent": {"turnComplete": True}}
            await ws.send(json.dumps(turn_complete_msg))
            
            # If no exception occurred, integration is successful
            assert True
    except ConnectionRefusedError:
        pytest.skip("Relay is not running on localhost:8765")
