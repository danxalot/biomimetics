import httpx
import asyncio
import json
import os

# Mock or assume local gateway is running at 8080
GATEWAY_URL = "http://localhost:8080"
HEADERS = {
    "X-Genesis-Chain": "test-chain",
    "Content-Type": "application/json"
}

async def test_embedding_routing():
    print("Testing Embedding Routing Logic...")
    
    # 1. Test Local Routing (Default)
    payload_local = {
        "model": "qwen-embedding-local",
        "input": "This should go to local"
    }
    
    # We can't easily test the actual redirect without a live backend,
    # but we can check if the gateway logs the routing or returns a predictable error if backend is down.
    # Since I'm on the user's machine, I might be able to intercept or check logs if I had a way.
    # For now, let's just check if it accepts the request and tries to forward it.
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{GATEWAY_URL}/v1/embeddings", json=payload_local, headers=HEADERS, timeout=5.0)
            print(f"Local request status: {resp.status_code}")
        except Exception as e:
            print(f"Local request failed (expected if backend down): {e}")

    # 2. Test OCI Routing (via suffix)
    payload_oci = {
        "model": "qwen-embedding-oci",
        "input": "This should go to OCI"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{GATEWAY_URL}/v1/embeddings", json=payload_oci, headers=HEADERS, timeout=5.0)
            print(f"OCI request status: {resp.status_code}")
        except Exception as e:
            print(f"OCI request failed (expected if backend down): {e}")

async def main():
    await test_embedding_routing()

if __name__ == "__main__":
    asyncio.run(main())
