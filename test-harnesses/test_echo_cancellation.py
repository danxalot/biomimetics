import asyncio
import time
import httpx
import logging
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import uvicorn
import threading

# Import the console router
from scripts.copaw.src.copaw.app.routers.console import router as console_router
from scripts.copaw.src.copaw.app.channels.voice.vultr_relay_client import VultrRelayClient

logging.basicConfig(level=logging.DEBUG)

# 1. Setup a test FastAPI app
app = FastAPI()
app.include_router(console_router)
client = TestClient(app)

# 2. Start the test app in a background thread so the client can hit it
def run_app():
    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="error")

thread = threading.Thread(target=run_app, daemon=True)
thread.start()
time.sleep(1) # wait for server to start

async def main():
    print("\n--- Starting Automated Echo Cancellation Test ---")
    
    # 3. Initialize the relay client with mock audio
    relay = VultrRelayClient("ws://mock")
    relay.copaw_base_url = "http://127.0.0.1:8099" # point to our test server
    
    # Mock the asyncio loop
    relay.loop = asyncio.get_running_loop()
    
    # Mock VAD
    relay.vad = MagicMock()
    relay.vad.is_speech.return_value = True # always detect speech
    
    # We will simulate the mic capture logic directly to avoid threading issues
    print("Test 1: Normal microphone capture (no playback)")
    
    # Simulate the check
    is_playing = await relay._check_external_playback()
    print(f"External playback status: {is_playing}")
    assert not is_playing, "Should not be playing initially"
    
    # Simulate a fake "browser" setting the playing state for 2 seconds
    print("\nTest 2: Browser starts playing audio")
    async with httpx.AsyncClient() as hc:
        resp = await hc.post("http://127.0.0.1:8099/console/set-playing", json={"duration": 2.0})
        print(f"Set playing response: {resp.json()}")
        
    is_playing = await relay._check_external_playback()
    print(f"External playback status: {is_playing}")
    assert is_playing, "Should be playing after set-playing"
    
    print("\nTest 3: Waiting for playback to finish")
    await asyncio.sleep(2.1)
    
    is_playing = await relay._check_external_playback()
    print(f"External playback status: {is_playing}")
    assert not is_playing, "Should not be playing after duration expires"
    
    print("\n✅ All automated echo cancellation tests passed.")

if __name__ == "__main__":
    asyncio.run(main())
