#!/usr/bin/env python3
"""
CoPaw Services Launcher

Starts both the CoPaw Webhook Receiver (port 8000) and Jarvis Daemon
concurrently with proper process management.

Usage:
    python3 launch_copaw_services.py
    
Or run services separately:
    Terminal 1: python3 -m scripts.copaw.copaw_webhook_receiver
    Terminal 2: python3 -m scripts.copaw.jarvis_daemon
"""

import subprocess
import sys
import signal
import os
from pathlib import Path

# Script paths
SCRIPT_DIR = Path(__file__).parent
WEBHOOK_RECEIVER = SCRIPT_DIR / "copaw-webhook-receiver.py"
JARVIS_DAEMON = SCRIPT_DIR / "jarvis_daemon.py"

# Processes
processes = []


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\n👋 Shutting down CoPaw services...")
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    sys.exit(0)


def check_dependencies():
    """Check required packages"""
    required = [
        "aiohttp",
        "pyaudio",
        "google-genai",
        "requests",
        "webrtcvad",
    ]
    
    missing = []
    for pkg in required:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print("❌ Missing packages. Install with:")
        print(f"   pip3 install {' '.join(missing)}")
        return False
    
    print("✅ All dependencies installed")
    return True


def launch_services():
    """Launch both services"""
    print("=" * 60)
    print("  CoPaw Services Launcher")
    print("=" * 60)
    print()
    
    # Check dependencies
    print("Checking dependencies...")
    if not check_dependencies():
        sys.exit(1)
    print()
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Launch webhook receiver
    print(f"🚀 Starting CoPaw Webhook Receiver on port 8000...")
    print(f"   Script: {WEBHOOK_RECEIVER}")
    webhook_proc = subprocess.Popen(
        [sys.executable, str(WEBHOOK_RECEIVER)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    processes.append(webhook_proc)
    
    # Wait for webhook to start
    import time
    time.sleep(2)
    
    # Launch Jarvis daemon
    print(f"🎙️  Starting Jarvis Daemon...")
    print(f"   Script: {JARVIS_DAEMON}")
    jarvis_proc = subprocess.Popen(
        [sys.executable, str(JARVIS_DAEMON)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    processes.append(jarvis_proc)
    
    print()
    print("=" * 60)
    print("  ✅ Both services started")
    print("=" * 60)
    print()
    print("📡 CoPaw Webhook Receiver: http://localhost:8000")
    print("   - Gmail integration: type 'gmail' in webhook payload")
    print("   - WhatsApp integration: type 'whatsapp' in webhook payload")
    print("   - Tri-Factor routing: type 'brain_delegate' in webhook payload")
    print()
    print("🎙️  Jarvis Daemon: Listening for voice input")
    print("   - Say 'Jarvis' to activate (if configured)")
    print("   - Speak naturally - VAD handles turn-taking")
    print()
    print("Press Ctrl+C to stop all services")
    print("-" * 60)
    
    # Monitor processes
    try:
        while True:
            for i, proc in enumerate(processes):
                if proc.poll() is not None:
                    # Process exited
                    name = "Webhook Receiver" if i == 0 else "Jarvis Daemon"
                    print(f"\n⚠️  {name} exited with code {proc.returncode}")
                    # Restart or exit
                    for p in processes:
                        if p.poll() is None:
                            p.terminate()
                    sys.exit(1)
            
            # Output logs
            for proc in processes:
                stdout = proc.stdout.readline()
                stderr = proc.stderr.readline()
                if stdout:
                    print(stdout.strip())
                if stderr:
                    print(stderr.strip(), file=sys.stderr)
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    launch_services()
