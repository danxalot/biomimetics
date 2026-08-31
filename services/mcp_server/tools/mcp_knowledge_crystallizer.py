import os
import sys
import logging
import json
import httpx
import asyncio
from neo4j import GraphDatabase
from mcp.server.fastmcp import FastMCP

# Add the project root to sys.path to allow importing from services
# We assume this file is at services/mcp_server/tools/mcp_knowledge_crystallizer.py
# So project root is ../../../
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
if project_root not in sys.path:
    sys.path.append(project_root)

# Attempt to import EmbeddingService
try:
    from services.embedding_system.embedding_service import EmbeddingService, EmbeddingConfig
    EMBEDDING_SERVICE_AVAILABLE = True
except ImportError:
    EMBEDDING_SERVICE_AVAILABLE = False
    EmbeddingService = None
    EmbeddingConfig = None

# Initialize FastMCP
mcp = FastMCP("mcp-knowledge-crystallizer")
logger = logging.getLogger(__name__)

# Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "arca_password")
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8000/v1/chat/completions")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

async def generalize_observation(observation: str) -> str:
    """Calls LLM Gateway to generalize a specific observation into an abstract pattern."""
    async with httpx.AsyncClient() as client:
        payload = {
            "model": "learnlm-2.0-flash-experimental", # Specialized model for generalization
            "messages": [
                {"role": "system", "content": "You are an expert systems architect. Generalize the following specific observation into a reusable, abstract technical pattern or anti-pattern description. Be concise and focus on the underlying principle."},
                {"role": "user", "content": observation}
            ],
            "temperature": 0.3
        }
        try:
            # We need to handle potential connection errors if gateway is down
            response = await client.post(LLM_GATEWAY_URL, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Failed to generalize observation: {e}")
            return observation # Fallback to original if AI fails

async def get_embedding(text: str) -> list[float]:
    """Generates an embedding using the EmbeddingService."""
    if not EMBEDDING_SERVICE_AVAILABLE:
        logger.warning("Embedding service not available.")
        return []
    
    # Check for local embedding preference
    use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"
    
    if not use_local and not GOOGLE_API_KEY:
        logger.warning("Google API key missing and local embeddings not enabled.")
        return []
    
    try:
        config = EmbeddingConfig(
            api_key=GOOGLE_API_KEY,
            use_local=use_local
        )
        service = EmbeddingService(config=config)
        # generate_embeddings is async
        embeddings = await service.generate_embeddings([text])
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
    
    return []

@mcp.tool()
async def crystallize_pattern(pattern_name: str, type: str, observation: str, context_tags: list[str] = None) -> str:
    """
    Analyzes a specific observation, generalizes it into a pattern using AI, 
    generates an embedding, and saves it to the Knowledge Graph.
    
    Args:
        pattern_name: A short name for the pattern (e.g., 'Docker Volume Race Condition').
        type: The type of pattern ("Pattern" or "AntiPattern").
        observation: The specific detailed observation or error encountered.
        context_tags: List of tags to categorize the pattern (e.g., ['docker', 'storage']).
    """
    if type not in ["Pattern", "AntiPattern"]:
        return "Error: Type must be either 'Pattern' or 'AntiPattern'."

    # 1. Generalize the observation
    description = await generalize_observation(observation)
    
    # 2. Generate Embedding
    embedding = await get_embedding(description)
    
    # 3. Save to Neo4j
    driver = None
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        query = """
        MERGE (p:KnowledgePattern {name: $name})
        SET p.type = $type,
            p.description = $description,
            p.original_observation = $observation,
            p.embedding = $embedding,
            p.created_at = datetime()
        
        WITH p
        UNWIND $tags as tag
        MERGE (t:ContextTag {name: tag})
        MERGE (p)-[:RELATED_TO]->(t)
        
        RETURN p.name as name
        """
        
        with driver.session() as session:
            result = session.run(query, 
                               name=pattern_name, 
                               type=type, 
                               description=description,
                               observation=observation,
                               embedding=embedding,
                               tags=context_tags or [])
            record = result.single()
            if record:
                return f"Successfully crystallized pattern: {record['name']}\\nGeneralized Description: {description}"
            else:
                return "Failed to save pattern."
                
    except Exception as e:
        logger.error(f"Neo4j error: {e}")
        return f"Error saving pattern: {str(e)}"
    finally:
        if driver:
            driver.close()
