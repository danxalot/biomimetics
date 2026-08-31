# Observer Agent (Cognitive Reflex Layer)

The Observer Agent is a high-availability monitoring system designed to detect failures in the ARCA infrastructure and execute autonomous recovery ("Reflexes").

## Architecture
- **Runtime**: Docker Container (`observer_agent`)
- **Isolation**: Runs in its own PID namespace.
- **Intelligence**:
    - **Reflex**: Direct script execution for known failure patterns.
    - **Cognitive**: Uses Gemma-3 (via Google API) to deduce root causes for unknown failures.

## ⚠️ Critical Dependency: Native Host Bridge
The `local_ops` service (llama-server on port 11435) runs as a **Native macOS Binary** for performance (Vulkan/Metal). 

Because `observer_agent` lives in Docker (Linux), it **CANNOT** directly restart the macOS binary.

### The Solution: Host Bridge Routing
To restart `local_ops`, the agent sends a command to the `host_bridge`.

**IMPORTANT**: The `host_bridge` **MUST RUN NATIVELY** on the host machine.
- **Do NOT** run `host_bridge` via Docker Compose.
- **DO** run it via `./run_host_bridge_native.sh`.

### Recovery Flow
1. **Detection**: Observer detects `local_ops` is down (HTTP 500/timeout).
2. **Routing**: Observer POSTs to `http://host.docker.internal:8092/api/exec_script`.
3. **Execution**: The Native Host Bridge executes `scripts/restart_local_ops.sh` on the Mac host.
4. **Success**: The binary launches on the host OS.

## Development
- **Main Logic**: `main.py`
- **Toolbox**: `/app/shared_storage/observer_toolbox` (Mounted from host `shared_storage/observer_toolbox`)
