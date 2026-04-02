import asyncio
import logging
import sys
import os
from copaw.app.channels.voice.vultr_relay_client import VultrRelayClient

logging.basicConfig(level=logging.INFO)

async def test_full_client():
    # Use the same relay URL as production
    relay_url = "ws://100.86.112.119:8765/ws/live"
    client = VultrRelayClient(relay_url)
    
    print(f"--- Starting Full Client Test: {relay_url} ---")
    
    if not await client.connect():
        print("❌ Failed to connect to relay.")
        return

    # Send setup
    await client.send_setup_message()
    print("✓ Setup sent.")
    
    # Wait for setup acknowledgment (implicit)
    await asyncio.sleep(2)
    
    # Inject a text prompt to force Gemini to speak
    test_prompt = {
        "realtimeInput": {
            "text": "Hello Gemini. This is an automated diagnostic. Please say 'The BiOS voice relay is confirmed' clearly and then stop."
        }
    }
    # Note: Using the camelCase key 'realtimeInput' as per 3.1 spec
    await client.ws.send(json.dumps(test_prompt))
    print("✓ Test prompt injected.")
    
    # Capture results
    transcripts = []
    def on_transcript(t):
        transcripts.append(t)
        print(f"\n[📝 TRANSCRIPT RECEIVED]: {t}")

    client.running = True
    print("✓ Client state set to running.")

    print("Listening for 15 seconds...")
    try:
        # We don't need audio loops for this headless test, just the receiver
        await asyncio.wait_for(client.receive_loop(on_transcript), timeout=20.0)
    except asyncio.TimeoutError:
        print("\nTest timed out after 15s.")
    except Exception as e:
        print(f"\nError during receive: {e}")
    finally:
        await client.close()
        
    if transcripts:
        print("\n✅ SUCCESS: Intelligible language captured via relay transcript.")
        print(f"Final Transcript: {' '.join(transcripts)}")
    else:
        print("\n❌ FAILURE: No intelligible language captured.")

if __name__ == "__main__":
    import json
    # Add src to sys.path
    src_path = "/Users/danexall/biomimetics/scripts/copaw/src"
    if src_path not in sys.path:
        sys.path.append(src_path)
    
    asyncio.run(test_full_client())
