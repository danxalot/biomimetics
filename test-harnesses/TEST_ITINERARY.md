# BiOS Test Itinerary & Environment Guide

This document defines the automated testing infrastructure for the BiOS ecosystem, enabling autonomous validation of system components without requiring human intervention.

## 1. Environment Configuration

### Virtual Environments
- **CoPaw Core**: `/Users/danexall/biomimetics/config_copaw/venv`
  - Purpose: Primary execution environment for the CoPaw gateway and relay client.
  - Activation: `source config_copaw/venv/bin/activate`

### Infrastructure Dependencies
- **Tailscale**: Required for connectivity to the Vultr Relay (`100.86.112.119`).
- **Port 8090**: CoPaw Gateway (Uvicorn).
- **Port 8089**: Credentials Server (Azure Key Vault Bridge).
- **Relay URL**: `ws://100.86.112.119:8765/ws/live`

### Environment Variables
- `COPAW_API_PORT`: 8090
- `CREDENTIALS_SERVER_URL`: http://127.0.0.1:8089
- `GCP_GATEWAY_URL`: https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator

## 2. Automated Test Harnesses (`./test-harnesses`)

### Voice & Audio
- **`test_echo_cancellation.py`**: Verifies that the cross-process playback state is correctly synchronized between the browser and terminal relay.
- **`test_mic_capture_loop.py`**: Simulates the microphone capture thread and verifies that audio gating/ducking logic functions correctly under mock conditions.
- **`verify_server_vad.py`**: Validates contiguous audio frame transmission to ensure Google's server-side AEC receives an unbroken waveform.
- **`probe_relay_connectivity.py`** (Upcoming): Diagnoses WebSocket handshake timeouts and network latency to the Vultr relay.

## 3. Self-Testing Methodology

To test without user intervention, always follow these rules:
1. **Mock Hardware**: Never rely on a physical microphone or speaker. Use `unittest.mock` to simulate PyAudio streams.
2. **Mock Backend**: For component tests, run a lightweight FastAPI instance in a background thread to simulate the CoPaw API.
3. **Continuous Streaming**: Always test with 30ms @ 16kHz (480 byte) chunks to match production behavior.
4. **Environment Isolation**: Always run tests within the `config_copaw/venv` to ensure all dependencies (`agentscope`, `pyaudio`, `webrtcvad`) are available.

## 4. Current Objectives
- Resolve "timed out during opening handshake" errors when connecting to the Vultr relay.
- Implement automated "Relay Probes" to verify network health before starting the full gateway.
