#!/usr/bin/env python3
"""Direct test of MiniMax API with Bearer token"""
import json
import requests

# Load API key
with open("/home/ubuntu/ARCA/.secrets/MINIMAX_API_KEY.json", "r") as f:
    secrets = json.load(f)
    api_key = secrets["ARCA_MiniMax"]

print(f"✓ API key loaded (length: {len(api_key)})")

# Test direct API call
url = "https://api.minimax.io/anthropic/v1/messages"
headers = {
    "Authorization": f"Bearer {api_key}",
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json"
}
payload = {
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 100,
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "Hello, which model are you?"}]}
    ]
}

print(f"✓ Calling: {url}")
print(f"✓ Headers: {list(headers.keys())}")

try:
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    print(f"\n✓ Status: {response.status_code}")
    print(f"✓ Response: {response.text[:500]}")
except Exception as e:
    print(f"✗ Error: {e}")
