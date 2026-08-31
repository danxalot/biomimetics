# Pythia Server + Geometry ONNX Interpreter Integration

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARCA System Integration                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐         ┌─────────────────┐               │
│  │   ui_term       │         │   gateway       │               │
│  │   (port 8084)   │◄────────┤   (port 8080)   │               │
│  │                 │         │                 │               │
│  │  LangGraph      │         │  Routes to:     │               │
│  │  Agent          │         │  - Pythia       │               │
│  │  + Pythia       │         │  - Gemini       │               │
│  │  Integration    │         │  - Qwen         │               │
│  └────────┬────────┘         └────────┬────────┘               │
│           │                           │                          │
│           │ call /interpret/predict   │                          │
│           ▼                           │                          │
│  ┌─────────────────┐                  │                          │
│  │ geometry_onnx_  │                  │                          │
│  │ interpreter     │                  │                          │
│  │ (port 8096)     │                  │                          │
│  │                 │                  │                          │
│  │ ONNX Model      │                  │                          │
│  │ + Qwen3VL Call  │                  │                          │
│  └────────┬────────┘                  │                          │
│           │ call /v1/chat/completions │                          │
│           ▼                           │                          │
│  ┌─────────────────┐                  │                          │
│  │  pythia_server  │                  │                          │
│  │  (port 11435)   │                  │                          │
│  │                 │                  │                          │
│  │  llama.cpp      │                  │                          │
│  │  + Vulkan 0     │                  │                          │
│  │  Qwen3VL-2B     │                  │                          │
│  └─────────────────┘                  │                          │
│           ▲                           │                          │
│           │ model weights             │                          │
│           │ (ONNX + INT8)             │                          │
│  ┌────────┴────────┐                  │                          │
│  │   OCI Instance  │                  │                          │
│  │   (100.70.0.13) │                  │                          │
│  └─────────────────┘                  │                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Services Summary

### 1. Pythia Server (llama.cpp + Vulkan)
- **Location**: `/Users/danexall/Documents/VS Code Projects/ARCA/services/pythia_server/`
- **Port**: 11435
- **Model**: Qwen3VL-2B-Instruct-Q8_0.gguf
- **MMProj**: Qwen3VL-2B-Instruct-MMProj.gguf
- **Device**: Vulkan 0 (AMD Radeon Pro 5500M)
- **Script**: `start_server.sh`

### 2. Geometry ONNX Interpreter
- **Location**: `/Users/danexall/Documents/VS Code Projects/ARCA/services/geometry_onnx_interpreter/`
- **Port**: 8096
- **Model**: ONNX INT8 quantized (pythia_c2h_5000_int8.onnx)
- **Endpoints**:
  - `POST /interpret/predict` - Full pipeline (ONNX + Qwen3VL)
  - `POST /interpret/onnx_only` - ONNX model only
  - `GET /interpret/health` - Health check

### 3. LangGraph Agent (ui_term)
- **Location**: `/Users/danexall/Documents/VS Code Projects/ARCA/services/ui_term/`
- **Port**: 8084
- **Integration**: `pythia_integration.py`
- **New Node**: `_geometric_analysis_node` in workflow

## Integration Points

### A. Pythia Server → Geometry ONNX Interpreter
The geometry_onnx_interpreter calls the pythia_server for Qwen3VL interpretation:
```python
# In geometry_onnx_interpreter.py
PYTHIA_SERVER_URL = os.getenv("PYTHIA_SERVER_URL", "http://localhost:11435")
# Calls: POST {PYTHIA_SERVER_URL}/v1/chat/completions
```

### B. LangGraph Agent → Geometry ONNX Interpreter
The langgraph_agent calls geometry_onnx_interpreter for geometric analysis:
```python
# In pythia_integration.py
result = await client.interpret_geometric_data(solar_system_data)
# Calls: POST http://localhost:8096/interpret/predict
```

### C. Gateway → Pythia Server
The gateway routes requests to the local pythia_server:
```python
# In gateway/main.py
NATIVE_SERVER_URL = f"http://{os.environ.get('LOCAL_LLM_HOST', 'host.docker.internal')}:11435/v1"
```

## Environment Variables

### For pythia_server/start_server.sh
```bash
# Set in shell before running:
export DYLD_LIBRARY_PATH="$(pwd):$DYLD_LIBRARY_PATH"
```

### For geometry_onnx_interpreter
```bash
# Set in .env or shell:
PYTHIA_SERVER_URL=http://localhost:11435
ONNX_MODEL_PATH=/path/to/pythia_c2h_5000_int8.onnx
PORT=8096
```

### For ui_term (LangGraph agent)
```bash
# Set in .env or shell:
PYTHIA_SERVER_URL=http://localhost:11435
ONNX_INTERPRETER_URL=http://localhost:8096
```

## Startup Sequence

1. **Start Pythia Server**:
   ```bash
   cd /Users/danexall/Documents/VS\ Code\ Projects/ARCA/services/pythia_server
   ./start_server.sh
   ```

2. **Start Geometry ONNX Interpreter**:
   ```bash
   cd /Users/danexall/Documents/VS\ Code\ Projects/ARCA/services/geometry_onnx_interpreter
   python geometry_onnx_interpreter.py
   ```

3. **Start ui_term (LangGraph Agent)**:
   ```bash
   cd /Users/danexall/Documents/VS\ Code\ Projects/ARCA/services/ui_term
   python main.py
   # Or via Docker
   docker-compose -f docker-compose.yml up
   ```

## API Flow Example

1. User sends message via ui_term (port 8084)
2. LangGraph agent processes message
3. If geometric content detected, calls `_geometric_analysis_node`
4. Node calls `pythia_geometric_analysis()` in pythia_integration.py
5. Integration calls geometry_onnx_interpreter (port 8096)
6. ONNX interpreter runs model inference
7. ONNX interpreter calls pythia_server (port 11435) for Qwen3VL interpretation
8. Response flows back through the chain

## Testing Commands

```bash
# Test Pythia Server
curl http://localhost:11435/health

# Test Geometry ONNX Interpreter
curl http://localhost:8096/interpret/health

# Test Pythia Server chat completion
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen3VL-2B-Instruct-Q8_0.gguf", "messages": [{"role": "user", "content": "Hello"}]}'

# Test ONNX interpreter
curl -X POST http://localhost:8096/interpret/predict \
  -H "Content-Type: application/json" \
  -d '{"system_id": "test", "gravity_well": {"concept": "test", "mass": 5}, "objects": [], "trajectory": [0,0,0]}'
```

## Files Created/Modified

1. **pythia_integration.py** (new) - LangGraph integration module
2. **langgraph_agent.py** (modified) - Added geometric_analysis_node
3. **geometry_onnx_interpreter.py** (modified) - Added pythia_server_url support
4. **start_server.sh** (new) - Pythia server startup script
5. **llama_cpp_build/** (new) - Exposed llama.cpp build directory

## Notes

- The pythia_server runs on Vulkan 0 (AMD Radeon Pro 5500M)
- ONNX model is INT8 quantized for performance
- Integration is optional (graceful degradation if services unavailable)
- All services expose health check endpoints for monitoring
