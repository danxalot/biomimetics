"""
memU Service for OpenClaw Container
Provides HTTP API for memory operations.

Embedding: Gemini Embeddings API (text-embedding-004, 1024 dims) or local llama.cpp
Vector store: remote Qdrant (cloud)
Structured store: Firebase Firestore
Model calls: Gemma via memU (separate from embeddings)
"""

import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn

sys.path.insert(0, "/app/memu")

from memory_integration import UnifiedMemory, MemoryBackend, LocalEmbeddingClient, GeminiEmbeddingClient

# ── Config from environment ───────────────────────────────────────────────────
QDRANT_URL_FILE = os.getenv("QDRANT_URL_FILE")
QDRANT_URL = os.getenv("QDRANT_URL", "")  # fallback if not using secret file
QDRANT_KEY_FILE = os.getenv("QDRANT_API_KEY_FILE", "/secrets/qdrant_api_key")
FIREBASE_CREDS = os.getenv("FIREBASE_CREDENTIALS_PATH", "/secrets/gcp_credentials")

# Local embedding server (legacy/fallback)
EMBEDDING_URL = os.getenv("EMBEDDING_URL")  # No default - only used if explicitly set
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "1536"))  # Updated for gemini-embedding-2-preview

# Gemini Embeddings configuration - OMNIMODAL (1536 dimensions)
GEMINI_EMBEDDING_API_KEY_FILE = os.getenv("GEMINI_EMBEDDING_API_KEY_FILE", "/secrets/google_ai_studio")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2-preview")  # Updated to omnimodal
USE_GEMINI_EMBEDDINGS = os.getenv("USE_GEMINI_EMBEDDINGS", "true").lower() == "true"

QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "memu_archive_1536")  # New collection for 1536-dim vectors

# Agent Config (Gemma 3 via Google v1beta)
AGENT_PROVIDER = os.getenv("AGENT_PROVIDER", "gemini")
AGENT_MODEL = os.getenv("AGENT_MODEL")
AGENT_KEY_FILE = os.getenv("AGENT_API_KEY_FILE", "/secrets/google_ai_studio")

# Gemma 3 Rate Limits
AGENT_RPM = int(os.getenv("AGENT_RPM", "30"))       # 30 requests per minute (1 every 2s)
AGENT_TPM = int(os.getenv("AGENT_TPM", "15000"))    # 15k tokens per minute
AGENT_CONTEXT_LIMIT = int(os.getenv("AGENT_CONTEXT_LIMIT", "131072"))  # 130k context

# Embedding Rate Limits
EMBEDDING_RPM = int(os.getenv("EMBEDDING_RPM", "100"))  # 100 requests per minute
EMBEDDING_TPM = int(os.getenv("EMBEDDING_TPM", "30"))   # 30 tokens per minute
EMBEDDING_TPD = int(os.getenv("EMBEDDING_TPD", "1000")) # 1k tokens per day

# ── Global state ──────────────────────────────────────────────────────────────
memory: Optional[UnifiedMemory] = None
_resolved_qdrant_url: str = ""


def _read_secret(path: str) -> Optional[str]:
    """Read secret from file path with fallback to environment variable"""
    if path and os.path.exists(path):
        val = open(path).read().strip()
        # Handle "KEY=VALUE" or "KEY:VALUE" formats
        if "=" in val and "\n" not in val:
            val = val.split("=", 1)[1].strip()
        elif ":" in val and "\n" not in val and not val.startswith("{"): # don't split JSON
            # Only split if it looks like a prefix, not a URL
            parts = val.split(":", 1)
            if len(parts[0]) < 20: # arbitrary prefix length
                val = parts[1].strip()
        if val:
            return val
    
    # Fallback: try environment variable based on path
    env_var_map = {
        "/secrets/google_ai_studio": "GEMINI_API_KEY",
        "/secrets/qdrant_api_key": "QDRANT_API_KEY",
        "/secrets/gcp_credentials": "GOOGLE_APPLICATION_CREDENTIALS",
        "/run/secrets/google_ai_studio": "GEMINI_API_KEY",
        "/run/secrets/qdrant_api_key": "QDRANT_API_KEY",
        "/run/secrets/gcp_credentials": "GOOGLE_APPLICATION_CREDENTIALS",
    }
    env_var = env_var_map.get(path)
    if env_var:
        return os.environ.get(env_var)
    
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global memory, _resolved_qdrant_url

    # Resolve Qdrant URL
    qdrant_url = _read_secret(QDRANT_URL_FILE) or QDRANT_URL
    if not qdrant_url:
        raise RuntimeError("No Qdrant URL configured")
    _resolved_qdrant_url = qdrant_url

    qdrant_api_key = _read_secret(QDRANT_KEY_FILE)
    agent_api_key = _read_secret(AGENT_KEY_FILE)
    gemini_embedding_api_key = _read_secret(GEMINI_EMBEDDING_API_KEY_FILE)
    
    # Debug logging for secret loading
    print(f"🔑 GEMINI_EMBEDDING_API_KEY_FILE path: {GEMINI_EMBEDDING_API_KEY_FILE}")
    print(f"🔑 Secret exists at path: {os.path.exists(GEMINI_EMBEDDING_API_KEY_FILE)}")
    print(f"🔑 GEMINI_API_KEY env var set: {bool(os.environ.get('GEMINI_API_KEY'))}")
    print(f"🔑 Loaded gemini_embedding_api_key: {'***' + gemini_embedding_api_key[-4:] if gemini_embedding_api_key else 'None'}")
    print(f"🔑 USE_GEMINI_EMBEDDINGS: {USE_GEMINI_EMBEDDINGS}")

    memory = UnifiedMemory(
        qdrant_host=qdrant_url,
        firebase_project="arca-471022",
        agent_api_key=agent_api_key,
        agent_provider=AGENT_PROVIDER,
        agent_model=AGENT_MODEL,
        embedding_url=EMBEDDING_URL,  # Only used if Gemini embeddings disabled
        embedding_dims=EMBEDDING_DIMS,
        gemini_api_key=gemini_embedding_api_key,
        gemini_embedding_model=GEMINI_EMBEDDING_MODEL,
        use_gemini_embeddings=USE_GEMINI_EMBEDDINGS,
    )

    # Qdrant init
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    cloud_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    try:
        existing = [c.name for c in cloud_client.get_collections().collections]
        if QDRANT_COLLECTION not in existing:
            cloud_client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=EMBEDDING_DIMS, distance=Distance.COSINE),
            )
        print(f"✅ Qdrant connected: {qdrant_url}")
    except Exception as e:
        print(f"⚠️  Qdrant connection issue (will retry on first use): {e}")

    memory.qdrant.client = cloud_client
    memory.qdrant.collection = QDRANT_COLLECTION
    memory.qdrant._initialized = True

    # Firebase
    if FIREBASE_CREDS and os.path.exists(FIREBASE_CREDS):
        memory.firebase.initialize(credentials_path=FIREBASE_CREDS)

    print(f"✅ Agent: {AGENT_PROVIDER} ({AGENT_MODEL or 'default'}) @ {AGENT_RPM} rpm, {AGENT_TPM} tpm")
    print(f"✅ Embeddings: Gemini ({GEMINI_EMBEDDING_MODEL}) @ {EMBEDDING_RPM} rpm, {EMBEDDING_TPM} tpm, {EMBEDDING_TPD} tpd")
    print(f"✅ memU service ready")

    yield

    if memory and memory.embedder:
        await memory.embedder.close()
    if memory and memory.agent:
        await memory.agent.close()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="memU Service", version="1.2.0", lifespan=lifespan)


# ── Request models ────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    temperature: float = 0.7
    max_tokens: int = 4096


class EmbedRequest(BaseModel):
    text: str


class StoreRequest(BaseModel):
    # OpenClaw sends {"text": "..."} matching its local SQLite schema
    # We accept both field names — text takes priority if content is absent
    content: Optional[str] = None
    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    backends: Optional[List[str]] = None  # ["qdrant", "firebase", "obsidian"]

    def resolved_content(self) -> str:
        val = self.content or self.text
        if not val:
            raise ValueError("Either 'content' or 'text' must be provided")
        return val


class RecallRequest(BaseModel):
    # OpenClaw sends {"text": "..."} or {"query": "..."}
    query: Optional[str] = None
    text: Optional[str] = None
    limit: int = 5
    backends: Optional[List[str]] = None
    tags: Optional[List[str]] = None

    def resolved_query(self) -> str:
        val = self.query or self.text
        if not val:
            raise ValueError("Either 'query' or 'text' must be provided")
        return val


class SearchRequest(BaseModel):
    """Cloud Function Gateway search request"""
    query: str
    user_id: Optional[str] = "default"
    limit: int = 10
    min_confidence: float = 0.3


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    embedder_ok = memory is not None and memory.embedder is not None
    agent_ok = memory is not None and memory.agent is not None
    
    # Determine embedder type
    embedder_type = "none"
    if memory and memory.embedder:
        if isinstance(memory.embedder, GeminiEmbeddingClient):
            embedder_type = "gemini"
        elif isinstance(memory.embedder, LocalEmbeddingClient):
            embedder_type = "local"
    
    return {
        "status": "healthy",
        "service": "memu",
        "version": "1.2.0",
        "agent": {
            "provider": AGENT_PROVIDER,
            "model": AGENT_MODEL,
            "ready": agent_ok
        },
        "embedding": {
            "type": embedder_type,
            "model": GEMINI_EMBEDDING_MODEL if embedder_type == "gemini" else None,
            "url": EMBEDDING_URL if embedder_type == "local" else None,
            "dims": EMBEDDING_DIMS,
        },
        "qdrant_url": _resolved_qdrant_url,
        "qdrant_collection": QDRANT_COLLECTION,
        "embedder_ready": embedder_ok,
    }


@app.post("/search")
async def search_memories(req: SearchRequest):
    """
    Search archive memories via Qdrant + Firestore.
    Used by Cloud Function Gateway for unified memory queries.
    
    Args:
        query: Search query text
        user_id: User identifier (for multi-tenant support)
        limit: Max results to return
        min_confidence: Minimum confidence threshold
    
    Returns:
        Unified search results with confidence scores
    """
    if not memory:
        raise HTTPException(status_code=503, detail="Memory system not initialised")
    
    try:
        # Generate embedding for the query
        query_embedding = await memory.embedder.generate_embedding(req.query)

        # Search Qdrant for similar vectors using correct API
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        search_results = memory.qdrant.client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_embedding,
            limit=req.limit,
            score_threshold=req.min_confidence
        ).points

        # Format results with confidence scores
        results = []
        for hit in search_results:
            result = {
                "id": hit.id,
                "content": hit.payload.get("content", "") if hit.payload else "",
                "metadata": hit.payload.get("metadata", {}) if hit.payload else {},
                "confidence": hit.score,
                "source": "memu_archive"
            }
            results.append(result)
        
        return {
            "status": "success",
            "query": req.query,
            "user_id": req.user_id,
            "results": results,
            "source": "memu_archive",
            "total_found": len(results)
        }
        
    except Exception as e:
        # Return empty results on error (don't fail the entire gateway)
        return {
            "status": "error",
            "query": req.query,
            "results": [],
            "error": str(e),
            "source": "memu_archive"
        }


@app.post("/complete")
async def model_complete(req: ChatRequest):
    """Completion endpoint for agent calls"""
    if not memory or not memory.agent:
        raise HTTPException(status_code=533, detail="Agent not configured")
    try:
        result = await memory.agent.complete(
            messages=req.messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/embed")
async def generate_embedding(req: EmbedRequest):
    """Generate embedding via local llama.cpp server"""
    if not memory or not memory.embedder:
        raise HTTPException(status_code=503, detail="Embedding server not configured")
    try:
        embedding = await memory.embedder.generate_embedding(req.text)
        return {"embedding": embedding, "dimension": len(embedding)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/embeddings")
async def openai_embeddings(req: dict):
    """OpenAI-compatible embeddings endpoint for OpenClaw memory search"""
    if not memory or not memory.embedder:
        raise HTTPException(status_code=503, detail="Embedding server not configured")

    input_texts = req.get("input", [])
    if isinstance(input_texts, str):
        input_texts = [input_texts]

    model = req.get("model", "memu-embedding")

    try:
        embeddings = []
        for text in input_texts:
            emb = await memory.embedder.generate_embedding(text)
            embeddings.append(
                {"object": "embedding", "embedding": emb, "index": len(embeddings)}
            )

        return {
            "object": "list",
            "data": embeddings,
            "model": model,
            "usage": {
                "prompt_tokens": sum(len(t.split()) for t in input_texts),
                "total_tokens": sum(len(t.split()) for t in input_texts),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/store")
async def store_memory(req: StoreRequest):
    """Store memory across backends (Qdrant + Firebase by default).
    Accepts both {"content": ...} and {"text": ...} for OpenClaw compatibility."""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory system not initialised")
    try:
        content = req.resolved_content()
        backends = [MemoryBackend(b) for b in req.backends] if req.backends else None
        await memory.store(
            content=content,
            metadata=req.metadata,
            tags=req.tags,
            backends=backends,
        )
        used = req.backends or ["qdrant", "firebase"]
        return {"status": "stored", "backends": used}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recall")
async def recall_memory(req: RecallRequest):
    """Semantic search across memory backends.
    Accepts both {"query": ...} and {"text": ...} for OpenClaw compatibility."""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory system not initialised")
    try:
        query = req.resolved_query()
        backends = [MemoryBackend(b) for b in req.backends] if req.backends else None
        results = await memory.recall(query=query, backends=backends, limit=req.limit, filter_tags=req.tags)
        return {
            "results": [
                {
                    "id": r.id,
                    "content": r.content,
                    "metadata": r.metadata,
                    "tags": r.tags,
                    "created_at": r.created_at.isoformat() if hasattr(r, "created_at") and r.created_at else None,
                }
                for r in results
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
async def search_memory(req: RecallRequest):
    """Alias for /recall — OpenClaw's memorySearch.remote calls /search.
    Accepts {"text": ...} or {"query": ...}."""
    return await recall_memory(req)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8096)
