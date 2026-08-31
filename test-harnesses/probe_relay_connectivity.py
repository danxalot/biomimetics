import asyncio
import websockets
import time
import socket
import logging

# Configuration
RELAY_URL = "ws://100.86.112.119:8765/ws/live"
RELAY_IP = "100.86.112.119"
RELAY_PORT = 8765

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RelayProbe")

async def probe_tcp():
    logger.info(f"Probing TCP connectivity to {RELAY_IP}:{RELAY_PORT}...")
    try:
        start = time.time()
        # Use a low-level socket to check if the port is open
        with socket.create_connection((RELAY_IP, RELAY_PORT), timeout=5):
            latency = (time.time() - start) * 1000
            logger.info(f"✅ TCP Port {RELAY_PORT} is OPEN. Latency: {latency:.2f}ms")
            return True
    except Exception as e:
        logger.error(f"❌ TCP Port {RELAY_PORT} is CLOSED or Unreachable: {e}")
        return False

async def probe_websocket():
    logger.info(f"Probing WebSocket Handshake to {RELAY_URL}...")
    try:
        start = time.time()
        # Test with a generous timeout to see how long it actually takes
        async with websockets.connect(RELAY_URL, open_timeout=30) as ws:
            latency = (time.time() - start) * 1000
            logger.info(f"✅ WebSocket Handshake SUCCESSFUL. Handshake time: {latency:.2f}ms")
            return True
    except asyncio.TimeoutError:
        logger.error("❌ WebSocket Handshake TIMED OUT (after 30s).")
    except Exception as e:
        logger.error(f"❌ WebSocket Handshake FAILED: {e}")
    return False

async def run_diagnostics():
    print("\n--- BiOS Relay Connectivity Diagnostics ---")
    
    tcp_ok = await probe_tcp()
    if not tcp_ok:
        print("\nPossible causes:")
        print("1. Tailscale is disconnected.")
        print("2. Vultr Relay service is down.")
        print("3. Firewall is blocking port 8765.")
        return

    ws_ok = await probe_websocket()
    if not ws_ok:
        print("\nPossible causes:")
        print("1. Relay service is overwhelmed and cannot complete handshakes.")
        print("2. MTU issues over Tailscale (fragmented packets).")
        print("3. WebSocket configuration mismatch on server.")
    else:
        print("\n✅ Connectivity is HEALTHY.")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
