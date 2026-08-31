import subprocess
import time
import os
import sys

def main():
    print("=== Starting E2E BiOS Voice Test ===", flush=True)
    
    # 1. Start BiOS Voice Server
    print("Launching BiOS Voice Server...", flush=True)
    env = os.environ.copy()
    env["BIOS_TEST_MODE"] = "1"
    server = subprocess.Popen(
        ["bash", "./scripts/sys/bios-voice.sh"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env
    )
    
    import threading
    log_lines = []
    
    def read_server():
        for line in server.stdout:
            sys.stdout.write(f"[BiOS] {line}")
            sys.stdout.flush()
            log_lines.append(line)
            
    threading.Thread(target=read_server, daemon=True).start()
    
    # 2. Wait for Handshake
    print("Waiting for Setup Handshake Complete...", flush=True)
    start_wait = time.time()
    handshake_done = False
    while time.time() - start_wait < 120:
        if any("Setup Handshake Complete" in l for l in log_lines):
            handshake_done = True
            break
        time.sleep(0.5)
        
    if not handshake_done:
        print("❌ Server failed to handshake.", flush=True)
        server.terminate()
        sys.exit(1)
        
    print("✅ Handshake complete. Stabilizing for 2 seconds...", flush=True)
    time.sleep(2)
    
    # 3. Simulate Human Speech
    print("🗣️ Triggering 'say' to simulate user speech...", flush=True)
    log_lines.clear()
    subprocess.run(["say", "-v", "Alex", "Hello BiOS, please introduce yourself in one short sentence."])
    
    # 4. Wait for BiOS Response
    print("⏳ Waiting for BiOS to respond...", flush=True)
    start_wait = time.time()
    responded = False
    while time.time() - start_wait < 15:
        if any("[🤖 BiOS]:" in l for l in log_lines):
            responded = True
            break
        time.sleep(0.5)
        
    if not responded:
        print("❌ BiOS did not respond to speech.", flush=True)
        server.terminate()
        sys.exit(1)
        
    print("✅ BiOS is responding!", flush=True)
    
    # Wait a bit for BiOS to talk
    time.sleep(2)
    
    # 5. Simulate Barge-In
    print("🗣️ Triggering Barge-In interruption...", flush=True)
    subprocess.run(["say", "-v", "Alex", "Actually, please tell me a joke instead."])
    
    print("⏳ Waiting for interruption response...", flush=True)
    start_wait = time.time()
    interrupted_or_joke = False
    
    log_lines.clear()
    while time.time() - start_wait < 15:
        combined = "".join(log_lines).lower()
        if "joke" in combined or "interrupt" in combined:
            interrupted_or_joke = True
            break
        time.sleep(0.5)
        
    if interrupted_or_joke:
        print("✅ BiOS successfully handled barge-in interruption!", flush=True)
    else:
        print("❌ BiOS did not process barge-in.", flush=True)
    
    print("=== Test Complete. Shutting down. ===", flush=True)
    server.terminate()

if __name__ == "__main__":
    main()
