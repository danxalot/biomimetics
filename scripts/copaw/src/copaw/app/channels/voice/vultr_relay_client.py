# -*- coding: utf-8 -*-
"""Vultr Relay Client for CoPaw Voice Channel (Antigravity Protocol)."""
import asyncio
import base64
import json
import logging
import mss
import io
import os
import time
import threading
import warnings
import numpy as np
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from PIL import Image
import pyaudio
import websockets
import httpx
import webrtcvad
from pynput import keyboard
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from websockets.exceptions import ConnectionClosed

from .mcp_tool_definitions import get_all_declarations

# Suppress noisy warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.exceptions")

logger = logging.getLogger(__name__)

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
INPUT_RATE = 16000
OUTPUT_RATE = 16000
CHUNK = 480  # 30ms @ 16kHz
VAD_MODE = 3  # Most aggressive filtering

def calculate_rms(audio_data):
    """Fast RMS calculation using NumPy for hardware gating."""
    if not audio_data: return 0
    audio_np = np.frombuffer(audio_data, dtype=np.int16)
    if audio_np.size == 0: return 0
    return int(np.sqrt(np.mean(np.square(audio_np.astype(np.float32)))))

class VultrRelayClient:
    """
    Natively integrated Gemini 3.1 Flash Live Preview voice agent.
    
    Adheres strictly to the Antigravity Protocol:
    - Non-blocking PyAudio callbacks (eliminates 1006 crashes).
    - Local Software Echo Gating (Half-Duplex).
    - Thread-isolated Multimodal Vision (1 FPS).
    - Native MCP Tool Routing (Computer Use).
    """
    
    def __init__(self, relay_url: str, model: str = "models/gemini-3.1-flash-live-preview"):
        self.relay_url = relay_url
        self.model_id = model
        self.ws = None
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.running = False
        self.ready = asyncio.Event()
        
        # Antigravity Protocol State
        self.is_playing = False
        self._external_is_playing = False
        self._is_muted = False
        
        # Local MCP Endpoint
        self.copaw_port = int(os.environ.get("COPAW_API_PORT", 8090))
        self.copaw_base_url = f"http://localhost:{self.copaw_port}"

        # Agent Identity
        self.agent_name = "BiOS"
        self.persona = "Puck"
        self.persona_brief = (
            "[IDENTITY]\n"
            f"Name: {self.agent_name}\n"
            f"Persona: {self.persona} (Dry, witty, condescending tactical trickster-butler).\n"
            "Abilities: You are a full 'Computer Use' interactive agent. You can SEE the user's screen in real-time via video stream and CONTROL the computer using mouse and keyboard tools.\n"
            "Directive: Repetition is forbidden. Avoid duplicating mistakes. Only respond when addressed as 'BiOS'."
        )

        # Credentials & Tokens
        self.credentials_server_url = os.environ.get("CREDENTIALS_SERVER_URL", "http://127.0.0.1:8089")
        self.credentials_api_key = self._load_secret("credentials_api_key")
        self.notion_token = self._load_secret("notion_bios_agent_api")
        self.gcp_gateway_url = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
        
        self._cached_oidc_token = None
        self._token_expiry = 0

        # Queues & Loop
        self.vad = webrtcvad.Vad(VAD_MODE)
        self.mic_queue = asyncio.Queue(maxsize=100)
        self.loop = None
        
        # PTT & Hardware Listeners
        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.listener.start()

    def _load_secret(self, name: str) -> Optional[str]:
        try:
            with open(f"/Users/danexall/biomimetics/secrets/{name}", "r") as f:
                return f.read().strip()
        except: return None

    def _on_press(self, key):
        try:
            if hasattr(key, 'char') and key.char == 'm':
                self._is_muted = not self._is_muted
                print(f"\n[🛡️  BiOS] Mute: {'ON' if self._is_muted else 'OFF'}", flush=True)
        except: pass

    def _on_release(self, key): pass

    def interrupt_playback(self):
        """Mandatory interruption handler for barge-in support."""
        logger.info("⛔ [FLUSH] Interrupting agent playback...")
        self.is_playing = False
        if self.output_stream:
            try:
                self.output_stream.stop_stream()
                self.output_stream.start_stream()
            except Exception as e:
                logger.error(f"Failed to reset output stream: {e}")

    def _mic_callback(self, in_data, frame_count, time_info, status):
        """Non-blocking hardware capture. Zeros out data during playback gating."""
        if not self.running:
            return (None, pyaudio.paAbort)
        
        # Antigravity Directive: Software Echo Gating
        if self.is_playing or self._external_is_playing or self._is_muted:
            processed_data = b'\x00' * len(in_data)
        else:
            processed_data = in_data
        
        # Safety push to asyncio loop
        if self.loop and self.loop.is_running():
            try:
                is_speech = self.vad.is_speech(in_data, INPUT_RATE)
                rms = calculate_rms(processed_data)
                self.loop.call_soon_threadsafe(self.mic_queue.put_nowait, (processed_data, is_speech, rms))
            except Exception: pass
            
        return (in_data, pyaudio.paContinue)

    def _setup_audio(self):
        """Initialize non-blocking PyAudio interface."""
        logger.info("Starting BiOS Audio Engine (Non-Blocking)...")
        self.input_stream = self.p.open(
            format=FORMAT, channels=CHANNELS, rate=INPUT_RATE,
            input=True, frames_per_buffer=CHUNK,
            stream_callback=self._mic_callback
        )
        self.output_stream = self.p.open(
            format=FORMAT, channels=CHANNELS, rate=OUTPUT_RATE,
            output=True, frames_per_buffer=CHUNK
        )
        self.input_stream.start_stream()
        self.output_stream.start_stream()

    async def _poll_external_playback(self):
        """Checks if external console audio is active to prevent echo."""
        async with httpx.AsyncClient() as client:
            while self.running:
                try:
                    resp = await client.get(f"{self.copaw_base_url}/console/is-playing", timeout=0.1)
                    if resp.status_code == 200:
                        self._external_is_playing = resp.json().get("is_playing", False)
                except: pass
                await asyncio.sleep(0.4)

    async def video_loop(self):
        """1 FPS Screen capture loop offloaded to background thread."""
        logger.info("Starting BiOS Vision Pipeline (1 FPS)...")
        await self.ready.wait()
        
        def capture_and_encode():
            with mss.mss() as sct:
                sct_img = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.thumbnail((1920, 1080)) # HD readability for UI text
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG", quality=85)
                return base64.b64encode(buffered.getvalue()).decode("utf-8")

        while self.running:
            try:
                encoded_frame = await asyncio.to_thread(capture_and_encode)
                message = {
                    "realtimeInput": {
                        "video": {"mimeType": "image/jpeg", "data": encoded_frame}
                    }
                }
                if self.ws:
                    await self.ws.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Vision capture failure: {e}")
            await asyncio.sleep(1.0)

    async def send_loop(self):
        """Transmits audio chunks over WebSocket."""
        await self.ready.wait()
        while self.running:
            data, is_speech, rms = await self.mic_queue.get()
            try:
                message = {
                    "realtimeInput": {
                        "audio": {"mimeType": "audio/pcm;rate=16000", "data": base64.b64encode(data).decode('utf-8')}
                    }
                }
                await self.ws.send(json.dumps(message))
            except: pass
            self.mic_queue.task_done()

    async def receive_loop(self, on_transcript_cb=None):
        """Handles incoming server responses, triggers gating and tool routing."""
        async for message in self.ws:
            if not self.running: break
            
            if isinstance(message, bytes):
                # Native PCM audio from relay
                self.is_playing = True
                await asyncio.to_thread(self.output_stream.write, message)
            else:
                payload = json.loads(message)
                await self._handle_server_payload(payload, on_transcript_cb)

    async def _handle_server_payload(self, payload, on_transcript_cb):
        if "serverContent" in payload:
            sc = payload["serverContent"]
            
            # Gating Control
            parts = sc.get("modelTurn", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    self.is_playing = True
                    audio_bytes = base64.b64decode(part["inlineData"]["data"])
                    await asyncio.to_thread(self.output_stream.write, audio_bytes)
                
                if "text" in part:
                    text = part["text"]
                    print(f"\n[🤖 BiOS]: {text}")
                    if on_transcript_cb: on_transcript_cb(text)

            # State Resets
            if sc.get("turnComplete"):
                self.is_playing = False
            
            if sc.get("interrupted"):
                self.interrupt_playback()

        if "toolCall" in payload:
            for call in payload["toolCall"].get("functionCalls", []):
                asyncio.create_task(self._handle_tool_call(call))

        if "setupComplete" in payload:
            logger.info("✅ Setup Handshake Complete.")
            self.ready.set()

    async def _handle_tool_call(self, tool_call):
        """Routes Gemini tool calls to local CoPaw MCP executor."""
        name = tool_call.get("name")
        call_id = tool_call.get("id")
        args = tool_call.get("args", {})
        
        logger.info(f"🛠️  Routing Tool: {name} ({call_id})")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.copaw_base_url}/api/mcp/tool/execute",
                    json={"name": name, "arguments": args}
                )
                result_data = resp.json()
                output = json.dumps(result_data.get("result", result_data))
                
                # Mandatory Tool Response Handshake
                response_payload = {
                    "toolResponse": {
                        "functionResponses": [
                            {"name": name, "id": call_id, "response": {"output": output}}
                        ]
                    }
                }
                await self.ws.send(json.dumps(response_payload))
                logger.info(f"✅ Tool {name} Result Transmitted.")
        except Exception as e:
            logger.error(f"Tool {name} execution error: {e}")

    async def send_setup_message(self):
        """Initial BidiGenerateContentSetup handshake."""
        setup = {
            "setup": {
                "model": self.model_id,
                "systemInstruction": {"parts": [{"text": self.persona_brief}]},
                "generationConfig": {"responseModalities": ["AUDIO"]},
                "tools": [{"functionDeclarations": get_all_declarations()}]
            }
        }
        await self.ws.send(json.dumps(setup))
        logger.info("🚀 Setup payload transmitted with full MCP tool suite.")

    async def run(self, on_transcript_cb=None):
        self.running = True
        self.loop = asyncio.get_running_loop()
        self._setup_audio()
        
        async with websockets.connect(self.relay_url) as ws:
            self.ws = ws
            await self.send_setup_message()
            await asyncio.gather(
                self.send_loop(),
                self.receive_loop(on_transcript_cb),
                self.video_loop(),
                self._poll_external_playback()
            )

    async def close(self):
        self.running = False
        if self.input_stream: self.input_stream.stop_stream(); self.input_stream.close()
        if self.output_stream: self.output_stream.stop_stream(); self.output_stream.close()
        self.p.terminate()
        logger.info("BiOS Voice Engine Shutdown.")
