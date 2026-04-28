"""
memU Service for OpenClaw Container
Provides HTTP API for memory operations.

Embedding: Gemini Embeddings API (gemini-embedding-2-preview, 1536 dims)
Vector store: remote Qdrant (cloud)
Structured store: Firebase Firestore (via Application Default Credentials)
Model calls: Gemma 3 12b-it via Google v1beta
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

# Local embedding server (legacy/fallback)
EMBEDDING_URL = os.getenv("EMBEDDING_URL")  # Only used if explicitly set
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "1536"))  # gemini-embedding-2-preview → 1536

# Gemini Embeddings configuration
GEMINI_EMBEDDING_API_KEY_FILE = os.getenv("GEMINI_EMBEDDING_API_KEY_FILE", "/secrets/google_ai_studio")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2-preview")
USE_GEMINI_EMBEDDINGS = os.getenv("USE_GEMINI_EMBEDDINGS", "true").lower() == "true"

QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "memu_archive_1536")

# Agent Config (Gemma 3 12b-it via Google v1beta)
AGENT_PROVIDER = os.getenv("AGENT_PROVIDER", "gemini")
AGENT_MODEL = os.getenv("AGENT_MODEL", "gemma-3-12b-it")
AGENT_KEY_FILE = os.getenv("AGENT_API_KEY_FILE", "/secrets/google_ai_studio")

# Firebase / GCP project
FIREBASE_PROJECT = os.getenv("FIREBASE_PROJECT", "arca-471022")
FIREBASE_COLLECTION = os.getenv("FIREBASE_COLLECTION", "memu_memories")

# Rate Limits
AGENT_RPM = int(os.getenv("AGENT_RPM", "30"))
AGENT_TPM = int(os.getenv("AGENT_TPM", "15000"))
AGENT_CONTEXT_LIMIT = int(os.getenv("AGENT_CONTEXT_LIMIT", "131072"))

EMBEDDING_RPM = int(os.getenv("EMBEDDING_RPM", "100"))
EMBEDDING_TPD = int(os.getenv("EMBEDDING_TPD", "1000"))

# ── Global state ──────────────────────────────────────────────────────────────
memory: Optional[UnifiedMemory] = None
_resolved_qdrant_url: str = ""
_qdrant_client = None


def _read_secret(path: str) -> Optional[str]:
    """Read secret from file path with fallback to environment variable"""
    if path and os.path.exists(path):
        val = open(path).read().strip()
        if "=" in val and "\n" not in val:
            val = val.split("=", 1)[1].strip()
        elif ":" in val and "\n" not in val and not val.startswith("{"):
            parts = val.split(":", 1)
            if len(parts[0]) < 20:
                val = parts[1].strip()
        if val:
            return val

    env_var_map = {
        "/secrets/google_ai_studio": "GEMINI_API_KEY",
        "/secrets/qdrant_api_key": "QDRANT_API_KEY",
        "/run/secrets/google_ai_studio": "GEMINI_API_KEY",
        "/run/secrets/qdrant_api_key": "QDRANT_API_KEY",
    }
    env_var = env_var_map.get(path)
    if env_var:
        return os.environ.get(env_var)

    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global memory, _resolved_qdrant_url, _qdrant_client

    # ── Resolve secrets ───────────────────────────────────────────────────────
    qdrant_url = _read_secret(QDRANT_URL_FILE) or QDRANT_URL
    if not qdrant_url:
        raise RuntimeError("No Qdrant URL configured")
    _resolved_qdrant_url = qdrant_url

    qdrant_api_key = _read_secret(QDRANT_KEY_FILE)
    agent_api_key = _read_secret(AGENT_KEY_FILE)
    gemini_embedding_api_key = _read_secret(GEMINI_EMBEDDING_API_KEY_FILE)

    print(f"🔑 GEMINI_EMBEDDING_API_KEY_FILE path: {GEMINI_EMBEDDING_API_KEY_FILE}")
    print(f"🔑 Secret exists at path: {os.path.exists(GEMINI_EMBEDDING_API_KEY_FILE)}")
    print(f"🔑 Loaded key: {'***' + gemini_embedding_api_key[-4:] if gemini_embedding_api_key else 'None'}")
    print(f"🔑 USE_GEMINI_EMBEDDINGS: {USE_GEMINI_EMBEDDINGS}")

    # ── UnifiedMemory init ────────────────────────────────────────────────────
    memory = UnifiedMemory(
        qdrant_host=qdrant_url,
        firebase_project=FIREBASE_PROJECT,
        agent_api_key=agent_api_key,
        agent_provider=AGENT_PROVIDER,
        agent_model=AGENT_MODEL,
        embedding_url=EMBEDDING_URL,
        embedding_dims=EMBEDDING_DIMS,
        gemini_api_key=gemini_embedding_api_key,
        gemini_embedding_model=GEMINI_EMBEDDING_MODEL,
        use_gemini_embeddings=USE_GEMINI_EMBEDDINGS,
    )

    # ── Qdrant init ───────────────────────────────────────────────────────────
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    _qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    try:
        existing = [c.name for c in _qdrant_client.get_collections().collections]
        if QDRANT_COLLECTION not in existing:
            _qdrant_client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=EMBEDDING_DIMS, distance=Distance.COSINE),
            )
            print(f"✅ Qdrant: created collection '{QDRANT_COLLECTION}' ({EMBEDDING_DIMS} dims)")
        else:
            print(f"✅ Qdrant connected — collection '{QDRANT_COLLECTION}' exists")
    except Exception as e:
        print(f"⚠️  Qdrant connection issue (will retry on first use): {e}")

    memory.qdrant.client = _qdrant_client
    memory.qdrant.collection = QDRANT_COLLECTION
    memory.qdrant._initialized = True

    # ── Firebase init (always via ADC on Cloud Run) ───────────────────────────
    # No credentials file needed — Cloud Run SA provides ADC automatically.
    # arca-service-agent@arca-471022.iam.gserviceaccount.com has roles/datastore.user
    try:
        memory.firebase.initialize()
        print(f"✅ Firebase Firestore connected — project: {FIREBASE_PROJECT}")
    except Exception as e:
        print(f"⚠️  Firebase init failed (non-fatal): {e}")

    print(f"✅ Agent: {AGENT_PROVIDER}/{AGENT_MODEL} @ {AGENT_RPM} rpm")
    print(f"✅ Embeddings: {GEMINI_EMBEDDING_MODEL} @ {EMBEDDING_RPM} rpm, {EMBEDDING_TPD} tpd")
    print(f"✅ memU v1.3.0 ready")

    yield

    if memory and memory.embedder:
        await memory.embedder.close()
    if memory and memory.agent:
        await memory.agent.close()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="memU Service", version="1.3.0", lifespan=lifespan)


# ── Request models ────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    temperature: float = 0.7
    max_tokens: int = 4096


class EmbedRequest(BaseModel):
    text: str


class StoreRequest(BaseModel):
    content: Optional[str] = None
    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    backends: Optional[List[str]] = None

    def resolved_content(self) -> str:
        val = self.content or self.text
        if not val:
            raise ValueError("Either 'content' or 'text' must be provided")
        return val


class RecallRequest(BaseModel):
    """OpenClaw /recall — accepts {query} or {text}"""
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
    """Cloud Function Gateway /search — accepts {query}, {text}, or {user_id, limit, min_confidence}"""
    query: Optional[str] = None
    text: Optional[str] = None              # alias accepted for OpenClaw compat
    user_id: Optional[str] = "default"
    limit: int = 10
    min_confidence: float = 0.3

    def resolved_query(self) -> str:
        val = self.query or self.text
        if not val:
            raise ValueError("Either 'query' or 'text' must be provided in /search request")
        return val


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    embedder_ok = memory is not None and memory.embedder is not None
    agent_ok = memory is not None and memory.agent is not None
    firebase_ok = memory is not None and memory.firebase is not None and memory.firebase.db is not None

    embedder_type = "none"
    if memory and memory.embedder:
        if isinstance(memory.embedder, GeminiEmbeddingClient):
            embedder_type = "gemini"
        elif isinstance(memory.embedder, LocalEmbeddingClient):
            embedder_type = "local"

    return {
        "status": "healthy",
        "service": "memu",
        "version": "1.3.0",
        "agent": {
            "provider": AGENT_PROVIDER,
            "model": AGENT_MODEL,
            "ready": agent_ok,
        },
        "embedding": {
            "type": embedder_type,
            "model": GEMINI_EMBEDDING_MODEL if embedder_type == "gemini" else None,
            "dims": EMBEDDING_DIMS,
        },
        "firebase": {
            "project": FIREBASE_PROJECT,
            "ready": firebase_ok,
        },
        "qdrant_url": _resolved_qdrant_url,
        "qdrant_collection": QDRANT_COLLECTION,
        "embedder_ready": embedder_ok,
    }


@app.post("/search")
async def search_memories(req: SearchRequest):
    """
    Unified search endpoint — handles both:
      - Cloud Function Gateway: {query, user_id, limit, min_confidence}
      - OpenClaw legacy: {text, limit}

    Previously there were TWO competing @app.post('/search') decorators on this
    file — the second (RecallRequest alias) overwrote the first, causing all
    gateway calls to fail with a 422/500 which timed out to a 504.
    """
    if not memory:
        raise HTTPException(status_code=503, detail="Memory system not initialised")

    try:
        q = req.resolved_query()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        # Generate 1536-dim embedding
        query_embedding = await memory.embedder.generate_embedding(q)

        search_results = _qdrant_client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_embedding,
            limit=req.limit,
            score_threshold=req.min_confidence,
        ).points

        results = [
            {
                "id": hit.id,
                "content": hit.payload.get("content", "") if hit.payload else "",
                "metadata": hit.payload.get("metadata", {}) if hit.payload else {},
                "confidence": hit.score,
                "source": "memu_archive",
            }
            for hit in search_results
        ]

        return {
            "status": "success",
            "query": q,
            "user_id": req.user_id,
            "results": results,
            "source": "memu_archive",
            "total_found": len(results),
        }

    except Exception as e:
        # Return structured error — do NOT silently swallow to empty results
        print(f"❌ /search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recall")
async def recall_memory(req: RecallRequest):
    """Semantic search across memory backends (OpenClaw primary interface)."""
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


@app.post("/complete")
async def model_complete(req: ChatRequest):
    """Completion endpoint for agent calls (Gemma 3 12b-it)"""
    if not memory or not memory.agent:
        raise HTTPException(status_code=503, detail="Agent not configured")
    try:
        result = await memory.agent.complete(
            messages=req.messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/embed")
async def generate_embedding(req: EmbedRequest):
    """Generate 1536-dim embedding via Gemini Embeddings API"""
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
            embeddings.append({"object": "embedding", "embedding": emb, "index": len(embeddings)})

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
    """Store memory across backends (Qdrant + Firebase by default)."""
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8096)
