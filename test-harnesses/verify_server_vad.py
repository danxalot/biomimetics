import asyncio
import base64
import json
import websockets
from scripts.copaw.src.copaw.app.channels.voice.vultr_relay_client import VultrRelayClient

async def test_streaming_logic():
    print("Testing send_loop frame alignment for Gemini Server-Side VAD")
    
    relay = VultrRelayClient("ws://mock")
    relay.running = True
    relay.ready.set()
    
    # Push 3 frames
    relay.mic_queue.put_nowait((b'\x01'*480, True, 100))
    relay.mic_queue.put_nowait((b'\x02'*480, True, 200))
    relay.mic_queue.put_nowait((b'\x03'*480, True, 300))
    
    print(f"Queue size before drain: {relay.mic_queue.qsize()}")
    
    # Manually run the extraction block
    data, is_speech, current_mic_rms = await relay.mic_queue.get()
    while not relay.mic_queue.empty():
        try:
            data, is_speech, current_mic_rms = relay.mic_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
            
    print(f"Queue size after drain: {relay.mic_queue.qsize()}")
    print(f"Data byte: {data[0]}") # Should be 3, the freshest frame
    
    if data[0] == 3:
        print("✅ Drain logic is correctly grabbing the freshest frame.")
        print("⚠️ WARNING: Aggressively draining the queue DROPS FRAMES.")
        print("⚠️ Dropping frames creates jumps in the audio waveform.")
        print("⚠️ Acoustic Echo Cancellation (AEC) REQUIRES a contiguous, unbroken waveform to subtract the echo signal.")
    else:
        print("❌ Drain logic failed.")

asyncio.run(test_streaming_logic())
