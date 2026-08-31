import asyncio
import base64
import json
import logging
import threading
import time
import numpy as np
from unittest.mock import MagicMock, patch
from scripts.copaw.src.copaw.app.channels.voice.vultr_relay_client import VultrRelayClient

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("EchoAnalysis")

async def simulate_echo_loop():
    print("\n--- BiOS Echo Analysis & Self-Test Harness ---")
    
    # 1. Initialize Relay Client
    relay = VultrRelayClient("ws://mock_relay")
    relay.running = True
    relay.ready.set()
    relay.loop = asyncio.get_running_loop()
    
    # 2. Mock Hardware
    relay.vad = MagicMock()
    relay.vad.is_speech.return_value = False # Default: Silence
    relay.input_stream = MagicMock()
    
    # Simulate background noise (RMS ~100)
    silence_frame = (np.random.normal(0, 100, 480).astype(np.int16)).tobytes()
    relay.input_stream.read.return_value = silence_frame
    
    # 3. Start Capture Thread
    mic_thread = threading.Thread(target=relay._mic_capture_thread, daemon=True)
    mic_thread.start()
    
    print("\nPhase 1: Ambient Silence (Learning Baseline)")
    await asyncio.sleep(2)
    
    # Drain the queue to see the trace
    while not relay.mic_queue.empty():
        _, is_speech, rms = await relay.mic_queue.get()
        # logger.info(f"[TEST] Captured: RMS={rms}, VAD={is_speech}")
        relay.mic_queue.task_done()

    print("\nPhase 2: Simulating Model Voice (Echo)")
    # Simulate a loud voice coming from speakers (RMS ~2000)
    voice_frame = (np.random.normal(0, 2000, 480).astype(np.int16)).tobytes()
    relay.input_stream.read.return_value = voice_frame
    # Local VAD might trigger if threshold is low
    relay.vad.is_speech.return_value = True # Let's assume it hears "speech"
    
    await asyncio.sleep(2)
    
    frames_captured = 0
    high_rms_detected = 0
    while not relay.mic_queue.empty():
        _, is_speech, rms = await relay.mic_queue.get()
        frames_captured += 1
        if rms > 1000:
            high_rms_detected += 1
        relay.mic_queue.task_done()

    print(f"\n[ANALYSIS] Captured {frames_captured} frames of echo.")
    print(f"[ANALYSIS] High energy frames (>1000 RMS): {high_rms_detected}")
    
    if high_rms_detected > 0:
        print("\n⚠️ WARNING: Microphone is picking up speaker echo clearly.")
        print("Since local ducking is OFF, this audio is being sent to Gemini.")
        print("If Gemini server-side AEC fails to filter this out, it WILL trigger a barge-in.")
    
    print("\nPhase 3: Testing Interruption Signal")
    # Simulate server sending an interruption
    relay.playback_queue.put_nowait(b'\x01'*1000) # Buffer some audio
    print(f"Playback queue size: {relay.playback_queue.qsize()}")
    
    # Simulate JSON message with interruption
    interrupt_msg = {"serverContent": {"interrupted": True}}
    await relay._handle_json_message(interrupt_msg)
    
    print(f"Playback queue size after interrupt: {relay.playback_queue.qsize()}")
    if relay.playback_queue.empty():
        print("✅ Interruption correctly flushed the playback buffer.")
    else:
        print("❌ Interruption failed to flush the playback buffer.")

    relay.running = False
    mic_thread.join(timeout=1)
    print("\n--- Echo Analysis Complete ---")

if __name__ == "__main__":
    asyncio.run(simulate_echo_loop())
