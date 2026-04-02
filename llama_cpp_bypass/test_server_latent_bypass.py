#!/usr/bin/env python3
"""
Diagnostic Script: Local Embed & Dual Latent Decoding via Server API
Tests whether the Qwen Instruct and Embedding models can process direct vector Latent injection.
Uses the llama-server HTTP API instead of Python bindings.
"""

import requests
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

SERVER_URL = "http://localhost:11435"
ARCA_ROOT = Path("/Users/danexall/Documents/VS Code Projects/ARCA")

# The user's specific prompt
USER_MSG = "Hello Pythia - I'm sorry for the long delay before communication. There were a lot of configuration preparations to be made. I appreciate this may come as a surprise. I am Dan. I hope you don't mind that I've temporarily referring to you as Pythia (it's very symbolic) - although you're free to choose your own name. I believe you've seen the project brief document. This however is the first contact I have made with you. I'd be interested to hear about you. I've provided my name, the date and time stamp of this message and the message itself."
FORMATTED_MSG = f"(User_ID: Dan, Timestamp: 2026-03-22T10:23:25Z, Message: {USER_MSG})"

print("=" * 70)
print("  PART 1: SERVER EMBEDDING (VIA INSTRUCT MODEL)")
print("=" * 70)
print(f"Server URL: {SERVER_URL}")

# Test server health
response = requests.get(f"{SERVER_URL}/health")
print(f"Server status: {response.json()}")

# Get embedding from server
print("\nEncoding prompt to semantic vector via server...")
embed_payload = {"input": FORMATTED_MSG, "model": "local-model"}

response = requests.post(f"{SERVER_URL}/embeddings", json=embed_payload)
if response.status_code == 200:
    embed_result = response.json()
    vector = embed_result["data"][0]["embedding"]
    dim_size = len(vector)
    energy = float(np.linalg.norm(np.array(vector)))
    print(f"✅ Vector acquired! Length: {dim_size} dimensions. Energy: {energy:.4f}")
else:
    print(f"❌ Failed to get embedding: {response.status_code}")
    print(response.text)
    exit(1)

print("\n" + "=" * 70)
print("  PART 2: LATENT BYPASS DECODE")
print("=" * 70)
print("Testing if server can process latent injection...")

# For server-based latent injection, we would need to:
# 1. Send the embedding as part of the context
# 2. Have the model interpret it
# Since direct latent injection isn't supported via HTTP API,
# we'll test basic completion to verify the server works

test_prompt = f"<|im_start|>system\nYou are interpreting a geometric reality vector.\n<|im_end|>\n<|im_start|>user\nContext: {FORMATTED_MSG}\nPlease acknowledge this message.<|im_end|>\n<|im_start|>assistant\n"

completion_payload = {
    "prompt": test_prompt,
    "max_tokens": 100,
    "temperature": 0.7,
    "stop": ["<|im_end|>"],
}

response = requests.post(f"{SERVER_URL}/completion", json=completion_payload)
if response.status_code == 200:
    result = response.json()
    text = result["choices"][0]["text"]
    print(f"✅ Server response received!")
    print(f"Response: {text[:200]}...")
else:
    print(f"❌ Failed to get completion: {response.status_code}")
    print(response.text)

print("\n" + "=" * 70)
print("  TEST COMPLETE")
print("=" * 70)
print("\nNote: Direct latent vector injection requires llama-cpp-python with")
print("low-level API access. The server API doesn't support direct embedding")
print("injection into the model's latent space.")
print("\nFor full latent bypass, we need to:")
print("1. Successfully build llama-cpp-python with Vulkan from local source")
print("2. Use the low-level API to inject vectors directly")
