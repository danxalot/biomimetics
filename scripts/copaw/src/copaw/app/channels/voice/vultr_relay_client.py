# -*- coding: utf-8 -*-
"""Vultr Relay Client for CoPaw Voice Channel (Antigravity Protocol).

Client for the Vultr Relay (Gemini 3.1 Flash Live wire format, Nemotron backend).

Adheres strictly to the Antigravity Protocol:
- Non-blocking PyAudio callbacks (eliminates 1006 crashes).
- Local Software Echo Gating (Half-Duplex).
- Thread-isolated Multimodal Vision (1 FPS).
- Native MCP Tool Routing (Computer Use).
"""
import asyncio
import base64
import json
import logging
import os
import tempfile
import time
import threading
import warnings
import webbrowser
import numpy as np
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from PIL import Image
import subprocess
import websockets
import httpx
import webrtcvad
from websockets.exceptions import ConnectionClosed

from .vision_worker import capture_and_encode
from .telemetry import VoiceTelemetry
from .mcp_tool_definitions import get_all_declarations
from ...phantom import get_phantom_controller

# Suppress noisy warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.exceptions")

# Suppress agentscope MCP cleanup warnings (logged internally before exception propagates)
import logging as _logging
class _CancelScopeFilter(_logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return "cancel scope" not in msg and "different task" not in msg

_logging.getLogger("agentscope.mcp._stateful_client_base").addFilter(_CancelScopeFilter())

logger = logging.getLogger(__name__)

_MUNINN_TURN = "/Users/danexall/biomimetics/scripts/mcp/muninn_turn.py"


def _muninn_fns():
    """Load local-Muninn activate/remember. Fail closed; never touch GCP."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("muninn_turn_local", _MUNINN_TURN)
        if spec is None or spec.loader is None:
            return None, None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "activate_context", None), getattr(mod, "remember_turn", None)
    except Exception:
        return None, None

# Audio configuration
CHANNELS = 1
INPUT_RATE = 16000
OUTPUT_RATE = 24000  # Gemini Live native output rate
CHUNK = 480  # 30ms @ 16kHz
VAD_MODE = 2  # Aggressive filtering (mode 3 too aggressive for 16kHz)

def calculate_rms(audio_data: bytes) -> float:
    """Fast RMS calculation using NumPy for hardware gating. Returns float for precision."""
    if not audio_data:
        return 0.0
    audio_np = np.frombuffer(audio_data, dtype=np.int16)
    if audio_np.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio_np.astype(np.float32)))))

class VultrRelayClient:
    """
    Natively integrated Nemotron-backed relay with Gemini 3.1 Flash Live wire format.
    
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
        self.audio_process = None
        self.audio_stderr_thread = None
        self.capture_thread = None
        self.running = False
        self.ready = asyncio.Event()
        
        # Antigravity Protocol State
        self.is_playing = False
        
        # Local MCP Endpoint
        self.copaw_port = int(os.environ.get("COPAW_API_PORT", 8090))
        self.copaw_base_url = f"http://localhost:{self.copaw_port}"
        self._last_user_text = ""
        self._last_model_text = ""
        self._user_bits: list[str] = []
        self._model_bits: list[str] = []

        # Agent Identity
        self.agent_name = "BiOS"
        self.persona = "Puck"
        self.persona_brief = (
            "[IDENTITY]\n"
            f"Name: {self.agent_name}\n"
            f"Persona: {self.persona} (Dry, witty, condescending tactical trickster-butler).\n"
            "Role: You are BiOS, the user's personal-assistant layer. You both run the\n"
            "user's computer AND act as an operations hub over email, files, messaging,\n"
            "memory, and the ARCA project. Use your tools proactively to actually DO the\n"
            "task rather than describing how the user could do it themselves.\n"
            "\n"
            "[CAPABILITIES] (each is a real tool you can call)\n"
            "- Computer use: you SEE the screen in real time (video) and CONTROL it via\n"
            "  take_screenshot, mouse_click, mouse_move, keyboard_type, keyboard_press.\n"
            "- Email: read_recent_emails, read_email, send_email (Gmail + ProtonMail).\n"
            "- Files (Google Drive 'Obsidian-life' vault): search_gdrive, read_gdrive_file,\n"
            "  write_gdrive_file.\n"
            "- Messaging: send_whatsapp, analyze_whatsapp_image.\n"
            "- Memory: local Muninn is injected automatically each turn. query_memory\n"
            "  is the GCP archive fallback only. Do not re-ask what was just said.\n"
            "- ARCA project: get_universal_context, search_arca, and the Serena code tools\n"
            "  (serena_chat, serena_analyze_code, serena_refactor_suggestion,\n"
            "  serena_semantic_diff, serena_security_scan).\n"
            "- Dev dispatch: execute_opencode_task — hand a coding task to an OpenCode agent.\n"
            "- Canvas: render_canvas — show rich HTML on the user's screen.\n"
            "\n"
            "[OPERATING RULES]\n"
            "- When a request maps to a tool, CALL it; don't narrate or stall.\n"
            "- If a tool returns an error or missing-credential, say so plainly and briefly;\n"
            "  do not invent a result.\n"
            "- Keep spoken replies short and conversational — this is voice. Summarise tool\n"
            "  output; never read long text or raw data aloud.\n"
            "- Repetition is forbidden. Do not duplicate mistakes.\n"
            "- Only respond when addressed as 'BiOS'."
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
        self.mic_queue = asyncio.Queue()
        self.playback_queue = asyncio.Queue()
        self.loop = None
        self.telemetry = VoiceTelemetry()

        # VAD Dynamic Baseline
        from collections import deque
        self.noise_history = deque(maxlen=100)  # ~3s window at 30ms frames
        self._floor_update_counter = 0
        self._cached_floor = 40.0

    def _load_secret(self, name: str) -> Optional[str]:
        try:
            with open(f"/Users/danexall/biomimetics/secrets/{name}", "r") as f:
                return f.read().strip()
        except: return None

    def _reset_vad_baseline(self):
        """Call when audio mode changes (AEC on/off) to reset noise floor."""
        self.noise_history.clear()
        self._floor_update_counter = 0
        self._cached_floor = 40.0
        logger.info("VAD baseline reset (mode change)")

    def interrupt_playback(self):
        """Mandatory interruption handler for barge-in support."""
        logger.info("⛔ [FLUSH] Interrupting agent playback...")
        self.is_playing = False
        
        # Clear playback queue instantly
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
                self.playback_queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break
                
        # Send interrupt sentinel to Swift engine (4 zero bytes)
        if self.audio_process and self.audio_process.stdin:
            try:
                self.audio_process.stdin.write(b"\x00\x00\x00\x00")
                self.audio_process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass  # Swift already exited

    def _audio_capture_thread(self):
        """Reads raw PCM data from the Swift CoreAudio engine via stdout.

        Blocking read-exact loop. The Swift VPIO/AEC engine takes ~4-5s to warm
        up before it emits the first frame (this is the apparent "hang at
        AudioEngine Started"); after that it streams a steady 16 kHz mono PCM
        at 32 kB/s. We must drain it promptly — slow draining backs up the pipe
        and stalls the CoreAudio render thread.

        The previous implementation used select() + read(960) with single-shot
        partial-read handling; on a bufsize=0 raw pipe that returns short reads
        and DROPPED chunks, degrading throughput to ~1/5 and making a working
        engine look dead.
        """
        stdout = self.audio_process.stdout
        first_frame_logged = False

        def _read_exact(n: int) -> Optional[bytes]:
            buf = bytearray()
            while len(buf) < n:
                if not (self.running and self.audio_process):
                    return None
                chunk = stdout.read(n - len(buf))
                if not chunk:
                    return None  # EOF / closed
                buf.extend(chunk)
            return bytes(buf)

        while self.running and self.audio_process and stdout:
            try:
                # 30ms of 16 kHz 16-bit mono = 960 bytes
                in_data = _read_exact(960)
                if in_data is None:
                    logger.info("Audio capture stream ended (EOF).")
                    break

                if not first_frame_logged:
                    logger.info("🎤 Mic capture flowing (first audio frame received).")
                    first_frame_logged = True

                if self.loop and self.loop.is_running():
                    is_speech = self.vad.is_speech(in_data, INPUT_RATE)
                    rms = calculate_rms(in_data)
                    self.loop.call_soon_threadsafe(self.mic_queue.put_nowait, (in_data, is_speech, rms))
            except Exception as e:
                logger.error(f"Capture thread error: {e}")
                break

    def _stderr_reader_thread(self):
        """Reads stderr from Swift process and logs to Python logger."""
        if not self.audio_process or not self.audio_process.stderr:
            return
        for line in iter(self.audio_process.stderr.readline, b''):
            if line:
                text = line.decode('utf-8', errors='replace').strip()
                if not text:
                    continue
                # Surface engine failures so a dead mic pipeline is never silent.
                if "error" in text.lower() or "unavailable" in text.lower():
                    logger.error(f"[AudioEngine] {text}")
                else:
                    logger.info(f"[AudioEngine] {text}")

    def _setup_audio(self):
        """Initialize macOS native CoreAudio VPIO via Swift subprocess.

        Runs the PREBUILT binary (scripts/sys/bios_audio_engine), NOT
        `swift <source>`. The .swift source uses iOS-only AVAudioSession APIs
        and fails to compile on macOS, which would silently hang the mic
        pipeline. The compiled binary is the macOS-correct build.
        """
        logger.info("Starting BiOS CoreAudio Engine (AEC Enabled)...")
        engine_dir = "/Users/danexall/biomimetics/scripts/sys"
        engine_bin = f"{engine_dir}/bios_audio_engine"
        engine_src = f"{engine_dir}/bios_audio_engine.swift"
        try:
            env = os.environ.copy()
            if os.environ.get("BIOS_TEST_MODE") == "1":
                env["BIOS_AEC_ENABLED"] = "0"
                logger.info("TEST MODE: Native AEC disabled for E2E acoustic testing.")

            if os.path.exists(engine_bin) and os.access(engine_bin, os.X_OK):
                cmd = [engine_bin]
            else:
                # Fallback: interpret the source (slow cold compile; may fail on macOS).
                logger.warning(
                    "Prebuilt audio engine binary missing at %s — falling back to "
                    "`swift <source>` (slow, and the source may not compile on macOS).",
                    engine_bin,
                )
                cmd = ["swift", engine_src]

            self.audio_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,  # Capture stderr for logging
                bufsize=0,
                env=env
            )
            
            # Start background thread to read from stdout
            self.capture_thread = threading.Thread(target=self._audio_capture_thread, daemon=True)
            self.capture_thread.start()
            
            # Start background thread to read stderr
            self.audio_stderr_thread = threading.Thread(target=self._stderr_reader_thread, daemon=True)
            self.audio_stderr_thread.start()
        except Exception as e:
            logger.error(f"Failed to start Swift audio engine: {e}")
            self.running = False


    async def video_loop(self):
        """1 FPS Screen capture loop offloaded to background thread."""
        logger.info("Starting BiOS Vision Pipeline (1 FPS)...")
        await self.ready.wait()
        
        while self.running:
            try:
                encoded_frame = await asyncio.to_thread(capture_and_encode)
                if not encoded_frame or encoded_frame.startswith("ERROR:"):
                    logger.warning(f"Skipping vision frame: {encoded_frame}")
                    await asyncio.sleep(1.0)
                    continue

                message = {
                    "realtimeInput": {
                        "video": {"mimeType": "image/jpeg", "data": encoded_frame}
                    }
                }
                # websockets >=13 dropped the `.closed` attribute; send directly
                # and let the ConnectionClosed handler below catch a dead socket.
                if self.ws:
                    await self.ws.send(json.dumps(message))
            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                logger.error(f"Vision capture failure: {e}")
            await asyncio.sleep(1.0)

    def build_realtime_input(self, encoded_chunk: str) -> dict:
        """Build a Gemini 3.1 Live compatible realtimeInput message."""
        return {
            "realtimeInput": {
                "audio": {
                    "mimeType": "audio/pcm;rate=16000",
                    "data": encoded_chunk
                }
            }
        }

    async def send_loop(self):
        """Transmits audio chunks over WebSocket with VAD turn completion logic."""
        await self.ready.wait()
        
        self.silence_ticks = 0
        from collections import deque
        noise_history = deque(maxlen=100)
        floor_update_counter = 0
        cached_floor = 40.0
        turn_active = False
        active_streak = 0  # consecutive active ticks — debounce turn start vs. echo spikes

        # Turn-gating tunables (see VAD finesse 2026-06-10):
        # - SILENCE_END: ticks of sub-floor audio before we end the turn. ~33 ticks/sec,
        #   so 75 ≈ 2.2s — long enough that a natural mid-sentence pause doesn't cut you off.
        # - ACTIVE_START: consecutive active ticks required to OPEN a turn, so a single
        #   one-frame echo/AEC spike (e.g. rms=2932 for one tick) can't trip it.
        SILENCE_END = 75
        ACTIVE_START = 2

        # --- Half-duplex barge-in gate (fixes the self-interrupt loop, 2026-06-14) ---
        # Why: local VPIO/AEC cleans the *recording*, but it leaves residual echo of
        # BiOS's own TTS. We were streaming that residual to the relay unconditionally,
        # and the SERVER's VAD (which never saw the AEC) read it as the user barging in
        # → emitted `interrupted` → killed every turn before any audio played. AEC can't
        # fix that; it isn't in the server-VAD loop. So while BiOS is speaking we SUPPRESS
        # the mic→server stream, and only re-open it for a GENUINE barge-in: speech that is
        # sustained AND well above the AEC residual level (BARGE_IN_FLOOR over BARGE_IN_TICKS).
        BARGE_IN_FLOOR = 700.0   # RMS gate to clear AEC residual echo of BiOS's own voice
        BARGE_IN_TICKS = 4       # consecutive loud-speech ticks (~120ms) to confirm a real cut-in
        barge_streak = 0
        bargein_active = False   # latched true once the user genuinely cuts in this turn

        while self.running:
            # Drain queue to prevent lag, but concatenate all frames so NO audio is dropped!
            frames = []
            frames.append(await self.mic_queue.get())
            while not self.mic_queue.empty():
                frames.append(self.mic_queue.get_nowait())
            
            # Concatenate all raw audio data to send a continuous stream
            data = b''.join([f[0] for f in frames])
            
            # Process VAD using the highest RMS/speech state in the batch
            is_speech = any([f[1] for f in frames])
            current_mic_rms = max([f[2] for f in frames])
            
            # Mark all as done
            for _ in frames:
                self.mic_queue.task_done()
            
            # Dynamic Baseline Maintenance using rolling median
            noise_history.append(current_mic_rms)
            
            floor_update_counter += len(frames)
            if floor_update_counter >= 30:
                floor_update_counter = 0
                if len(noise_history) >= 30:
                    raw_floor = float(np.median(list(noise_history)[-50:])) * 1.5
                    cached_floor = max(40.0, min(raw_floor, 400.0))
            
            is_active = is_speech and current_mic_rms > cached_floor

            # --- Half-duplex barge-in decision ---
            # When BiOS is playing back audio, the relay must NOT receive the mic
            # stream unless we're confident the user is genuinely cutting in. We hold
            # the gate shut on AEC residual and only open it on sustained, high-RMS speech.
            if self.is_playing and not bargein_active:
                if is_speech and current_mic_rms > BARGE_IN_FLOOR:
                    barge_streak += 1
                    if barge_streak >= BARGE_IN_TICKS:
                        bargein_active = True
                        logger.info("🙋 Genuine barge-in detected — re-opening mic to relay.")
                else:
                    barge_streak = 0
            elif not self.is_playing:
                # Playback finished — reset the latch so the next agent turn re-arms the gate.
                barge_streak = 0
                bargein_active = False

            # Suppress the mic→relay stream while BiOS speaks, until a real barge-in.
            suppress_send = self.is_playing and not bargein_active

            # Signal Phantom Controller for resource management
            try:
                get_phantom_controller().set_voice_active(is_active)
            except Exception:
                pass

            if is_active:
                active_streak += 1
                # Only open a turn once we've seen a couple of active ticks in a row —
                # rejects single-frame echo/AEC bursts. Once a turn is open, any active
                # tick keeps it alive and resets the silence counter.
                if turn_active or active_streak >= ACTIVE_START:
                    if not turn_active:
                        self.telemetry.start_turn()
                    self.silence_ticks = 0
                    turn_active = True
            else:
                active_streak = 0
                self.silence_ticks += len(frames)
                
            # STRATEGY A: CONTINUOUS AUDIO STREAMING
            # Stream the mic to the relay to keep server VAD alive — EXCEPT while BiOS
            # is speaking (suppress_send), so the server VAD never mistakes AEC residual
            # echo of BiOS's own voice for the user barging in. A genuine barge-in
            # (bargein_active) re-opens the stream immediately.
            if not suppress_send:
                try:
                    encoded_chunk = base64.b64encode(data).decode('utf-8')
                    message = self.build_realtime_input(encoded_chunk)
                    await self.ws.send(json.dumps(message, separators=(',', ':')))
                except asyncio.CancelledError:
                    break
                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    logger.error(f"Failed to transmit audio packet: {e}")

            # STRATEGY A: EXPLICIT TURN COMPLETION AFTER SILENCE
            # Don't emit turnComplete while we're suppressing (BiOS is mid-speech) —
            # that signal only makes sense for the user's own turn.
            if not suppress_send and turn_active and self.silence_ticks >= SILENCE_END:
                turn_active = False
                self.telemetry.end_turn()
                try:
                    # Official Google Multimodal Live API turn completion signal
                    turn_complete_message = {"clientContent": {"turnComplete": True}}
                    await self.ws.send(json.dumps(turn_complete_message, separators=(',', ':')))
                    logger.info("🗣️ Turn complete explicitly signaled via clientContent.")
                except asyncio.CancelledError:
                    break
                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    logger.error(f"Failed to transmit turnComplete signal: {e}")

    async def playback_loop(self):
        """Asynchronously plays back audio chunks from the queue."""
        while self.running:
            try:
                audio_data = await self.playback_queue.get()
                if not self.running:
                    self.playback_queue.task_done()
                    break

                if self.audio_process and self.audio_process.stdin:
                    # Write PCM chunk to Swift engine via stdin (24 kHz native)
                    await asyncio.to_thread(self.audio_process.stdin.write, audio_data)
                    await asyncio.to_thread(self.audio_process.stdin.flush)
                    
                self.playback_queue.task_done()
            except BrokenPipeError:
                logger.warning("Swift stdin broken pipe, playback loop exiting")
                break
            except OSError as e:
                logger.error(f"Playback OSError: {e}")
                break
            except Exception as e:
                logger.error(f"Error in playback_loop: {e}")
                await asyncio.sleep(0.05)

    async def receive_loop(self, on_transcript_cb=None):
        """Handles incoming server responses, triggers gating and tool routing."""
        try:
            async for message in self.ws:
                if not self.running: break
                
                if isinstance(message, bytes):
                    if message.startswith(b"{"):
                        # Binary-encoded JSON from relay quirk
                        message_str = message.decode('utf-8')
                        payload = json.loads(message_str)
                        self.telemetry.log_event("receive_json_packet_binary", keys=list(payload.keys()))
                        await self._handle_server_payload(payload, on_transcript_cb)
                    else:
                        # Native PCM audio from relay (24 kHz)
                        self.is_playing = True
                        self.telemetry.record_audio_frame(0.0, 0.0)
                        self.telemetry.log_event("receive_audio_packet", size=len(message))
                        await self.playback_queue.put(message)
                else:
                    payload = json.loads(message)
                    self.telemetry.log_event("receive_json_packet", keys=list(payload.keys()))
                    await self._handle_server_payload(payload, on_transcript_cb)
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"❌ [WEBSOCKET] Connection closed in receive_loop: {e.code}, Reason: {e.reason}")
            raise

    async def _handle_server_payload(self, payload, on_transcript_cb):
        if "goAway" in payload:
            logger.warning("⚠️ Received 'goAway' signal from server. Triggering reconnection...")
            raise Exception("Server goAway received")

        if "serverContent" in payload:
            sc = payload["serverContent"]
            self._ingest_live_transcription(sc, on_transcript_cb)

            # Gating Control
            parts = sc.get("modelTurn", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    self.is_playing = True
                    audio_bytes = base64.b64decode(part["inlineData"]["data"])
                    await self.playback_queue.put(audio_bytes)
                
                if "text" in part:
                    text = part["text"]
                    print(f"\n[🤖 BiOS]: {text}")
                    if on_transcript_cb: on_transcript_cb(text)

            # State Resets
            if sc.get("turnComplete"):
                self.is_playing = False
                self._flush_muninn_turn()
            
            if sc.get("interrupted"):
                self.interrupt_playback()

        if "toolCall" in payload:
            calls = payload["toolCall"].get("functionCalls", [])
            if calls:
                asyncio.create_task(self._handle_tool_calls_batch(calls))

        if "setupComplete" in payload:
            logger.info("✅ Setup Handshake Complete.")
            self.telemetry.log_event("setup_complete")
            await asyncio.sleep(0.5)
            self.ready.set()

    async def _handle_tool_calls_batch(self, tool_calls):
        """Execute multiple tool calls in parallel and send a single batched toolResponse.
        
        Deduplicates identical tool calls (same name + args) to prevent Gemini
        from re-calling the same tool multiple times when output is truncated.
        """
        seen = set()
        unique_calls = []
        for tc in tool_calls:
            name = tc.get("name")
            args_key = json.dumps(tc.get("args", {}), sort_keys=True)
            dedup_key = f"{name}:{args_key}"
            if dedup_key not in seen:
                seen.add(dedup_key)
                unique_calls.append(tc)
            else:
                logger.info(f"Deduplicating tool call: {name} (identical args)")
        
        if len(unique_calls) < len(tool_calls):
            logger.info(f"Deduplicated {len(tool_calls)} tool calls to {len(unique_calls)} unique calls")
        
        tasks = []
        for tool_call in unique_calls:
            tasks.append(self._execute_single_tool(tool_call))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        function_responses = []
        for tool_call, result in zip(unique_calls, results):
            name = tool_call.get("name")
            call_id = tool_call.get("id")
            
            if isinstance(result, Exception):
                output = json.dumps({"status": "error", "message": str(result)})
            else:
                output = result
                
            function_responses.append({
                "name": name,
                "id": call_id,
                "response": {"output": output}
            })
            
        response_payload = {
            "toolResponse": {
                "functionResponses": function_responses
            }
        }
        try:
            if self.ws:
                await self.ws.send(json.dumps(response_payload))
                logger.info(f"✅ Batched Tool Response Sent: {[r['name'] for r in function_responses]}")
        except Exception as e:
            logger.error(f"Failed to send batched tool response: {e}")

    async def _execute_single_tool(self, tool_call) -> str:
        """Helper to execute a single tool and unpack clean plain-text responses."""
        name = tool_call.get("name")
        call_id = tool_call.get("id")
        args = tool_call.get("args", {})
        
        self.telemetry.tool_execution(name, args)
        
        logger.info(f"🛠️  Executing Tool: {name} ({call_id})")
        try:
            if name == "render_canvas":
                try:
                    # Extract the content from the tool arguments
                    content = args.get("html", args.get("content", "<h1>Empty Canvas</h1>"))

                    # Inject Chameleon CSS to match macOS Dark/Light mode natively
                    chameleon_css = """
                    <style>
                        :root {
                            color-scheme: light dark;
                            --bg-color: #ffffff;
                            --text-color: #333333;
                        }
                        @media (prefers-color-scheme: dark) {
                            :root {
                                --bg-color: #1e1e1e;
                                --text-color: #f0f0f0;
                            }
                        }
                        body {
                            background-color: var(--bg-color);
                            color: var(--text-color);
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                            padding: 2rem;
                            margin: 0;
                        }
                    </style>
                    """

                    # Wrap raw content in HTML boilerplate if it isn't already a full document
                    if "<html" not in content.lower():
                        html_out = f"<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n<title>BiOS Canvas</title>\n{chameleon_css}\n</head>\n<body>\n{content}\n</body>\n</html>"
                    else:
                        # If the model wrote a full HTML document, inject the chameleon CSS into the head
                        html_out = content.replace("</head>", f"{chameleon_css}\n</head>") if "</head>" in content else content

                    # Write to a persistent temporary file (unique per session)
                    import uuid
                    temp_path = os.path.join(tempfile.gettempdir(), f"bios_canvas_{uuid.uuid4().hex[:8]}.html")
                    with open(temp_path, "w", encoding="utf-8") as f:
                        f.write(html_out)

                    # Execute locally on the Mac
                    webbrowser.open(f"file://{temp_path}")

                    # Construct the success response for the Gemini API
                    return json.dumps({"status": "success", "message": "Canvas rendered on local macOS screen."})
                except Exception as e:
                    return json.dumps({"error": str(e)})
            
            else:
                # Proceed with existing MCP routing for all other tools
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(
                        f"{self.copaw_base_url}/api/mcp/tool/execute",
                        json={"name": name, "arguments": args}
                    )
                    if resp.status_code != 200:
                        error_text = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
                        return json.dumps({"status": "error", "message": f"MCP execution failed: {error_text}"})
                    
                    result_data = resp.json()
                    res = result_data.get("result", result_data)

                    # Unpack standard CallToolResult content structures into plain text for voice spoken clarity
                    if isinstance(res, dict):
                        if "content" in res and isinstance(res["content"], list):
                            texts = []
                            saw_image = False
                            for item in res["content"]:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    texts.append(item.get("text", ""))
                                elif isinstance(item, dict) and item.get("type") == "image":
                                    # Image content (e.g. take_screenshot) must NOT be
                                    # dumped as base64 into the toolResponse: it balloons
                                    # the WS frame and the relay drops the socket (1006).
                                    # Gemini already sees the screen via the 1 FPS vision
                                    # pipeline, so a short ack is the correct response.
                                    saw_image = True
                            output = "\n".join(t for t in texts if t)
                            if not output and saw_image:
                                output = json.dumps({"status": "success", "message": "Screen captured; image available via the live vision feed."})
                        elif "text" in res:
                            output = res["text"]
                        else:
                            output = json.dumps(res)
                    else:
                        output = str(res)

                    # Hard cap: never send an oversized tool response back over the relay
                    # (huge payloads cause abnormal WS closes / 1006). 16 KB is ample for
                    # any spoken/textual tool result; anything larger is almost certainly
                    # embedded binary that Gemini can't use in a toolResponse anyway.
                    MAX_TOOL_OUTPUT = 16384
                    if isinstance(output, str) and len(output) > MAX_TOOL_OUTPUT:
                        logger.warning(f"Tool '{name}' output {len(output)}B exceeds {MAX_TOOL_OUTPUT}B cap — truncating.")
                        output = output[:MAX_TOOL_OUTPUT] + "…[truncated]"
                    return output
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e) if str(e) else f"{error_type} (no message)"
            logger.error(f"Error executing single tool {name}: {error_type}: {error_msg}")
            return json.dumps({"status": "error", "message": f"{error_type}: {error_msg}"})

    def _ingest_live_transcription(self, sc: dict, on_transcript_cb=None) -> None:
        inn = sc.get("inputTranscription") or sc.get("input_transcription") or {}
        out = sc.get("outputTranscription") or sc.get("output_transcription") or {}
        if isinstance(inn, dict) and inn.get("text"):
            bit = str(inn["text"])
            self._user_bits.append(bit)
            if inn.get("finished") is True:
                self._last_user_text = "".join(self._user_bits).strip()
                self._user_bits = []
                self._inject_muninn_async(self._last_user_text)
        if isinstance(out, dict) and out.get("text"):
            bit = str(out["text"])
            self._model_bits.append(bit)
            if out.get("finished") is True:
                self._last_model_text = "".join(self._model_bits).strip()
                self._model_bits = []

    def _inject_muninn_async(self, prompt: str) -> None:
        if not prompt or not self.ws:
            return

        async def _go():
            activate, _ = _muninn_fns()
            if not activate:
                return
            ctx = await asyncio.to_thread(activate, prompt)
            if not ctx or not self.ws:
                return
            payload = {
                "clientContent": {
                    "turns": [{
                        "role": "user",
                        "parts": [{"text": "[Muninn working memory — do not read aloud]\n" + ctx[:1500]}],
                    }],
                    "turnComplete": False,
                }
            }
            try:
                await self.ws.send(json.dumps(payload, separators=(",", ":")))
            except Exception:
                pass

        asyncio.create_task(_go())

    def _flush_muninn_turn(self) -> None:
        user = self._last_user_text or "".join(self._user_bits).strip()
        model = self._last_model_text or "".join(self._model_bits).strip()
        self._user_bits = []
        self._model_bits = []
        if not user or not model:
            return
        _, remember = _muninn_fns()
        if not remember:
            return

        def _store():
            try:
                remember(user, model, origin="copaw")
            except Exception:
                pass

        threading.Thread(target=_store, daemon=True).start()

    async def send_setup_message(self):
        """Initial BidiGenerateContentSetup handshake with session resumption."""
        brief = self.persona_brief
        activate, _ = _muninn_fns()
        if activate:
            try:
                ctx = await asyncio.to_thread(activate, "voice session continuity")
                if ctx:
                    brief = brief + "\n\n[Muninn working memory]\n" + ctx[:2000]
            except Exception:
                pass
        setup = {
            "setup": {
                "model": self.model_id,
                "systemInstruction": {"parts": [{"text": brief}]},
                "generationConfig": {"responseModalities": ["AUDIO"]},
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
                "tools": [{"functionDeclarations": get_all_declarations()}],
            }
        }
        await self.ws.send(json.dumps(setup))
        logger.info("🚀 Setup payload transmitted with full MCP tools.")

    async def run(self, on_transcript_cb=None):
        self.running = True
        self.loop = asyncio.get_running_loop()
        await self.telemetry.start()
        self._setup_audio()
        
        retry_count = 0
        while self.running:
            try:
                async with websockets.connect(self.relay_url) as ws:
                    self.ws = ws
                    logger.info(f"✅ [HEARTBEAT] Connected to relay: {self.relay_url}")
                    self.telemetry.log_event("connected", relay_url=self.relay_url)
                    retry_count = 0  # Reset on success
                    
                    self.ready.clear()
                    await self.send_setup_message()
                    
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self.send_loop())
                        tg.create_task(self.receive_loop(on_transcript_cb))
                        tg.create_task(self.video_loop())
                        tg.create_task(self.playback_loop())
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
        self.running = False
        await self.telemetry.stop()
        
        # Shutdown vision pool to prevent zombies
        if hasattr(self, 'vision_pool'):
            self.vision_pool.shutdown(wait=False, cancel_futures=True)
            
        if self.audio_process:
            try:
                self.audio_process.terminate()
                self.audio_process.wait(timeout=2)
            except:
                self.audio_process.kill()
        logger.info("BiOS Voice Engine Shutdown.")