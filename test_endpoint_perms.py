import asyncio
import websockets
import json

API_KEY = "4U2zu8YAvXxGB_yks0s9A4gSgcr96N9OEiwVtNo5zwM"

async def test_url(url):
    print(f"Testing: {url}")
    try:
        async with websockets.connect(url) as ws:
            print(f"  ✅ SUCCESS: Connected to {url}")
            return True
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

async def main():
    perms = [
        f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService/BidiGenerateContent?key={API_KEY}",
        f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={API_KEY}",
        f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService/BidiGenerateContent?key={API_KEY}",
        f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={API_KEY}",
        f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService:BidiGenerateContent?key={API_KEY}",
    ]
    for p in perms:
        if await test_url(p):
            print(f"\n🎯 VALID ENDPOINT: {p}")
            break

if __name__ == "__main__":
    asyncio.run(main())
