import asyncio
import os
import sys

# Add copaw src to path
sys.path.append("/Users/danexall/biomimetics/scripts/copaw/src")

from copaw.app.channels.voice.vultr_relay_client import VultrRelayClient

RELAY_URL = "ws://localhost:8766/ws/live"

async def test_updated_client():
    print(f"--- 🚀 TESTING UPDATED VULTR RELAY CLIENT ---")
    print(f"Connecting to: {RELAY_URL}")
    
    client = VultrRelayClient(RELAY_URL)
    
    def on_transcript(text):
        print(f"\n[CLIENT CALLBACK]: {text}")

    # Set running to True manually to allow loops to start
    client.running = True
    
    try:
        if not await client.connect():
            print("❌ Failed to connect.")
            return

        print("✓ Connected. Setting up audio (using dummy streams if necessary)...")
        # We don't want to actually open mic/speakers if running in CI/terminal without hardware
        # But let's see if it works. If it fails, we'll mock them.
        try:
            client._setup_audio()
        except Exception as e:
            print(f"⚠ PyAudio error (expected if no hardware): {e}")
            print("Proceeding without local audio I/O...")
            # Mock streams to avoid errors in loops
            class MockStream:
                def read(self, *args, **kwargs): return b'\x00' * 2048
                def write(self, *args, **kwargs): pass
                def stop_stream(self): pass
                def close(self): pass
            client.input_stream = MockStream()
            client.output_stream = MockStream()

        print("✓ Sending setup (with transcription enabled)...")
        await client.send_setup_message()
        
        # Inject a text prompt to trigger an audio response with transcript
        await asyncio.sleep(1)
        instruction = "Please say 'The BiOS voice relay is now fully operational with transcripts.' clearly."
        print(f"✓ Injecting instruction: {instruction}")
        
        msg = client.build_realtime_input("text", "text/plain", instruction)
        import json
        await client.ws.send(json.dumps(msg))

        print("\nListening for 10 seconds for responses...")
        # Run receive_loop for a bit
        try:
            await asyncio.wait_for(client.receive_loop(on_transcript), timeout=10.0)
        except asyncio.TimeoutError:
            print("\n--- Timeout reached ---")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.close()
        print("\n--- Test Finished ---")

if __name__ == "__main__":
    asyncio.run(test_updated_client())
