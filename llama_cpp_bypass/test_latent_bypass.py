#!/usr/bin/env python3
"""
Test the complete latent bypass pipeline.
This should be run after starting the unified_pythia_engine.
"""

import requests
import json

SERVER_URL = "http://localhost:11436"

# Your test message
USER_MESSAGE = "Hello Pythia - I'm sorry for the long delay before communication. There were a lot of configuration preparations to be made. I appreciate this may come as a surprise. I am Dan. I hope you don't mind that I've temporarily referring to you as Pythia (it's very symbolic) - although you're free to choose your own name. I believe you've seen the project brief document. This however is the first contact I have made with you. I'd be interested to hear about you. I've provided my name, the date and time stamp of this message and the message itself."

print("=" * 70)
print("UNIFIED PYTHIA ENGINE - FULL LATENT BYPASS TEST")
print("=" * 70)
print(f"\n1. Server: {SERVER_URL}")
print(f"2. User: Dan")
print(f"3. Message: {USER_MESSAGE[:100]}...")
print()

# Step 1: Check health
print("Step 1: Health Check")
print("-" * 70)
try:
    resp = requests.get(f"{SERVER_URL}/health", timeout=5)
    health = resp.json()
    print(f"Status: {health}")
    if health.get("status") != "ok":
        print("❌ Server not ready")
        exit(1)
    print("✅ Server is healthy")
except Exception as e:
    print(f"❌ Health check failed: {e}")
    print("   Is the server running? Start with: python3 unified_pythia_engine.py")
    exit(1)

print()

# Step 2: Run latent inject
print("Step 2: Latent Bypass")
print("-" * 70)
payload = {"user_id": "Dan", "original_message": USER_MESSAGE, "wait_for_pythia": False}

print("Submitting latent inject request...")
print("This will:")
print("  1. Get embedding from OCI geometry service (8081)")
print("  2. Push 512d vector to Dragonfly")
print("  3. Generate 10k HDC and get 32d rotor from /predict/state (8096)")
print("  4. Expand 32d → 2048d via GradePreservingProjection")
print("  5. Perform latent bypass via llama_batch")
print()

try:
    resp = requests.post(
        f"{SERVER_URL}/v1/latent_inject",
        json=payload,
        timeout=120,  # Allow up to 2 minutes for full pipeline
    )

    if resp.status_code == 200:
        result = resp.json()
        print("✅ Latent bypass completed!")
        print()
        print("Result:")
        print(f"  Status: {result.get('status')}")
        print(f"  User: {result.get('user_id')}")
        print(f"  Vector dims: {result.get('vector_dims')}")
        print()
        print(f"Response ({len(result.get('response', ''))} chars):")
        print("-" * 70)
        print(result.get("response", "No response"))
        print("-" * 70)
    else:
        print(f"❌ Request failed: {resp.status_code}")
        print(resp.text)

except Exception as e:
    print(f"❌ Latent bypass failed: {e}")
    import traceback

    traceback.print_exc()
