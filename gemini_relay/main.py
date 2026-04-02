#!/usr/bin/env python3
"""
Gemini Live WebSocket Relay Server

Lightweight, asynchronous WebSocket proxy for bridging clients to Gemini Live API.
Designed for micro VPS (0.1 vCPU / 512MB RAM).

Features:
- Bidirectional message piping (client <-> Gemini)
- Azure Key Vault integration for API key retrieval
- Background memory spooler for Muninn integration
- Minimal memory footprint, no audio transcoding

Usage:
    python3 main.py

Environment Variables:
    GEMINI_API_KEY          - Direct API key (optional if using Azure KV)
    AZURE_KEY_VAULT_NAME    - Azure Key Vault name
    AZURE_TENANT_ID         - Azure AD tenant ID
    AZURE_CLIENT_ID         - Service principal client ID
    AZURE_CLIENT_SECRET     - Service principal client secret
    GEMINI_SECRET_NAME      - Name of secret in Azure KV (default: gemini-api-key)
    MUNINN_URL              - Muninn endpoint for memory spooler
    RELAY_HOST              - Host to bind (default: 0.0.0.0)
    RELAY_PORT              - Port to bind (default: 8765)
"""

import os
import sys
import json
import asyncio
import base64
import logging
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

import httpx
import ssl
import certifi
import websockets
from websockets.server import WebSocketServerProtocol
from websockets.client import WebSocketClientProtocol
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.logger import logger as fastapi_logger

# Ensure log directory exists before setting up handlers
LOG_DIR = Path.home() / ".gemini_relay"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "relay.log"),
    ],
)
log = logging.getLogger("gemini_relay")

# Configuration
RELAY_HOST = os.getenv("RELAY_HOST", "0.0.0.0")
RELAY_PORT = int(os.getenv("RELAY_PORT", "8765"))

# Gemini Live API endpoint
GEMINI_WS_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"

# Azure Key Vault configuration
AZURE_KEY_VAULT_NAME = os.getenv("AZURE_KEY_VAULT_NAME", "arca-mcp-kv-dae")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
GEMINI_SECRET_NAME = os.getenv("GEMINI_SECRET_NAME", "gemini-api-key")

# Muninn memory spooler configuration
MUNINN_URL = os.getenv("MUNINN_URL", "http://10.128.0.3/api/engrams")

# Global API key cache
_gemini_api_key: Optional[str] = None


# ============================================================================
# Azure Key Vault Integration
# ============================================================================

async def fetch_gemini_api_key() -> str:
    """
    Fetch Gemini API key from Azure Key Vault or environment.
    
    Priority:
    1. GEMINI_API_KEY environment variable
    2. Azure Key Vault
    """
    global _gemini_api_key
    
    # Check environment first
    if os.getenv("GEMINI_API_KEY"):
        _gemini_api_key = os.getenv("GEMINI_API_KEY")
        log.info("✓ Using GEMINI_API_KEY from environment")
        return _gemini_api_key
    
    # Check if already cached
    if _gemini_api_key:
        log.info("✓ Using cached GEMINI_API_KEY")
        return _gemini_api_key
    
    # Fetch from Azure Key Vault
    if not all([AZURE_TENANT_ID, AZURE_CLIENT_ID]):
        log.warning("⚠ Azure credentials not configured and GEMINI_API_KEY not set")
        return ""
    
    try:
        # Get access token
        token = await _get_azure_access_token()
        
        # Fetch secret from Key Vault
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://{AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/{GEMINI_SECRET_NAME}?api-version=7.4",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            data = response.json()
            _gemini_api_key = data.get("value", "")
        
        if _gemini_api_key:
            log.info(f"✓ Fetched GEMINI_API_KEY from Azure Key Vault ({AZURE_KEY_VAULT_NAME})")
        else:
            log.warning("⚠ Secret value empty in Azure Key Vault")
            
        return _gemini_api_key
        
    except Exception as e:
        log.error(f"✗ Failed to fetch API key from Azure: {e}")
        return ""


async def _get_azure_access_token() -> str:
    """Get Azure AD access token for Key Vault."""
    token_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": AZURE_CLIENT_ID,
                "client_secret": AZURE_CLIENT_SECRET,
                "scope": "https://vault.azure.net/.default"
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["access_token"]


# ============================================================================
# Memory Spooler (Background Task)
# ============================================================================

class MemorySpooler:
    """
    Extracts conversational context from WebSocket stream
    and pushes to Muninn endpoint without blocking audio.
    """
    
    def __init__(self, muninn_url: str = ""):
        self.muninn_url = muninn_url or MUNINN_URL
        self.transcript_chunks: List[str] = []
        self.session_id: str = ""
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
    
    def start_session(self, session_id: str):
        """Start a new conversation session."""
        self.session_id = session_id
        self.start_time = datetime.now()
        self.end_time = None
        self.transcript_chunks = []
        log.info(f"📝 Memory spooler session started: {session_id}")
    
    def add_transcript(self, text: str):
        """Add a transcript chunk."""
        if text.strip():
            self.transcript_chunks.append(text.strip())
    
    def end_session(self):
        """End the session and trigger background spool."""
        self.end_time = datetime.now()
        
        # Spawn background task (non-blocking)
        asyncio.create_task(self._spool_to_muninn())
    
    async def _spool_to_muninn(self):
        """POST aggregated transcript to Muninn (background task)."""
        if not self.muninn_url:
            log.debug("⊘ Muninn URL not configured, skipping spool")
            return
        
        if not self.transcript_chunks:
            log.debug("⊘ No transcript to spool")
            return
        
        # Aggregate transcript
        full_transcript = " ".join(self.transcript_chunks)
        
        payload = {
            "session_id": self.session_id,
            "type": "gemini_live_transcript",
            "content": full_transcript,
            "metadata": {
                "source": "gemini_relay",
                "start_time": self.start_time.isoformat() if self.start_time else "",
                "end_time": self.end_time.isoformat() if self.end_time else "",
                "chunk_count": len(self.transcript_chunks),
                "character_count": len(full_transcript)
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.muninn_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                log.info(f"✓ Spooled {len(full_transcript)} chars to Muninn")
        except Exception as e:
            log.error(f"✗ Failed to spool to Muninn: {e}")


# ============================================================================
# WebSocket Relay Handler
# ============================================================================

class RelayHandler:
    """
    Handles bidirectional message piping between client and Gemini.
    """
    
    def __init__(self, client_ws: WebSocketServerProtocol, session_id: str):
        self.client_ws = client_ws
        self.session_id = session_id
        self.gemini_ws: Optional[WebSocketClientProtocol] = None
        self.spooler = MemorySpooler()
        self.running = True
        self.messages_relayed = 0
    
    async def connect_to_gemini(self, api_key: str) -> bool:
        """Establish connection to Gemini Live API."""
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            self.gemini_ws = await websockets.connect(
                f"{GEMINI_WS_URL}?key={api_key}",
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
                ssl=ssl_context
            )
            log.info(f"✓ Connected to Gemini Live API (session: {self.session_id})")
            self.spooler.start_session(self.session_id)
            return True
        except Exception as e:
            log.error(f"✗ Failed to connect to Gemini: {e}")
            return False
    
    async def relay_messages(self):
        """
        Main relay loop - pipes messages bidirectionally.
        """
        tasks = [
            asyncio.create_task(self._client_to_gemini()),
            asyncio.create_task(self._gemini_to_client())
        ]
        
        try:
            # Wait for either task to finish
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Identify which task finished
            for task in done:
                name = "Client->Gemini" if task == tasks[0] else "Gemini->Client"
                log.info(f"🏁 {name} task finished (session: {self.session_id})")
                if task.exception():
                    log.error(f"✗ Task exception: {task.exception()}")
            
            self.running = False
            for task in pending:
                task.cancel()
                
        except Exception as e:
            log.error(f"✗ Relay error: {e}")
        finally:
            await self.cleanup()
    
    async def _client_to_gemini(self):
        """Pipe messages from client to Gemini."""
        try:
            while self.running:
                try:
                    # FastAPI WebSocket doesn't support 'async for'
                    data = await self.client_ws.receive()
                    
                    if data["type"] == "websocket.disconnect":
                        log.info(f"⊘ Client requested disconnect (session: {self.session_id})")
                        break
                        
                    message = data.get("text") or data.get("bytes")
                    if message is None:
                        continue

                    if not self.gemini_ws:
                        log.warning("⚠ Gemini connection not established, dropping message")
                        break
                        
                    await self.gemini_ws.send(message)
                    self.messages_relayed += 1
                except Exception as e:
                    log.error(f"✗ Failed to relay to Gemini: {e}")
                    log.error(traceback.format_exc())
                    break
        except WebSocketDisconnect:
            log.info(f"⊘ Client disconnected (session: {self.session_id})")
        except Exception as e:
            log.error(f"✗ Client->Gemini error: {e}")
            log.error(traceback.format_exc())
    
    async def _gemini_to_client(self):
        """Pipe messages from Gemini to client."""
        try:
            async for message in self.gemini_ws:
                if not self.running:
                    break
                
                try:
                    # _process_gemini_message handles discrimination and forwarding to client
                    await self._process_gemini_message(message)
                except Exception as e:
                    log.error(f"✗ Failed to send to client: {e}")
                    log.error(traceback.format_exc())
                    break
        except Exception as e:
            log.error(f"✗ Gemini->Client error: {e}")
            log.error(traceback.format_exc())
    
    async def _send_to_client(self, message):
        """Helper to send message to FastAPI WebSocket (text or bytes)."""
        try:
            if not self.running:
                return
            if isinstance(message, str):
                await self.client_ws.send_text(message)
            else:
                await self.client_ws.send_bytes(message)
        except (RuntimeError, Exception) as e:
            if "already completed" not in str(e):
                log.error(f"✗ WebSocket send error: {e}")

    async def _process_gemini_message(self, message):
        """
        Discriminate between:
        1. Raw binary audio (Gemini 1.5 style)
        2. JSON encapsulated in binary (Gemini 3.1 style)
        3. Raw JSON text frames
        """
        payload = None
        
        try:
            if isinstance(message, bytes):
                # Try to decode as UTF-8 JSON (Gemini 3.1 style)
                try:
                    text_payload = message.decode('utf-8')
                    payload = json.loads(text_payload)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    # Pure binary audio (Gemini 1.5 style)
                    # Spooler doesn't handle audio chunks, only transcripts
                    await self._send_to_client(message)
                    return
            elif isinstance(message, str):
                # Raw text frame (JSON)
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    log.warning(f"⚠ Received non-JSON text frame: {message[:100]}")
                    return

            if payload:
                log.info(f"⬅ Gemini message keys: {list(payload.keys())}")
                if "serverContent" in payload:
                    sc = payload["serverContent"]
                    
                    # 1. Model turn (Audio + Transcripts)
                    if "modelTurn" in sc:
                        for part in sc["modelTurn"].get("parts", []):
                            # Audio chunk (Unwrap from JSON)
                            if "inlineData" in part:
                                b64_audio = part["inlineData"].get("data")
                                if b64_audio:
                                    audio_bytes = base64.b64decode(b64_audio)
                                    # Forward as RAW BINARY for low-latency playback
                                    await self._send_to_client(audio_bytes)
                                    # Strip from JSON to keep metadata lean
                                    del part["inlineData"]
                            
                            # Transcript (Forward as side-channel events)
                            if "text" in part:
                                self.spooler.add_transcript(part["text"])
                                await self._send_to_client(json.dumps({
                                    "type": "voice_events",
                                    "event_type": "transcript",
                                    "source": "model",
                                    "text": part["text"]
                                }))

                    # 2. Input transcription
                    input_tx = sc.get("inputTranscription") or sc.get("input_transcription")
                    if input_tx:
                        await self._send_to_client(json.dumps({
                            "type": "voice_events",
                            "event_type": "transcript",
                            "source": "user",
                            "text": input_tx
                        }))

                # 3. Always forward the (now lean) JSON as text for metadata/protocol
                await self._send_to_client(json.dumps(payload))

        except Exception as e:
            log.error(f"✗ Error processing Gemini message: {e}")
            log.error(traceback.format_exc())
    
    async def cleanup(self):
        """Clean up connections and trigger memory spool."""
        self.running = False
        
        # End spooler session (triggers background POST to Muninn)
        self.spooler.end_session()
        
        # Close Gemini connection
        if self.gemini_ws:
            try:
                await self.gemini_ws.close()
            except:
                pass
        
        log.info(f"✓ Session cleanup complete: {self.session_id} (messages: {self.messages_relayed})")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Gemini Live WebSocket Relay",
    description="Lightweight WebSocket proxy for Gemini Live API",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Initialize on startup - fetch API key."""
    log.info("=" * 60)
    log.info("Gemini Live WebSocket Relay Starting")
    log.info("=" * 60)
    
    # Ensure log directory exists
    (Path.home() / ".gemini_relay").mkdir(parents=True, exist_ok=True)
    
    # Fetch API key
    api_key = await fetch_gemini_api_key()
    if not api_key:
        log.warning("⚠ GEMINI_API_KEY not available - connections will fail")
    else:
        log.info("✓ GEMINI_API_KEY ready")
    
    log.info(f"📡 Listening on {RELAY_HOST}:{RELAY_PORT}")
    log.info("=" * 60)


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """
    WebSocket endpoint for Gemini Live relay.
    
    Accepts client connection, opens secondary connection to Gemini,
    and pipes messages bidirectionally.
    """
    # Accept client connection
    await websocket.accept()
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    log.info(f"🔌 Client connected: {session_id}")
    
    # Get API key
    api_key = _gemini_api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        await websocket.send_json({"error": "API key not configured"})
        await websocket.close()
        return
    
    # Create relay handler
    relay = RelayHandler(websocket, session_id)
    
    # Connect to Gemini
    if not await relay.connect_to_gemini(api_key):
        await websocket.send_json({"error": "Failed to connect to Gemini"})
        await websocket.close()
        return
    
    # Start relay (bidirectional message piping)
    await relay.relay_messages()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "gemini_relay",
        "timestamp": datetime.now().isoformat(),
        "api_key_configured": bool(_gemini_api_key or os.getenv("GEMINI_API_KEY"))
    }


@app.get("/metrics")
async def metrics():
    """Basic metrics endpoint."""
    return {
        "service": "gemini_relay",
        "uptime": "N/A",  # Would track with proper metrics
        "memory_usage": "N/A"  # Would track with psutil
    }


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the WebSocket relay server."""
    import uvicorn
    
    uvicorn.run(
        app,
        host=RELAY_HOST,
        port=RELAY_PORT,
        log_level="info",
        ws_ping_interval=30,
        ws_ping_timeout=10
    )


if __name__ == "__main__":
    main()
