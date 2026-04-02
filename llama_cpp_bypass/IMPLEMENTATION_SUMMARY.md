# Unified Pythia Engine - Implementation Summary

## ✅ COMPLETED

### 1. Python 3.11 Virtual Environment
- Location: `/Users/danexall/Documents/VS Code Projects/ARCA/services/llama_cpp_bypass/venv`
- Status: Active and working

### 2. Unified Pythia Engine Server
- **File**: `unified_pythia_engine.py`
- **Port**: 11436
- **Features**:
  - FastAPI-based REST API
  - Global model loading with Vulkan acceleration
  - Translation bridge integration (10k HDC → 2048 dense)
  - Full latent bypass pipeline

### 3. API Endpoints

#### GET /health
Health check with model and translation bridge status

#### POST /v1/chat/completions
Standard chat completion using Qwen3-VL model

#### POST /v1/latent_inject
**Full Pipeline Workflow**:
1. Receives `user_id`, `original_message`, optional `incoming_vector`
2. If no vector provided:
   - Calls OCI Geometry Embedding service (port 8081)
   - Gets 2048d embedding
   - Truncates to 512d
   - Pushes to Dragonfly FIFO
   - Returns pending status (waits for Pythia 10k response)
3. If 10k HDC vector provided:
   - Runs through translation bridge (10k → 2048)
   - Truncates to 1536
   - Pads with Gaussian noise to 2048
   - Performs direct latent bypass via llama_batch
   - Returns generated response
   - Logs to memory API (port 8088)

#### POST /v1/geometry_embed
Direct call to OCI geometry embedding service

### 4. Vector Processing Pipeline

```
Input Prompt
    ↓
OCI Geometry Service (port 8081) → 2048d embedding
    ↓
Truncate to 512d
    ↓
Dragonfly FIFO (port 8082)
    ↓
[Pythia processes and returns 10k HDC vector]
    ↓
Translation Bridge (10k → 2048)
    ↓
Truncate to 1536 + Gaussian pad to 2048
    ↓
Latent Bypass via llama_batch
    ↓
Qwen3-VL Response
```

### 5. Translation Bridge Integration
- **Location**: `/Users/danexall/Documents/VS Code Projects/ARCA/services/translation_bridge/`
- **Weights**: `/Users/danexall/Documents/VS Code Projects/ARCA/models/translation_bridge_v1.npz` (377MB)
- **Functions**: `hdc_to_dense()`, `dense_to_hdc()`
- **Status**: ✅ Working and tested

### 6. Startup Script
- **File**: `start_unified_engine.sh`
- Automatically checks for Vulkan support
- Attempts rebuild if needed
- Installs dependencies
- Starts server on port 11436

## ❌ CRITICAL BLOCKER

### llama-cpp-python Vulkan Support
**Status**: NOT BUILT YET

**Problem**:
- PyPI version (0.3.16) is CPU-only
- Multiple build attempts have timed out (5+ minutes)
- CMake builds fail or hang during compilation

**What We've Tried**:
1. ✅ Installed Python 3.11 via Homebrew
2. ✅ Created isolated venv
3. ✅ Installed base dependencies (numpy, fastapi, etc.)
4. ❌ Building llama-cpp-python from source times out
5. ❌ CMake with Vulkan flags hangs

**Why This Matters**:
Without Vulkan support:
- Model runs on CPU only (10-100x slower)
- Latent bypass is impractical (too slow for real-time)
- 4GB VRAM on AMD Radeon goes unused
- Cannot meet performance requirements

## 🔧 NEXT STEPS TO COMPLETE

### Option 1: Manual CMake Build (Recommended)
```bash
cd /Users/danexall/Documents/VS\ Code\ Projects/ARCA/services/llama_cpp_bypass/venv
source bin/activate

# Clone llama-cpp-python
git clone --recurse-submodules https://github.com/abetlen/llama-cpp-python.git

# Replace vendor llama.cpp with local version
rm -rf llama-cpp-python/vendor/llama.cpp
ln -s /Users/danexall/Documents/VS\ Code\ Projects/ARCA/tools/llama.cpp llama-cpp-python/vendor/llama.cpp

# Install build dependencies
pip install scikit-build-core cmake ninja

# Build with Vulkan (this will take 10-20 minutes)
cd llama-cpp-python
export VULKAN_SDK=/usr/local
export CMAKE_ARGS="-DGGML_VULKAN=ON -DGGML_USE_METAL=OFF -DLLAMA_BUILD_TOOLS=OFF"
pip install . --no-build-isolation -v
```

### Option 2: Use Pre-built Server
The existing `llama-server` in `/Users/danexall/Documents/VS Code Projects/ARCA/services/pythia_server/` has Vulkan support but:
- Doesn't support direct latent injection
- Uses Metal (not Vulkan) for GPU
- Only provides HTTP API (no low-level batch access)

### Option 3: Docker/Vagrant
Build in a container with more resources to avoid timeout issues.

## 📋 FILES CREATED

1. `unified_pythia_engine.py` - Main FastAPI server (566 lines)
2. `start_unified_engine.sh` - Startup script with Vulkan check
3. `requirements.txt` - Python dependencies
4. `services/translation_bridge/__init__.py` - Module exports

## 🔗 SERVICE ENDPOINTS

- **Unified Pythia Engine**: `http://localhost:11436`
- **OCI Geometry Embedding**: `http://100.70.0.13:8081/geometry/embed`
- **Dragonfly FIFO**: `http://100.70.0.13:8082/fifo/push` (assumed)
- **Memory API**: `http://127.0.0.1:8088/api/agent/memory`

## ⚠️ CRITICAL REQUIREMENTS

1. **llama-cpp-python MUST be built with Vulkan** for this to work
2. **Translation bridge weights** (377MB) must be present
3. **OCI services** must be accessible via Tailscale
4. **4GB VRAM** is tight - model may need quantization adjustments

## 🚀 TO START THE SERVER

Once Vulkan build is complete:

```bash
cd "/Users/danexall/Documents/VS Code Projects/ARCA/services/llama_cpp_bypass"
./start_unified_engine.sh
```

The server will:
1. Check for Vulkan support
2. Build from source if needed
3. Load Qwen3-VL model
4. Initialize translation bridge
5. Start listening on port 11436

## 📊 TESTING

### Test Health Endpoint
```bash
curl http://localhost:11436/health
```

### Test Chat Completion
```bash
curl -X POST http://localhost:11436/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```

### Test Latent Inject
```bash
curl -X POST http://localhost:11436/v1/latent_inject \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "Dan",
    "original_message": "Hello Pythia...",
    "incoming_vector": null,
    "wait_for_pythia": false
  }'
```

## 🎯 SUCCESS CRITERIA

The latent bypass is working when:
1. ✅ Server starts without errors
2. ✅ Vulkan device is detected (AMD Radeon Pro 5500M)
3. ✅ Model loads into VRAM
4. ✅ Translation bridge processes 10k vectors
5. ✅ Latent injection completes in < 5 seconds
6. ✅ Response text is generated from bypassed vector

**CURRENT STATUS**: Waiting for Vulkan build completion
