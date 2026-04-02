# -*- coding: utf-8 -*-
"""Vultr Relay Client for CoPaw Voice Channel."""
import asyncio
import base64
import json
import logging
import wave
import wave
# import audioop  # Removed for Python 3.13+ compatibility
import pyaudio
import websockets
import httpx
import webrtcvad
import time
import threading
import statistics
import warnings
import numpy as np
import os
from websockets.exceptions import ConnectionClosed
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.exceptions")
from collections import deque
from pynput import keyboard
from datetime import datetime, timezone
# from copaw.app.console_push_store import append as push_store_append  # REMOVED: Process isolation issues

logger = logging.getLogger(__name__)

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
INPUT_RATE = 16000
OUTPUT_RATE = 24000
CHUNK = 480  # Task 3: Restored to 30ms @ 16kHz
VAD_MODE = 3  # Most aggressive filtering
DUCKING_TIMEOUT_SEC = 0.3  # Reset ducking if no audio received for 300ms

def calculate_rms(audio_data):
    """Fast RMS calculation using NumPy to avoid blocking the event loop."""
    if not audio_data: return 0
    # Convert bytes to numpy array (16-bit PCM = int16)
    audio_np = np.frombuffer(audio_data, dtype=np.int16)
    if audio_np.size == 0: return 0
    # Vectorized root-mean-square calculation
    return int(np.sqrt(np.mean(np.square(audio_np.astype(np.float32)))))

class VultrRelayClient:
    """
    Client for the Vultr Gemini 3.1 Live WebSocket Relay.
    
    Handles:
    - WebSocket connection to the relay
    - Audio capture from local microphone via PyAudio
    - Audio playback to local speakers via PyAudio
    - Bidirectional communication with the relay
    """
    
    def __init__(self, relay_url: str):
        self.relay_url = relay_url
        self.ws = None
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.running = False
        self.is_playing = False  # Flag for ducking (echo cancellation)
        self.last_audio_received_at = 0  # Timestamp of last received audio chunk
        self.current_speaker_rms = 0  # Fairy Dust v2: Track speaker energy
        self.ready = asyncio.Event()  # Sync flag for handshake completion
        
        # Load Notion Token from secrets
        try:
            with open("/Users/danexall/biomimetics/secrets/notion_bios_agent_api", "r") as f:
                self.notion_token = f.read().strip()
        except Exception as e:
            logger.error(f"Failed to load Notion token: {e}")
            self.notion_token = None

        self.notion_client = httpx.AsyncClient(
            base_url="https://api.notion.com/v1",
            headers={
                "Authorization": f"Bearer {self.notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
        )

        # Initialize VAD, PTT & Buffers
        self.vad = webrtcvad.Vad(VAD_MODE)
        self.ptt_active = False
        self.mic_muted = False  # Added: Microphone mute toggle
        self.noise_history = deque(maxlen=100) # Rolling baseline (3s window at 30ms frames)
        self.mic_queue = asyncio.Queue(maxsize=60)  # Task 1: Increased to 60 (1.2s @ 20ms) to survive stabilization delay
        self.loop = None                  # Initialized at runtime
        self.mic_thread = None            # Producer thread
        self._floor_update_counter = 0    # Recalculate median every 30 frames
        self._cached_floor = 40           # Initial fallback floor
        self._first_packet_logged = False # Diagnostic flag for first outbound packet
        
        # Start keyboard listener for PTT
        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.listener.start()
        logger.info("VAD, PTT & Dynamic Baseline initialized.")
        
        # Determine CoPaw API Port (Task: HUD Stability)
        self.copaw_port = int(os.environ.get("COPAW_API_PORT", 8090))
        self.copaw_base_url = f"http://localhost:{self.copaw_port}"
        logger.info(f"🚀 HUD Relay Target: {self.copaw_base_url}")

    def _on_press(self, key):
        try:
            if key == keyboard.Key.space:
                if not self.ptt_active:
                    self.ptt_active = True
                    print("\n[🔥 PTT ACTIVE] Force Transmitting...          ", flush=True)
            elif hasattr(key, 'char') and key.char == 'm':
                self.mic_muted = not self.mic_muted
                status = "[🔇 MIC MUTED]" if self.mic_muted else "[🎤 MIC LIVE]"
                print(f"\n{status}                                         ", flush=True)
        except AttributeError:
            pass # Ignore special keys that don't have .char

    def _on_release(self, key):
        if key == keyboard.Key.space:
            self.ptt_active = False
            print("\n[☁️ PTT RELEASED] VAD Gate restored.            ", flush=True)

    def get_dynamic_floor(self):
        """Calculate dynamic RMS floor with rate-limiting to save CPU."""
        self._floor_update_counter += 1
        # Only recalculate the median once every 30 frames (~1 second)
        if self._floor_update_counter >= 30:
            self._floor_update_counter = 0
            if len(self.noise_history) >= 10:
                # Median is robust against volume spikes; 50% buffer for breathing room
                raw_floor = statistics.median(self.noise_history) * 1.5
                self._cached_floor = min(raw_floor, 400) # Hard cap (Wiki aligned) to prevent runaway adaptation
        return self._cached_floor

    def _mic_capture_thread(self):
        """Dedicated background thread for hardware I/O to prevent async loop stalls."""
        logger.info("Microphone producer thread started.")
        frame_count = 0
        last_log_time = time.time()
        
        while self.running:
            try:
                # 1. Blocking Read (Safe here in a dedicated OS thread)
                data = self.input_stream.read(CHUNK, exception_on_overflow=False)
                
                # 2. Fast Math (VAD and RMS) and Alignment
                is_speech = self.vad.is_speech(data, 16000)
                rms = calculate_rms(data)
                
                # 2b. Force Little-Endian 16-bit PCM for server-side alignment (Task 1)
                aligned_chunk = np.frombuffer(data, dtype='<i2').tobytes()
                
                # 3. Push to Async Queue
                if self.loop and self.loop.is_running():
                    # Task 3: Safe Put Helper (Drop frame instead of crashing if queue overflows)
                    def safe_put(payload, sp, r):
                        try:
                            self.mic_queue.put_nowait((payload, sp, r))
                        except asyncio.QueueFull:
                            pass # Drop frame gracefully
                    
                    self.loop.call_soon_threadsafe(safe_put, aligned_chunk, is_speech, rms)
                
                # Diagnostic: Frame Rate
                frame_count += 1
                now = time.time()
                if now - last_log_time >= 1.0:
                    logger.debug(f"🎙️ [PRODUCER] Frame rate: {frame_count} fps")
                    frame_count = 0
                    last_log_time = now

            except Exception as e:
                if self.running:
                    logger.error(f"Mic capture thread error: {e}")
                break
        logger.info("Microphone producer thread terminated.")

    async def connect(self):
        """Connect to the Vultr relay."""
        logger.info(f"Connecting to Vultr relay at {self.relay_url}...")
        try:
            self.ws = await websockets.connect(self.relay_url)
            logger.info("Connected to Vultr relay successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Vultr relay: {e}")
            return False

    def _setup_audio(self):
        """Setup PyAudio input and output streams with separate rates."""
        logger.info(f"Setting up PyAudio: Input={INPUT_RATE}Hz, Output={OUTPUT_RATE}Hz")
        
        self.input_stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=INPUT_RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        self.output_stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_RATE,
            output=True,
            output_device_index=1, # 🚨 THE FIX: Force routing to MacBook Pro Speakers
            frames_per_buffer=CHUNK
        )
        logger.info(f"PyAudio Interface Ready: Mic={INPUT_RATE}Hz | Spkr={OUTPUT_RATE}Hz")
        print(f"[🎤] BiOS Audio Interface Started: {INPUT_RATE}Hz(In) / {OUTPUT_RATE}Hz(Out)")

    async def send_setup_message(self):
        """Send the initial setup message to Gemini with tool definitions."""
        # Note: The relay targets the specific model via URL, but we provide it here too.
        setup_message = {
            "setup": {
                "model": "models/gemini-3.1-flash-live-preview",
                "generationConfig": {
                    "responseModalities": ["AUDIO"]
                },
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
                "tools": [
                    {
                        "functionDeclarations": [
                            {
                                "name": "render_canvas",
                                "description": "Render visual components (HTML or Markdown) in the CoPaw HUD.",
                                "parameters": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "view": {"type": "STRING", "description": "View type (email, research, task, status)."},
                                        "content": {"type": "STRING", "description": "HTML or Markdown content."}
                                    },
                                    "required": ["view", "content"]
                                }
                            },
                            {
                                "name": "query_memory",
                                "description": "Query the unified memory system (MuninnDB working memory + MemU archive memory).",
                                "parameters": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "query": {"type": "STRING", "description": "The search query for memory retrieval."}
                                    },
                                    "required": ["query"]
                                }
                            },
                            {
                                "name": "trigger_notion_action",
                                "description": "Trigger a Notion action or workflow (create tasks, update pages, plan features).",
                                "parameters": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "action": {
                                            "type": "STRING",
                                            "enum": ["create_task", "update_page", "plan_feature", "review_code", "summarize_meeting"]
                                        },
                                        "data": {"type": "OBJECT", "description": "Action-specific payload."}
                                    },
                                    "required": ["action", "data"]
                                }
                            },
                            {
                                "name": "save_to_notion",
                                "description": "Save structured text to Notion for phone review.",
                                "parameters": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "content": {"type": "STRING", "description": "Content to save."},
                                        "category": {"type": "STRING", "description": "Target category or database."}
                                    },
                                    "required": ["content"]
                                }
                            }
                        ]
                    }
                ]
            }
        }
        await self.ws.send(json.dumps(setup_message))
        logger.info("Sent setup message with render_canvas tool definition.")

    async def send_tool_response(self, call_id: str, name: str, output: str):
        """Send tool execution response back to Gemini."""
        response_message = {
            "toolResponse": {
                "functionResponses": [
                    {
                        "name": name,
                        "id": call_id,
                        "response": {"output": output}
                    }
                ]
            }
        }
        await self.ws.send(json.dumps(response_message))
        logger.info(f"Sent tool_response for {name} ({call_id}).")
        
        # Log tool performance to Notion if IDs are provided
        asyncio.create_task(self._log_performance_to_notion(name, call_id, "success"))

    async def _log_session_to_notion(self, speaker: str, text: str):
        """Log a conversation turn to the Notion 'Voice Session Logs' database."""
        database_id = "3344d2d9-fc7c-8116-b0ed-c5840aaef8a4"
        if not self.notion_token or not text:
            return

        try:
            data = {
                "parent": {"database_id": database_id},
                "properties": {
                    "Name": {"title": [{"text": {"content": speaker}}]},
                    "Date": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                    "Transcript": {"rich_text": [{"text": {"content": text}}]},
                    "Session ID": {"rich_text": [{"text": {"content": "voice_session_" + datetime.now().strftime("%Y%m%d")}}] }
                }
            }
            await self.notion_client.post("/pages", json=data)
        except Exception as e:
            logger.error(f"Notion session log failure: {e}")

    async def _log_performance_to_notion(self, tool_name: str, call_id: str, status: str, latency_ms: int = 0):
        """Log tool performance metadata to the Notion 'Tool Performance' database."""
        database_id = "3344d2d9-fc7c-8134-9cce-e829fef9c6f5"
        if not self.notion_token:
            return

        try:
            data = {
                "parent": {"database_id": database_id},
                "properties": {
                    "Tool Name": {"title": [{"text": {"content": tool_name}}]},
                    "Call ID": {"rich_text": [{"text": {"content": call_id}}]},
                    "Latency (ms)": {"number": latency_ms},
                    "Status": {"select": {"name": status}}
                }
            }
            await self.notion_client.post("/pages", json=data)
        except Exception as e:
            logger.error(f"Notion performance log failure: {e}")

    async def _handle_tool_call(self, tool_call):
        """Handle a tool call from Gemini with robust ID extraction."""
        name = tool_call.get("name")
        call_id = tool_call.get("id", tool_call.get("call_id", tool_call.get("callId", "")))
        args = tool_call.get("args", {})
        start_time = time.time()
        
        if not name:
            logger.warning(f"Received tool call without name: {tool_call}")
            return
            
        logger.info(f"Routing tool call: {name} ({call_id})")

        if name == "render_canvas":
            view = args.get("view", "generic")
            content = args.get("content", "")
            hud_payload = f"### BiOS HUD: {view.upper()}\n\n{content}"
            # Send tool response immediately back to Gemini
            await self.send_tool_response(call_id, name, f"Acknowledged {view} render request.")

            async def _render_in_background():
                try:
                    # CROSS-PROCESS FIX: Push to local CoPaw server via HTTP
                    await self._push_to_console("console:default", hud_payload, sticky=True, type="canvas_update")
                    logger.info(f"BiOS HUD Rendered: {view} ({call_id})")
                except Exception as e:
                    logger.error(f"HUD render failure: {e}")

            asyncio.shield(asyncio.create_task(_render_in_background()))

        elif name == "query_memory":
            query = args.get("query", "")
            # TODO: Integrate with actual memory service (e.g., call MuninnDB or localhost:8088)
            response = f"Memory search for '{query}' completed. (Backend integration pending)."
            await self.send_tool_response(call_id, name, response)

        elif name == "trigger_notion_action":
            action = args.get("action", "unspecified")
            # TODO: Integrate with Notion worker or localhost:8088
            response = f"Notion action '{action}' triggered. (Integration pending)."
            await self.send_tool_response(call_id, name, response)

        elif name == "save_to_notion":
            # TODO: Direct save to Notion
            await self.send_tool_response(call_id, name, "Content saved to Notion.")

        else:
            logger.warning(f"Tool {name} not yet implemented in Vultr relay.")
            await self.send_tool_response(call_id, name, f"Tool {name} is defined but not implemented locally.")

        # Log performance
        latency = int((time.time() - start_time) * 1000)
        asyncio.create_task(self._log_performance_to_notion(name, call_id, "completed", latency))

    def build_realtime_input(self, data: str) -> dict:
        """Build a Gemini 3.1 Live compatible realtimeInput message (Stable Schema)."""
        return {
            "realtimeInput": {
                "audio": {
                    "mimeType": "audio/pcm;rate=16000",
                    "data": data
                }
            }
        }

    async def send_loop(self):
        """Async consumer loop: sends 30ms frames individually for precise alignment."""
        try:
            logger.info("Starting audio send loop (30ms Individuated)...")
            # Task 3: Wait for setupComplete handshake and 0.5s stabilization
            await self.ready.wait()
            self._packets_sent_count = 0  # Reset for pre-flight silence
            self.silence_ticks = 0        # ADDED: Track frames since last speech
            
            while self.running:
                # 1. Block until at least one frame is available
                data, is_speech, current_mic_rms = await self.mic_queue.get()

                # 2. Aggressively drain all pending frames to guarantee zero latency (Drop to Latest)
                while not self.mic_queue.empty():
                    try:
                        # Overwrite with the freshest frame, dropping the old ones
                        data, is_speech, current_mic_rms = self.mic_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                # 2. Echo Cancellation (Ducking)
                if self.is_playing:
                    if time.time() - self.last_audio_received_at > DUCKING_TIMEOUT_SEC:
                        self.is_playing = False
                    else:
                        if not self.ptt_active: # <--- FIX: PTT overrides ducking
                            continue

                # 3. Mute Override (Queue Drainage)
                if self.mic_muted:
                    continue # Frame was drained, but skip processing

                # 3. Dynamic Baseline Maintenance
                if not is_speech:
                    self.noise_history.append(current_mic_rms)

                dynamic_floor = self.get_dynamic_floor()

                # 4. Final Gate & Transmission (30ms frames)
                # Separate "is the mic active" from "should we transmit"
                is_active = self.ptt_active or (is_speech and current_mic_rms > dynamic_floor)
                
                if is_active:
                    self.silence_ticks = 0
                else:
                    self.silence_ticks += 1

                # CRITICAL FIX: Send audio if active, OR send 50 frames (~1.5s) of silence after speech stops.
                # Gemini's server-side VAD *must hear trailing silence* to know you finished talking.
                should_send = is_active or (self.silence_ticks < 50)
                
                if should_send:
                    if is_active:
                        pass
                    else:
                        # Overwrite actual background noise with pure digital silence.
                        # This triggers Gemini's VAD turn-completion without transmitting your background audio.
                        data = b'\x00' * len(data)
                        pass # Triggers Gemini's VAD turn-completion without transmitting background audio.

                    # Task 1 & 2: Restore Stable 'audio' Schema
                    encoded_chunk = base64.b64encode(data).decode('utf-8')
                    message = self.build_realtime_input(encoded_chunk)
                    
                    # Text Frame (Opcode 0x1) via json.dumps (no .encode)
                    await self.ws.send(json.dumps(message, separators=(',', ':')))
                    
                # 5. Rate Limit / Event Loop Breathe
                await asyncio.sleep(0)
                
        except Exception as e:
            logger.error(f"Error in send_loop: {e}")
        finally:
            logger.info("Audio send loop terminated.")

    async def receive_loop(self, on_transcript_cb=None):
        """Receive responses from relay (text/audio) with ducking triggers."""
        logger.info("Starting audio receive loop...")
        try:
            async for message in self.ws:
                if not self.running:
                    break
                
                if isinstance(message, bytes):
                    # SAFETY CHECK: Is this actually a binary-encoded JSON message from the relay?
                    if len(message) > 0 and message[0] == ord('{'):
                        try:
                            json_str = message.decode('utf-8')
                            data = json.loads(json_str)
                            # If it parsed, it's NOT audio. Handle as JSON.
                            await self._handle_json_message(data, on_transcript_cb)
                            continue
                        except:
                            pass # Not JSON, proceed as audio
                    
                    # Raw binary audio from relay
                    # Engage ducking to prevent echoing speaker output back to mic
                    self.is_playing = True
                    self.last_audio_received_at = time.time()
                    
                    # Update speaker RMS for dynamic thresholding
                    self.current_speaker_rms = calculate_rms(message)
                    
                    # Visual feedback for speaker handoff
                    # await asyncio.to_thread(self.output_stream.write, message) handled below
                    # Offload blocking I/O to a thread to prevent event loop starvation
                    await asyncio.to_thread(self.output_stream.write, message)
                else:
                    # JSON message (transcript, metadata, or embedded audio)
                    data = json.loads(message)
                    await self._handle_json_message(data, on_transcript_cb)
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"❌ [WEBSOCKET] Connection closed. Code: {e.code}, Reason: {e.reason}")
            raise # Propagate to run() for backoff/reconnect
        except Exception as e:
            logger.error(f"Error in receive_loop: {e}")
            raise
        finally:
            logger.info("Audio receive loop terminated.")

    async def _handle_json_message(self, payload, on_transcript_cb=None):
        """Strictly unpack serverContent for audio and tool execution."""
        
        # Root Key Check
        if "serverContent" in payload:
            sc = payload["serverContent"]
            
            # 2. Hardcoded Traversal for Model Turn Parts
            parts = sc.get("modelTurn", {}).get("parts", [])
            
            for part in parts:
                # 3a. Audio Extraction
                if "inlineData" in part and "data" in part["inlineData"]:
                    audio_payload = part["inlineData"]["data"]
                    self.is_playing = True
                    self.last_audio_received_at = time.time()
                    audio_bytes = base64.b64decode(audio_payload)
                    
                    # Update speaker RMS for dynamic thresholding
                    self.current_speaker_rms = calculate_rms(audio_bytes)
                    
                    # await asyncio.to_thread(self.output_stream.write, audio_bytes) handled below
                    # Offload blocking I/O to a thread to prevent event loop starvation
                    await asyncio.to_thread(self.output_stream.write, audio_bytes)
                
                # 3b. Tool Call Extraction
                if "functionCall" in part:
                    print(f"\n[🔥 TOOL CALLS]: {part['functionCall'].get('name')}")
                    asyncio.create_task(self._handle_tool_call(part["functionCall"]))

                # 3c. Transcript Extraction
                if "text" in part:
                    text = part["text"]
                    print(f"\n[📝 MODEL TRANSCRIPT]: {text}")
                    if on_transcript_cb:
                        on_transcript_cb(text)

            # 4. Tool Call (Top-Level fallback)
            if "toolCall" in sc:
                tc = sc["toolCall"]
                if "functionCalls" in tc:
                    for fc in tc["functionCalls"]:
                        print(f"\n[🔥 TOOL CALLS]: {fc.get('name')}")
                        await self._handle_tool_call(fc)

            # 5. Flush state on turnComplete
            if sc.get("turnComplete"):
                self.is_playing = False
                self.current_speaker_rms = 0 # Decay instantly
                print("\r[🏁 Turn Complete]", flush=True)

        # Catch top-level Tool Calls (Gemini Live Schema)
        if "toolCall" in payload:
            print("\r[🔥 TOOL CALLS] Intercepted! Executing Command...          ", flush=True)
            for call in payload["toolCall"].get("functionCalls", []):
                await self._handle_tool_call(call)

        # Catch Setup Complete
        if "setupComplete" in payload:
            logger.info("✅ [HEARTBEAT] Setup message acknowledged. Waiting 0.5s for state stabilization...")
            print("\n[✅ BiOS LIVE] Handshake successful. Initializing stream...          ", flush=True)
            # Add silent start buffer (0.5s) to ensure the session is ready (Task 3)
            await asyncio.sleep(0.5)
            self.ready.set()

        # Side-channel transcript (relay discrimination layer)
        if payload.get("type") == "voice_events" and payload.get("event_type") == "transcript":
            text = payload.get("text", "")
            source = payload.get("source", "model")
            print(f"\n[📝 TRANSCRIPT]: {text}")
            prefix = "🗣️ User:" if source == "user" else "🤖 Gemini:"
            # async update of the console
            asyncio.create_task(self._push_to_console("console:default", f"{prefix} {text}", sticky=False, type="text"))
            # Log turn to Notion
            asyncio.create_task(self._log_session_to_notion("User" if source == "user" else "Gemini", text))
            if on_transcript_cb:
                on_transcript_cb(text)

    async def _push_to_console(self, session_id, text, sticky=False, type="text"):
        """Forward a message to the CoPaw console router via HTTP POST."""
        try:
            url = f"{self.copaw_base_url}/console/push"
            payload = {
                "session_id": session_id,
                "text": text,
                "sticky": sticky,
                "type": type
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=2.0)
                if resp.status_code != 200:
                    logger.warning(f"Failed to push to console: {resp.status_code}")
                else:
                    logger.debug("Successfully pushed to console via HTTP.")
        except Exception as e:
            # Fallback to local store silently if server is not running
            # and we are running in the same process (rare but possible during tests)
            try:
                from copaw.app.console_push_store import append
                await append(session_id, text, sticky=sticky, type=type)
            except:
                logger.error(f"Console push communication failure: {e}")

    async def run(self, on_transcript_cb=None):
        """Run both loops with exponential backoff and background producer thread."""
        self.running = True
        self.loop = asyncio.get_running_loop()
        self._setup_audio()
        
        # Start the background mic producer once
        if not self.mic_thread or not self.mic_thread.is_alive():
            self.mic_thread = threading.Thread(target=self._mic_capture_thread, daemon=True)
            self.mic_thread.start()
        
        retry_count = 0
        while self.running:
            try:
                async with websockets.connect(self.relay_url) as websocket:
                    self.ws = websocket
                    logger.info(f"✅ [HEARTBEAT] Connected to relay: {self.relay_url}")
                    retry_count = 0 # Reset on success
                    
                    # Ensure we wait for the NEW setupComplete handshake before sending
                    self.ready.clear()
                    
                    # Send initial setup with tools
                    await self.send_setup_message()
                    
                    # Run loops concurrently
                    await asyncio.gather(
                        self.send_loop(),
                        self.receive_loop(on_transcript_cb)
                    )
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                if not self.running: break
                retry_count += 1
                delay = min(retry_count * 2, 30)
                logger.warning(f"⚠️ [RELAY] Connection lost ({e}). Retrying in {delay}s (Attempt {retry_count})...")
                await asyncio.sleep(delay)
            except Exception as e:
                if not self.running: break
                logger.error(f"❌ [RELAY] Unexpected error in run loop: {e}")
                await asyncio.sleep(5)

    async def close(self):
        """Cleanup resources."""
        self.running = False
        if self.ws:
            await self.ws.close()
        
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
            
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
            
        self.p.terminate()
        logger.info("VultrRelayClient resources cleaned up.")
