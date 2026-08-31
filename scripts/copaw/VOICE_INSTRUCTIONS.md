# CoPaw Voice Channel: BiOS

The CoPaw Voice Channel provides a real-time, multimodal interface to the BiOS ecosystem using Google's Gemini 3.1 Live API. The voice persona is **BiOS**, utilizing the "Puck" voice model.

## Architecture

The system uses a **Vultr Relay** to bridge local audio streams to the Gemini Live WebSocket API.

1.  **Local Client**: `scripts/copaw/src/copaw/app/channels/voice/vultr_relay_client.py`
2.  **Audio**: PyAudio for mic capture and speaker playback.
3.  **VAD**: WebRTCVAD for local voice activity detection to minimize bandwidth.
4.  **Relay**: A hosted WebSocket relay on Vultr (e.g., `ws://100.86.112.119:8765/ws/live`).
5.  **Tools**: Multi-modal tool calls are routed back to the local CoPaw API on port 8090.

## Performance Baseline (v2 Architecture)
- **Audio Playback:** A thread-safe, non-blocking bytearray buffer guarantees exact byte-alignment for 16-bit PCM playback. This completely eliminates fast-playback distortion.
- **Barge-in / Interrupts:** Fully supported and synchronous. Interruptions instantly clear the local playback buffer and broadcast a `turnComplete: true` signal to the Gemini WebSocket to accurately halt server-side generation.
- **Vision Pipeline:** 1-FPS screen capture and Base64 JPEG encoding is explicitly decoupled from the Python GIL using a `concurrent.futures.ProcessPoolExecutor`. This ensures the intensive 30ms hardware callbacks of PyAudio are never starved or dropped.

## Configuration

### 1. Environment Variables
The following environment variables should be set (usually handled by `bios-voice.sh` or the environment loader):

- `COPAW_ENABLED_CHANNELS=voice`
- `COPAW_API_PORT=8090` (The port CoPaw runs on for tool execution)
- `CREDENTIALS_API_KEY`: API key for the local credentials server (port 8089).

### 2. config.json
Ensure the `voice` channel is enabled in `config_copaw/config.json`:

```json
"voice": {
  "enabled": true,
  "relay_url": "ws://100.86.112.119:8765/ws/live",
  "model": "models/gemini-3.1-flash-live-preview"
}
```

## Operation

### Launching Puck
Use the dedicated activation script:
```bash
./scripts/sys/bios-voice.sh
```

### Controls
- **PTT (Push-To-Talk)**: Hold `SPACE` to force transmission regardless of VAD.
- **Mute**: Press `m` to toggle the hardware-level microphone mute.
- **Barge-in**: Simply speak while Puck is talking. The system uses a `playback_queue` and VAD to automatically interrupt the agent.

## Persona: BiOS
BiOS is configured with a specific persona brief:
- **Identity**: Attentive, polite, but curt. Witty and sarcastic, but amazingly effective when tasked.
- **Directive**: Output no excess sentences. Avoid repetition. Only respond when addressed as "BiOS".

## Troubleshooting

- **Loading Failures**: Check logs for `FATAL: failed to load built-in channel "voice"`. This usually indicates missing dependencies (e.g., `pyaudio`, `webrtcvad`).
- **Audio Issues**: Ensure no other process is holding the microphone. `bios-voice.sh` attempts to clear processes on port 8090.
- **Tool Failures**: Verify the main CoPaw application is running and accessible at `http://localhost:8090`.
- **Latency**: If latency is high, check the connection to the Vultr relay.
