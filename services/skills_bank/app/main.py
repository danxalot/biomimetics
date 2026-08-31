
# services/skills_bank/app/main.py
import logging
import os
import redis
from fastapi import FastAPI, HTTPException
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
import uuid
import json

from .models import Skill, ReasoningTrace, SearchResult

# Configuration
DRAGONFLY_URL = os.getenv("DRAGONFLY_URL", "dragonfly:6379")
QDRANT_URL = os.getenv("QDRANT_URL", "qdrant:6333")
HDC_ENCODER_URL = os.getenv("HDC_ENCODER_URL", "http://hdc-encoder:8081")

SKILLS_COLLECTION = "skills"
TRACES_COLLECTION = "reasoning_traces"

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SkillsBank")

app = FastAPI(title="ARCA Skills Bank", version="1.0.0")

# Connections
try:
    host, port = DRAGONFLY_URL.split(":")
    redis_client = redis.Redis(host=host, port=int(port), decode_responses=True)
except Exception as e:
    logger.error(f"Failed to connect to Dragonfly: {e}")
    redis_client = None

try:
    if ":" in QDRANT_URL:
        host, port = QDRANT_URL.split(":")
        qdrant_client = QdrantClient(host=host, port=int(port))
    else:
        qdrant_client = QdrantClient(url=QDRANT_URL)
except Exception as e:
    logger.error(f"Failed to connect to Qdrant: {e}")
    qdrant_client = None

@app.on_event("startup")
async def startup_event():
    # Initialize Qdrant Collections
    if qdrant_client:
        try:
            collections = qdrant_client.get_collections()
            names = [c.name for c in collections.collections]
            
            # Skills Collection
            if SKILLS_COLLECTION not in names:
                qdrant_client.create_collection(
                    collection_name=SKILLS_COLLECTION,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE) # Approx size for generic embeddings, adjustable
                )
                
            # Traces Collection
            if TRACES_COLLECTION not in names:
                qdrant_client.create_collection(
                    collection_name=TRACES_COLLECTION,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
            logger.info("Qdrant collections initialized.")
        except Exception as e:
            logger.error(f"Error initializing Qdrant: {e}")

@app.get("/health")
def health():
    return {
        "status": "healthy", 
        "dragonfly": redis_client.ping() if redis_client else False,
        "qdrant": True if qdrant_client else False
    }

@app.post("/skills")
async def store_skill(skill: Skill):
    if not redis_client:
        raise HTTPException(status_code=503, detail="Dragonfly unavailable")
    
    # Store hot copy in Redis
    key = f"skill:{skill.name}"
    redis_client.set(key, skill.model_dump_json())
    
    # Store semantic copy in Qdrant (stub embedding for now)
    # TODO: Call HDC Encoder to get vector
    if qdrant_client:
        # Placeholder vector
        vector = [0.0] * 384 
        qdrant_client.upsert(
            collection_name=SKILLS_COLLECTION,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=skill.model_dump()
                )
            ]
        )
        
    return {"status": "stored", "name": skill.name}

@app.get("/search")
async def search_skills(query: str, limit: int = 5):
    # TODO: Implement semantic search using HDC encoder + Qdrant
    if not qdrant_client:
        return {"results": []}
    
    # Placeholder: Return empty for now until Encoder is connected
    return {"results": [], "note": "Encoder connection pending"}
