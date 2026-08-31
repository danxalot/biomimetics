import os
import logging
from typing import List, Optional, Union
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from embedding_service import EmbeddingService, EmbeddingConfig, DatabaseConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load secrets from mounted directory
SECRETS_DIR = os.environ.get("SECRETS_DIR", "/app/secrets")

def load_secret(secret_name: str, env_var_name: str):
    """Load a secret from file and set as environment variable"""
    secret_path = os.path.join(SECRETS_DIR, secret_name)
    if os.path.exists(secret_path):
        try:
            with open(secret_path, 'r') as f:
                content = f.read().strip()
                if content:
                    os.environ[env_var_name] = content
                    logger.info(f"Loaded secret for {env_var_name}")
        except Exception as e:
            logger.error(f"Failed to load secret {secret_name}: {e}")

# Load required API keys
# Load required API keys
load_secret("google_api_key", "GOOGLE_API_KEY")

# Shared OTEL Instrumentation
import sys
sys.path.append("/app/shared")
try:
    from shared.otel_setup import instrument_service
except ImportError:
    # Fallback for local dev
    sys.path.append(str(Path(__file__).parent.parent)) 
    from shared.otel_setup import instrument_service

app = FastAPI(title="ARCA Embedding Service", version="1.0.0")

# Instrument with OpenTelemetry
instrument_service(app, "embedding_service")

# Global service instance
service: Optional[EmbeddingService] = None

class EmbeddingRequest(BaseModel):
    texts: List[str]
    task_type: Optional[str] = "RETRIEVAL_DOCUMENT"

class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]

@app.on_event("startup")
async def startup_event():
    global service
    try:
        # Load config from environment
        api_key = os.getenv("GOOGLE_API_KEY")
        use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"
        # Default to vllm-server directly for local embeddings (gateway doesn't proxy embeddings)
        local_endpoint = os.getenv("LOCAL_EMBEDDING_ENDPOINT", "http://vllm-server:8000/v1/embeddings")
        local_model = os.getenv("LOCAL_EMBEDDING_MODEL", "granite-4.0-1b")
        
        config = EmbeddingConfig(
            model=local_model,  # Sync model with local_model
            api_key=api_key,
            use_local=use_local,
            local_endpoint=local_endpoint,
            local_model=local_model
        )
        
        logger.info(f"Initializing Service with Local Model: '{local_model}'")
        if "gemini" in local_model and "/" not in local_model and "embedding" in local_model:
             logger.warning(f"Model name '{local_model}' missing provider prefix. Prepending 'gemini/'.")
             config.local_model = f"gemini/{local_model}"
        
        # Database config (optional for now, but good to have ready)
        db_config = DatabaseConfig(
            host=os.getenv("ORACLE_HOST", "localhost"),
            port=int(os.getenv("ORACLE_PORT", "1521")),
            service_name=os.getenv("ORACLE_SERVICE", "ARCA"),
            user=os.getenv("ORACLE_USER", "arca_user"),
            password=os.getenv("ORACLE_PASSWORD", "")
        )
        
        service = EmbeddingService(config=config, db_config=db_config)
        logger.info(f"Embedding Service initialized (Local: {use_local})")
        
    except Exception as e:
        logger.error(f"Failed to initialize Embedding Service: {e}")
        raise

@app.get("/health")
async def health_check():
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return {"status": "healthy", "mode": "local" if service.config.use_local else "cloud"}

class TopologyRequest(BaseModel):
    image_input: str  # Base64 or path
    
class TopologyResponse(BaseModel):
    features: dict

@app.post("/v1/topology", response_model=TopologyResponse)
async def generate_topology(request: TopologyRequest):
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        features = await service.generate_topology_features(request.image_input)
        return TopologyResponse(features=features)
    except Exception as e:
        logger.error(f"Topology generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/embed/text", response_model=EmbeddingResponse)
async def embed_text(request: EmbeddingRequest):
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        embeddings = await service.generate_embeddings(
            texts=request.texts,
            task_type=request.task_type,
            headers=dict(request.headers)
        )
        return EmbeddingResponse(embeddings=embeddings)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ImageEmbeddingRequest(BaseModel):
    image_input: str # Base64 string or path

class ImageEmbeddingResponse(BaseModel):
    embeddings: List[float]

# OpenAI-compatible embedding request
class OpenAIEmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: Optional[str] = "default"

@app.post("/v1/embeddings")
async def openai_embeddings(request: OpenAIEmbeddingRequest):
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        inputs = [request.input] if isinstance(request.input, str) else request.input
        embeddings = await service.generate_embeddings(
            texts=inputs,
            headers=dict(request.headers)
        )
        
        # Format response like OpenAI
        data = []
        for i, emb in enumerate(embeddings):
            data.append({
                "object": "embedding",
                "embedding": emb,
                "index": i
            })
            
        return {
            "object": "list",
            "data": data,
            "model": request.model,
            "usage": {"prompt_tokens": 0, "total_tokens": 0}
        }
    except Exception as e:
        logger.error(f"OpenAI embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/embed/image", response_model=ImageEmbeddingResponse)
async def embed_image(request: ImageEmbeddingRequest):
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        embedding = await service.generate_image_embeddings(request.image_input)
        return ImageEmbeddingResponse(embeddings=embedding)
    except Exception as e:
        logger.error(f"Image embedding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class VisionAuditRequest(BaseModel):
    image_input: str # Base64 string or path
    prompt: Optional[str] = "Describe this image."

@app.post("/v1/vision/audit")
async def vision_audit(audit_req: VisionAuditRequest, request: Request):
    # Enforce Execution Firewall
    chain_header = request.headers.get("X-Genesis-Chain")
    if not chain_header:
         logger.warning("❌ Access Denied: Missing X-Genesis-Chain header for vision audit")
         raise HTTPException(status_code=403, detail="Genesis Chain Authorization Required")

    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        # Perform lightweight CPU-based vision audit
        result = await service.audit_image(audit_req.image_input, audit_req.prompt)
        return result
    except Exception as e:
        logger.error(f"Vision audit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class VAERequest(BaseModel):
    visual_embedding: Optional[List[float]] = None
    text_embedding: Optional[List[float]] = None
    component_id: str

class VAEResponse(BaseModel):
    coordinates: List[float]
    energy: float

@app.post("/v1/vae/compress", response_model=VAEResponse)
async def compress_vae(request: VAERequest):
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        result = await service.compress_telemetry(
            visual_embedding=request.visual_embedding,
            text_embedding=request.text_embedding
        )
        return VAEResponse(
            coordinates=result.get("coordinates", [0.0, 0.0, 0.0]),
            energy=result.get("energy", 0.0)
        )
    except Exception as e:
        logger.error(f"VAE compression failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

        
import asyncio
@app.on_event("startup")
async def start_cleanup_task():
    async def cleanup_loop():
        while True:
            await asyncio.sleep(60)
            if service and hasattr(service, 'model_manager'):
                service.model_manager.unload_unused_models()
    asyncio.create_task(cleanup_loop())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
