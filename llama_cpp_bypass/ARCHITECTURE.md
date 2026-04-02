# Unified Pythia Engine - Complete Architecture & Process

## ✅ CORRECTED SERVICE ENDPOINTS (from Docker on OCI)

All services are running in Docker containers on `100.70.0.13`:

| Port | Service | Container | Key Endpoints |
|------|---------|-----------|---------------|
| **8081** | Qwen3-VL-Embedding-2B | geometry_embedding | `POST /embeddings` |
| 8082 | embedding-1024 | embedding-1024 | - |
| **8087** | geometry_kernel | geometry_kernel | `POST /geometry/ingest_recursive` |
| 8096 | geometry_onnx_interpreter | geometry_onnx_interpreter | - |
| **6380** | Dragonfly (Redis compat) | dragonfly | Redis protocol |
| 6379 | pythia_redis | pythia_redis | Redis protocol |

## COMPLETE MESSAGE FLOW

### Your Request
- **User**: Dan
- **Message**: "Hello Pythia - I'm sorry for the long delay..."
- **User_ID**: Dan

### Step 1: Format the Message (Local)
The system formats the message as:
```
(User_ID: Dan, Timestamp: 2026-03-22T17:30:00Z, Message: Hello Pythia...)
```

### Step 2: Get Embedding from OCI (port 8081)
```
POST http://100.70.0.13:8081/embeddings
{
  "input": "(User_ID: Dan, Timestamp: 2026-03-22T17:30:00Z, Message: Hello Pythia...)"
}
```
**Returns**: 2048d embedding vector

### Step 3: Truncate to 512d and Push to Dragonfly (port 6380)
- Truncate embedding from 2048d → 512d
- Push to Dragonfly using Redis protocol
- Key format: `pythia_Dan_{timestamp}`

### Step 4: Pythia Processes (on OCI)
Pythia retrieves the 512d vector from Dragonfly, processes it, and returns a **10,000d HDC vector**

### Step 5: Save Pythia's 10k Response (Local)
**CRITICAL**: The 10k HDC vector must be saved to a file BEFORE processing

### Step 6: Process Through Translation Bridge
```
10,000d HDC vector → Translation Bridge → 2,048d dense vector
```

### Step 7: Truncate and Pad
```
2,048d dense → Truncate to 1,536d → Pad with 512d Gaussian noise → 2,048d
```

### Step 8: Latent Bypass (Local GPU)
Using llama-cpp-python with Vulkan:
- Inject the 2,048d vector directly into the model via llama_batch
- Generate response

### Step 9: Save and Return
- Save response to Memory API (port 8088)
- Return response to user

## CODE CHANGES MADE

### 1. Service URLs Updated
```python
GEOMETRY_KERNEL_URL = "http://100.70.0.13:8087"
GEOMETRY_EMBEDDING_URL = "http://100.70.0.13:8081"
DRAGONFLY_HOST = "100.70.0.13"
DRAGONFLY_PORT = 6380
```

### 2. Message Formatting
```python
timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
formatted_text = f"(User_ID: {user_id}, Timestamp: {timestamp}, Message: {text})"
```

### 3. Correct Embedding Endpoint
```python
response = await client.post(
    f"{GEOMETRY_EMBEDDING_URL}/embeddings",  # NOT /geometry/embed
    json={"input": formatted_text}  # Correct format for llama-server
)
```

### 4. Dragonfly Integration
Uses Redis protocol on port 6380 to cache 512d vectors

## FILES CREATED

1. **unified_pythia_engine.py** - Main FastAPI server with:
   - `/health` - Health check
   - `/v1/chat/completions` - Standard chat
   - `/v1/latent_inject` - Full latent bypass pipeline
   - `/v1/geometry_embed` - Direct embedding service

2. **start_unified_engine.sh** - Startup script with Vulkan check

3. **requirements.txt** - Python dependencies

4. **services/translation_bridge/__init__.py** - Module exports

## EXECUTION COMMAND

```bash
cd "/Users/danexall/Documents/VS Code Projects/ARCA/services/llama_cpp_bypass"
source venv/bin/activate
./start_unified_engine.sh
```

## API USAGE

### Test Health
```bash
curl http://localhost:11436/health
```

### Submit Message
```bash
curl -X POST http://localhost:11436/v1/latent_inject \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "Dan",
    "original_message": "Hello Pythia - I'\''m sorry for the long delay before communication..."
  }'
```

## CRITICAL REQUIREMENTS

1. ✅ llama-cpp-python built with Vulkan support
2. ✅ Translation bridge weights at `models/translation_bridge_v1.npz`
3. ✅ OCI services accessible via Tailscale (100.70.0.13)
4. ✅ Dragonfly cache running on port 6380
5. ✅ Qwen3-VL-2B-Instruct model at `models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf`

## WHAT STILL NEEDS TO BE DONE

1. **Save Pythia's 10k response** - The code needs to save the 10k HDC vector before processing
2. **Test the full pipeline** - Run an end-to-end test
3. **Verify Dragonfly integration** - Ensure vectors are being cached/retrieved properly
