import wave
import pyaudio
import sys
import os

WAV_FILE = "bios_e2e_test.wav"

def test_speaker():
    if not os.path.exists(WAV_FILE):
        print(f"❌ Error: {WAV_FILE} not found. Run test_e2e_local_audio.py first.")
        sys.exit(1)

    print(f"--- [LOCAL SPEAKER TEST] ---")
    print(f"Playing {WAV_FILE} to verify PyAudio handoff...")

    wf = wave.open(WAV_FILE, 'rb')
    p = pyaudio.PyAudio()

    # Match the client's output stream parameters
    stream = p.open(
        format=p.get_format_from_width(wf.getsampwidth()),
        channels=wf.getnchannels(),
        rate=wf.getframerate(),
        output=True
    )

    print(f"Parameters: {wf.getframerate()}Hz, {wf.getnchannels()} Channels, {wf.getsampwidth()*8}-bit")

    data = wf.readframes(1024)
    chunks = 0
    try:
        while data:
            stream.write(data)
            data = wf.readframes(1024)
            chunks += 1
            if chunks % 100 == 0:
                print(f"  - Played {chunks} chunks...")
    except Exception as e:
        print(f"❌ Playback Error: {e}")
    finally:
        print("Playback finished.")
        stream.stop_stream()
        stream.close()
        p.terminate()
        wf.close()

if __name__ == "__main__":
    test_speaker()
