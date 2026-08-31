import subprocess
import time

engine_path = "/Users/danexall/biomimetics/scripts/sys/bios_audio_engine.swift"

proc = subprocess.Popen(
    ["swift", engine_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

print("Started swift process...")

# Read output
start = time.time()
while time.time() - start < 3:
    # Use non-blocking read or small read
    data = proc.stdout.read1(960)
    if data:
        print(f"Read {len(data)} bytes")
        break
    time.sleep(0.1)

proc.terminate()
