import asyncio
import base64
import json
import websockets

async def test_turn_complete():
    uri = "ws://100.86.112.119:8765/ws/live"
    
    token = "7a9a0937-916b-416a-ba31-6006630b0b78"
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri, additional_headers=headers) as ws:
            print("Connected.")
            
            setup_message = {
                "setup": {
                    "model": "models/gemini-3.1-flash-live-preview",
                    "systemInstruction": {"parts": [{"text": "You are Puck, a helpful assistant."}]},
                    "generationConfig": {"responseModalities": ["AUDIO"]},
                    "tools": [],
                }
            }
            await ws.send(json.dumps(setup_message))
            
            # Wait for setupComplete
            for _ in range(5):
                resp = await asyncio.wait_for(ws.recv(), timeout=3.0)
                if isinstance(resp, str):
                    payload = json.loads(resp)
                    print("Received:", payload.keys())
                    if "setupComplete" in payload:
                        break
            
            # Send audio frame
            silence_pcm = b'\x00' * 3200
            encoded_pcm = base64.b64encode(silence_pcm).decode("utf-8")
            
            audio_message = {
                "realtimeInput": {
                    "audio": {
                        "mimeType": "audio/pcm;rate=16000",
                        "data": encoded_pcm
                    }
                }
            }
            await ws.send(json.dumps(audio_message))
            print("Sent audio frame.")
            
            # Send turnComplete
            turn_complete_message = {"clientContent": {"turnComplete": True}}
            await ws.send(json.dumps(turn_complete_message))
            print("Sent turnComplete.")
            
            # Wait for response
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
                if isinstance(resp, bytes):
                    print("Received audio response")
                else:
                    print("Received:", json.loads(resp).keys())
            except asyncio.TimeoutError:
                print("Timeout waiting for response.")
                
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e.code} - {e.reason}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_turn_complete())
