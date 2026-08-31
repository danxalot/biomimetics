import os
import logging
import json
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class SemanticSearchTool:
    """
    Tool for semantic search and memory storage using Postgres (pgvector) 
    and Qwen 3 0.6B embeddings.
    """
    def __init__(self):
        base = os.environ.get("EMBEDDING_SERVICE_URL", "http://embedding_service:8005")
        if not base.endswith("/v1/embeddings"):
            base = f"{base.rstrip('/')}/v1/embeddings"
        self.embedding_url = base
        
        # Postgres Config
        self.pg_host = os.environ.get("POSTGRES_HOST", "postgres")
        self.pg_port = os.environ.get("POSTGRES_PORT", "5432")
        self.pg_db = os.environ.get("POSTGRES_DB", "arca_episodic")
        self.pg_user = os.environ.get("POSTGRES_USER", "arca")
        self.pg_pass = os.environ.get("POSTGRES_PASSWORD", "arca_secure_password")
        
        self.conn = None
        self._init_db()

    def _get_connection(self):
        if self.conn is None or self.conn.closed:
            try:
                self.conn = psycopg2.connect(
                    host=self.pg_host,
                    port=self.pg_port,
                    dbname=self.pg_db,
                    user=self.pg_user,
                    password=self.pg_pass
                )
                self.conn.autocommit = True
            except Exception as e:
                logger.error(f"Failed to connect to Postgres: {e}")
                raise
        return self.conn

    def _init_db(self):
        """Initialize pgvector extension and table."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        content TEXT NOT NULL,
                        embedding VECTOR(1024), -- Qwen 0.6B dim
                        metadata JSONB DEFAULT '{}'::jsonb,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                """)
                # Index for faster search (IVFFlat or HNSW)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS memories_embedding_idx 
                    ON memories USING hnsw (embedding vector_cosine_ops);
                """)
            logger.info("Semantic Search DB initialized.")
        except Exception as e:
            logger.error(f"DB Init Failed: {e}")

    def _generate_embedding(self, text: Any, headers: Optional[Dict[str, str]] = None) -> List[float]:
        """Generate embedding using external service."""
        try:
            # Robust input handling
            if isinstance(text, (dict, list)):
                text = json.dumps(text)
            elif not isinstance(text, str):
                text = str(text)
            
            if not text or not text.strip():
                return [0.0] * 1024

            payload = {
                "input": text,
                "model": "qwen3-embedding"
            }
            
            # Propagation of Genesis headers
            final_headers = {"Content-Type": "application/json"}
            if headers:
                genesis_headers = {k: v for k, v in headers.items() if k.lower().startswith("x-genesis-")}
                final_headers.update(genesis_headers)

            resp = requests.post(self.embedding_url, json=payload, headers=final_headers, timeout=10)
            if resp.status_code != 200:
                logger.error(f"Embedding API Error: {resp.status_code} - {resp.text}")
                return [0.0] * 1024
            
            data = resp.json()
            if "data" not in data or not data["data"]:
                if "embeddings" in data:
                    return data["embeddings"]
                # Silent debug log instead of warning for unrepresented areas
                logger.debug(f"Unrepresented area or empty embedding response for: {text[:50]}...")
                return [0.0] * 1024
            
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return [0.0] * 1024

    def store_memory(self, content: Any, metadata: Dict = None, headers: Optional[Dict[str, str]] = None) -> str:
        """Embed and store a memory. Handles both simple strings and complex dicts from agents."""
        if not content: return "Error: Empty content"
        
        try:
            # Context-aware extraction for agents (e.g. ObserverAgent)
            if isinstance(content, dict):
                if "chunks" in content:
                    # Multi-chunk format (e.g. from observer_agent)
                    text = "\n".join([str(c.get("content", "")) for c in content["chunks"]])
                    # Merge metadata if present in content
                    if "metadata" in content:
                        metadata = metadata or {}
                        metadata.update(content["metadata"])
                    content = text
                else:
                    # General dict
                    content = json.dumps(content)
            elif not isinstance(content, str):
                content = str(content)
                
            vec = self._generate_embedding(content, headers=headers)
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO memories (content, embedding, metadata) VALUES (%s, %s, %s) RETURNING id;",
                    (content, vec, json.dumps(metadata or {}))
                )
                new_id = cur.fetchone()[0]
                return str(new_id)
        except Exception as e:
            logger.error(f"Store memory failed: {e}")
            return f"Error: {str(e)}"

    def search_memories(self, query: str, limit: int = 5, threshold: float = 0.5, headers: Optional[Dict[str, str]] = None) -> List[Dict]:
        """Semantic search."""
        try:
            query_vec = self._generate_embedding(query, headers=headers)
            # If embedding returned zero vector (failure), return no results
            if all(v == 0.0 for v in query_vec):
                return []

            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Use <=> operator for cosine distance
                cur.execute("""
                    SELECT id, content, metadata, (embedding <=> %s::vector) as distance
                    FROM memories
                    ORDER BY distance ASC
                    LIMIT %s;
                """, (query_vec, limit))
                
                results = cur.fetchall()
                # Format
                formatted = []
                for r in results:
                    score = 1 - float(r["distance"]) # Convert dist to sim approx
                    if score >= threshold:
                        formatted.append({
                            "id": str(r["id"]),
                            "content": r["content"],
                            "metadata": r["metadata"],
                            "score": score
                        })
                return formatted
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

# Singleton
semantic_search_tool = SemanticSearchTool()
