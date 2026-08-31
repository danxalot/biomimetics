import asyncio
import time
import httpx
import logging
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch
import threading

# Import the console router
from scripts.copaw.src.copaw.app.routers.console import router as console_router
from scripts.copaw.src.copaw.app.channels.voice.vultr_relay_client import VultrRelayClient
from fastapi import FastAPI
from fastapi.testclient import TestClient
import uvicorn

logging.basicConfig(level=logging.DEBUG)

# 1. Setup a test FastAPI app
app = FastAPI()
app.include_router(console_router)

def run_app():
    uvicorn.run(app, host="127.0.0.1", port=8102, log_level="error")

thread = threading.Thread(target=run_app, daemon=True)
thread.start()
time.sleep(1) # wait for server to start

async def main():
    print("\n--- Starting Microphone Capture Loop Test ---")
    
    # 3. Initialize the relay client with mock audio
    relay = VultrRelayClient("ws://mock")
    relay.copaw_base_url = "http://127.0.0.1:8102" # point to our test server
    relay.running = True
    relay.loop = asyncio.get_running_loop()
    
    # Mock VAD and Stream
    relay.vad = MagicMock()
    relay.vad.is_speech.return_value = True # always detect speech initially
    relay.input_stream = MagicMock()
    relay.input_stream.read.return_value = b'\x01' * 480 # mock audio frame
    
    # Track what gets put into the mic_queue
    relay.mic_queue = asyncio.Queue()
    
    # Start the mic thread
    mic_thread = threading.Thread(target=relay._mic_capture_thread, daemon=True)
    mic_thread.start()
    
    print("Test 1: Normal capture (no playback)")
    await asyncio.sleep(0.5) # let the thread run
    
    frames = []
    while not relay.mic_queue.empty():
        frames.append(relay.mic_queue.get_nowait())
    
    assert len(frames) > 0, "Queue should have frames"
    assert any(any(b != 0 for b in f[0]) for f in frames), "Should contain non-zero speech data"
    print(f"Captured {len(frames)} normal frames")
    
    print("\nTest 2: Ducking active (Browser starts playing audio)")
    async with httpx.AsyncClient() as hc:
        await hc.post("http://127.0.0.1:8102/console/set-playing", json={"duration": 2.0})
        
    await asyncio.sleep(0.5) # Wait for the thread to process the new external state
    
    # Drain the queue of old frames
    while not relay.mic_queue.empty():
         relay.mic_queue.get_nowait()
         
    await asyncio.sleep(0.5) # Let the thread run while ducking is active
    
    frames = []
    while not relay.mic_queue.empty():
        frames.append(relay.mic_queue.get_nowait())
        
    assert len(frames) > 0, "Queue should have frames"
    # Find any frames that are NOT muted
    unmuted_frames = [f for f in frames if any(b != 0 for b in f[0])]
    if unmuted_frames:
        print(f"FAILED: Found {len(unmuted_frames)} unmuted frames out of {len(frames)}!")
        # Let's see what the first unmuted frame looks like
        print(f"Sample unmuted frame bytes: {unmuted_frames[0][0][:20]}")
    
    assert len(unmuted_frames) == 0, "All frames should be muted (zeroed out) during ducking"
    print(f"Captured {len(frames)} MUTED frames")
    
    relay.running = False
    mic_thread.join(timeout=1.0)
    print("\n✅ Microphone capture loop test passed.")

if __name__ == "__main__":
    asyncio.run(main())
