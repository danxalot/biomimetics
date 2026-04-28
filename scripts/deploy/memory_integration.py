"""
Memory Integration: Firebase + Qdrant + Obsidian + memU
Comprehensive memory system for ARCA.
"""

import os
import asyncio
import json
import hashlib
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import aiohttp
import hashlib
import firebase_admin
from firebase_admin import credentials, storage, firestore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


class MemoryBackend(Enum):
    QDRANT = "qdrant"
    FIREBASE = "firebase"
    OBSIDIAN = "obsidian"
    MEMU = "memu"


@dataclass
class MemoryEntry:
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)


class LocalEmbeddingClient:
    """Calls local llama.cpp embedding server (e.g. Qwen3-VL on port 8081)"""

    def __init__(self, url: str = "http://localhost:8081", dims: int = 1024):
        self.url = url.rstrip("/")
        self.dims = dims
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def generate_embedding(self, text: str) -> List[float]:
        """POST to /embedding (llama.cpp endpoint) and truncate to target dims"""
        import math

        session = await self._get_session()
        payload = {"content": text}
        async with session.post(f"{self.url}/embedding", json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise Exception(f"Embedding server error {resp.status}: {body}")
            data = await resp.json()
            embedding = data[0]["embedding"]
            if isinstance(embedding[0], list):
                embedding = embedding[0]
            if len(embedding) > self.dims:
                embedding = embedding[: self.dims]
            norm = math.sqrt(sum(x * x for x in embedding))
            if norm > 0:
                embedding = [x / norm for x in embedding]
            return embedding

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class GeminiEmbeddingClient:
    """
    Calls Google Gemini Embeddings API (gemini-embedding-2-preview) for 1536-dim omnimodal embeddings.
    Uses HTTP requests with certifi for SSL verification.

    Rate Limits:
        - 100 requests per minute (RPM)
        - 30 tokens per minute (TPM) - per request limit
        - 1,000 tokens per day (TPD)

    Model: gemini-embedding-2-preview (1536 dimensions, omnimodal)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-2-preview",
        dims: int = 1536,
        output_dimensionality: Optional[int] = None,
        rpm: int = 100,
        tpm: int = 30,
        tpd: int = 1000,
    ):
        self.api_key = api_key
        self.model = model
        self.dims = output_dimensionality or dims
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self._session: Optional[aiohttp.ClientSession] = None

        # Rate limiter for embeddings
        self._rate_limiter = RateLimiter(
            rpm=rpm,
            tpm=tpm,
            tpd=tpd,
            context_limit=8192,
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            import ssl
            ssl_context = ssl.create_default_context()
            self._session = aiohttp.ClientSession()
        return self._session

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using Gemini Embeddings API with rate limiting"""
        import math

        # Estimate tokens
        estimated_tokens = max(1, len(text) // 4)

        # Apply rate limiting
        await self._rate_limiter.acquire(estimated_tokens)

        session = await self._get_session()

        # Build request payload for Gemini Embeddings API
        # Format: https://ai.google.dev/api/embeddings#embedContent
        payload = {
            "model": f"models/{self.model}",
            "content": {
                "parts": [{"text": text}]
            }
        }

        # Always request 1536 dimensions for compatibility with Qdrant
        payload["outputDimensionality"] = 1536

        # Use correct API endpoint format with API key
        url = f"{self.base_url}/models/{self.model}:embedContent?key={self.api_key}"

        # Use SSL verification
        import ssl
        ssl_context = ssl.create_default_context()

        async with session.post(url, json=payload, ssl=ssl_context) as resp:
            if resp.status != 200:
                body = await resp.text()
                if resp.status == 429:
                    raise Exception(f"Gemini Embedding rate limit exceeded. {body}")
                raise Exception(f"Gemini Embedding API error {resp.status}: {body}")

            data = await resp.json()
            embedding = data.get("embedding", {}).get("values", [])

            if not embedding:
                raise Exception("No embedding returned from Gemini API")

            # Normalize the embedding (COSINE distance requires normalized vectors)
            norm = math.sqrt(sum(x * x for x in embedding))
            if norm > 0:
                embedding = [x / norm for x in embedding]

            return embedding

    async def generate_batch_embeddings(
        self, texts: List[str], batch_size: int = 5
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts in batches with rate limiting"""
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            session = await self._get_session()
            
            payload = {
                "requests": [
                    {
                        "model": f"models/{self.model}",
                        "content": {"parts": [{"text": text}]},
                    }
                    for text in batch
                ]
            }
            
            url = f"{self.base_url}/models/{self.model}:batchEmbedContents?key={self.api_key}"
            
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    
                    if resp.status == 429:
                        raise Exception(f"Gemini Embedding rate limit exceeded. {body}")
                    
                    raise Exception(f"Gemini Embedding API error {resp.status}: {body}")
                
                data = await resp.json()
                batch_embeddings = [
                    emb.get("values", []) for emb in data.get("embeddings", [])
                ]
                
                # Normalize each embedding
                for emb in batch_embeddings:
                    norm = math.sqrt(sum(x * x for x in emb))
                    if norm > 0:
                        emb = [x / norm for x in emb]
                    embeddings.append(emb)
        
        return embeddings

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class QdrantMemory:
    """Qdrant vector store for semantic memory"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection: str = "arca_memory",
        vector_size: int = 1024,
    ):
        self.host = host
        self.port = port
        self.collection = collection
        self.vector_size = vector_size
        self.client: Optional[QdrantClient] = None
        self._initialized = False

    async def initialize(self):
        """Initialize Qdrant connection and ensure collection exists"""
        if self._initialized:
            return

        url = None
        api_key = None
        
        # Determine root directory based on the file location, assume ARCA root
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        # If in ARCA/services/openclaw_integration/memory_integration.py then 
        # dirname refers to ARCA/services/openclaw_integration, ARCA/services, ARCA.
        # Oh wait, __file__ could be a symlink or we can search dynamically.
        # Better: use current working directory or hardcoded fallback.
        secrets_dir = os.path.join(os.getcwd(), ".secrets")
        if not os.path.exists(secrets_dir):
             secrets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".secrets")

        qdrant_url_file = os.path.join(secrets_dir, "qdrant_endpoint_claws")
        qdrant_key_file = os.path.join(secrets_dir, "qdrant_api_key")

        if os.path.exists(qdrant_url_file):
            with open(qdrant_url_file, "r") as f:
                url = f.read().strip()
                
        if os.path.exists(qdrant_key_file):
            with open(qdrant_key_file, "r") as f:
                api_key = f.read().strip()

        if url and api_key:
            self.client = QdrantClient(url=url, api_key=api_key)
        else:
            self.client = QdrantClient(host=self.host, port=self.port)

        # Create collection if not exists
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection for c in collections):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
            )
            print(
                f"Created Qdrant collection '{self.collection}' with {self.vector_size} dims"
            )
        else:
            print(f"Qdrant collection '{self.collection}' already exists")

        self._initialized = True

    async def store(self, entry: MemoryEntry):
        """Store memory entry in Qdrant"""
        if not self._initialized:
            await self.initialize()

        if not entry.embedding:
            raise ValueError("Embedding required for vector storage")

        point = PointStruct(
            id=entry.id,
            vector=entry.embedding,
            payload={
                "content": entry.content,
                "metadata": entry.metadata,
                "created_at": entry.created_at.isoformat(),
                "tags": entry.tags,
            },
        )

        self.client.upsert(collection_name=self.collection, points=[point])

    async def query_points(
        self,
        query_embedding: List[float],
        limit: int = 5,
        filter_tags: Optional[List[str]] = None,
    ) -> List[MemoryEntry]:
        """Search memory by semantic similarity"""
        if not self._initialized:
            await self.initialize()

        search_params = {
            "collection_name": self.collection,
            "query": query_embedding,
            "limit": limit,
        }

        # Add filter if tags provided
        if filter_tags:
            search_params["query_filter"] = {
                "must": [{"key": "tags", "match": {"any": filter_tags}}]
            }

        # Use query_points for qdrant-client 1.x API
        results = self.client.query_points(**search_params)

        entries = []
        for result in results.points:
            created_at_str = result.payload.get("created_at")
            try:
                created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now()
            except Exception:
                created_at = datetime.now()
            
            entries.append(
                MemoryEntry(
                    id=result.id,
                    content=result.payload["content"],
                    metadata=result.payload.get("metadata", {}),
                    embedding=query_embedding,
                    tags=result.payload.get("tags", []),
                    created_at=created_at,
                )
            )

        return entries


class FirebaseMemory:
    """Firebase Firestore for structured memory storage"""

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or os.environ.get("FIREBASE_PROJECT_ID")
        self.cred: Optional[credentials.Certificate] = None
        self.app = None
        self.db = None
        self.bucket = None

    def initialize(self, credentials_path: Optional[str] = None):
        """Initialize Firebase connection"""
        if self.app:
            return

        cred_path = credentials_path or os.environ.get("FIREBASE_CREDENTIALS_PATH")

        if not cred_path or not os.path.exists(cred_path):
            secrets_dir = os.path.join(os.getcwd(), ".secrets")
            if not os.path.exists(secrets_dir):
                 secrets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".secrets")
            fallback_cred = os.path.join(secrets_dir, "gcp_credentials.json")
            if os.path.exists(fallback_cred):
                cred_path = fallback_cred

        if cred_path and os.path.exists(cred_path):
            self.cred = credentials.Certificate(cred_path)
        else:
            # Use default credentials
            self.cred = credentials.ApplicationDefault()

        self.app = firebase_admin.initialize_app(
            self.cred, options={"projectId": self.project_id}
        )

        self.db = firestore.client()

        # Initialize storage bucket
        bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET")
        if bucket_name:
            self.bucket = storage.bucket(bucket_name)

    async def store(self, collection: str, entry: MemoryEntry):
        """Store memory entry in Firestore"""
        if not self.db:
            self.initialize()

        doc_ref = self.db.collection(collection).document(entry.id)
        doc_ref.set(
            {
                "content": entry.content,
                "metadata": entry.metadata,
                "tags": entry.tags,
                "created_at": firestore.SERVER_TIMESTAMP,
                "accessed_at": firestore.SERVER_TIMESTAMP,
            }
        )

    async def get(self, collection: str, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve memory entry from Firestore"""
        if not self.db:
            self.initialize()

        doc = self.db.collection(collection).document(entry_id).get()

        if not doc.exists:
            return None

        data = doc.to_dict()
        return MemoryEntry(
            id=doc.id,
            content=data["content"],
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )

    async def query(
        self, collection: str, filters: Dict[str, Any], limit: int = 10
    ) -> List[MemoryEntry]:
        """Query memory entries"""
        if not self.db:
            self.initialize()

        query = self.db.collection(collection)

        for key, value in filters.items():
            query = query.where(key, "==", value)

        docs = query.limit(limit).stream()

        entries = []
        for doc in docs:
            data = doc.to_dict()
            created_at = data.get("created_at")
            if hasattr(created_at, "timestamp"):
                created_at = datetime.fromtimestamp(created_at.timestamp())
            elif not isinstance(created_at, datetime):
                created_at = datetime.now()
                
            entries.append(
                MemoryEntry(
                    id=doc.id,
                    content=data["content"],
                    metadata=data.get("metadata", {}),
                    tags=data.get("tags", []),
                    created_at=created_at,
                )
            )

        return entries


class ObsidianMemory:
    """Obsidian vault integration via filesystem"""

    def __init__(self, vault_path: str):
        self.vault_path = vault_path

    def _get_note_path(self, note_id: str) -> str:
        """Get full path for a note"""
        safe_id = note_id.replace("/", "-").replace("\\", "-")
        return os.path.join(self.vault_path, f"{safe_id}.md")

    async def store(self, entry: MemoryEntry):
        """Store note in Obsidian vault"""
        note_path = self._get_note_path(entry.id)

        # Build frontmatter
        frontmatter = {
            "id": entry.id,
            "created": entry.created_at.isoformat(),
            "tags": entry.tags,
        }

        # Add metadata to frontmatter
        for key, value in entry.metadata.items():
            frontmatter[key] = value

        # Build content
        content = "---\n"
        content += json.dumps(frontmatter, indent=2)
        content += "\n---\n\n"
        content += entry.content

        # Write file
        os.makedirs(os.path.dirname(note_path), exist_ok=True)
        with open(note_path, "w") as f:
            f.write(content)

    async def get(self, note_id: str) -> Optional[MemoryEntry]:
        """Retrieve note from Obsidian vault"""
        note_path = self._get_note_path(note_id)

        if not os.path.exists(note_path):
            return None

        with open(note_path, "r") as f:
            content = f.read()

        # Parse frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = json.loads(parts[1])
                body = parts[2].strip()
            else:
                frontmatter = {}
                body = content
        else:
            frontmatter = {}
            body = content

        return MemoryEntry(
            id=frontmatter.get("id", note_id),
            content=body,
            metadata={
                k: v
                for k, v in frontmatter.items()
                if k not in ["id", "created", "tags"]
            },
            tags=frontmatter.get("tags", []),
        )

    async def search(self, query: str) -> List[MemoryEntry]:
        """Search notes by content"""
        results = []

        for filename in os.listdir(self.vault_path):
            if not filename.endswith(".md"):
                continue

            filepath = os.path.join(self.vault_path, filename)

            with open(filepath, "r") as f:
                content = f.read()

            if query.lower() in content.lower():
                entry = await self.get(filename[:-3])
                if entry:
                    results.append(entry)

        return results


class RateLimiter:
    """Token bucket rate limiter for API calls"""
    
    def __init__(
        self,
        rpm: int = 60,        # Requests per minute
        tpm: int = 60000,     # Tokens per minute
        tpd: int = 1000000,   # Tokens per day
        context_limit: int = 131072,  # Max context window
    ):
        self.rpm = rpm
        self.tpm = tpm
        self.tpd = tpd
        self.context_limit = context_limit
        
        # Token bucket state
        self._request_tokens = rpm
        self._token_tokens = tpm
        self._daily_tokens = tpd
        self._last_request_time = datetime.now()
        self._last_token_time = datetime.now()
        self._daily_reset_date = datetime.now().date()
        
        self._lock = asyncio.Lock()
    
    async def acquire(self, estimated_tokens: int = 100) -> None:
        """Wait until rate limit allows the request"""
        async with self._lock:
            now = datetime.now()
            
            # Reset daily tokens if new day
            if now.date() > self._daily_reset_date:
                self._daily_tokens = self.tpd
                self._daily_reset_date = now.date()
            
            # Calculate token regeneration
            request_elapsed = (now - self._last_request_time).total_seconds()
            token_elapsed = (now - self._last_token_time).total_seconds()
            
            # Regenerate tokens (per second rates)
            self._request_tokens = min(self.rpm, self._request_tokens + (self.rpm / 60.0) * request_elapsed)
            self._token_tokens = min(self.tpm, self._token_tokens + (self.tpm / 60.0) * token_elapsed)
            
            self._last_request_time = now
            self._last_token_time = now
            
            # Check limits and wait if necessary
            while True:
                can_proceed = (
                    self._request_tokens >= 1 and
                    self._token_tokens >= estimated_tokens and
                    self._daily_tokens >= estimated_tokens
                )
                
                if can_proceed:
                    # Consume tokens
                    self._request_tokens -= 1
                    self._token_tokens -= estimated_tokens
                    self._daily_tokens -= estimated_tokens
                    break
                
                # Calculate wait time
                wait_times = []
                if self._request_tokens < 1:
                    wait_times.append(60.0 / self.rpm)  # Wait for 1 request token
                if self._token_tokens < estimated_tokens:
                    wait_times.append((estimated_tokens - self._token_tokens) / (self.tpm / 60.0))
                if self._daily_tokens < estimated_tokens:
                    wait_times.append(86400)  # Wait until next day
                
                wait_time = max(wait_times)
                await asyncio.sleep(wait_time)
                
                now = datetime.now()
                token_elapsed = (now - self._last_token_time).total_seconds()
                self._token_tokens = min(self.tpm, self._token_tokens + (self.tpm / 60.0) * token_elapsed)
                self._last_token_time = now


class AgentClient:
    """Agent integration for Gemma 3 via Google's v1beta endpoint with inline tool calls"""

    def __init__(
        self,
        api_key: str,
        provider: str = "gemini",
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        rpm: int = 30,           # 1 request every 2 seconds = 30 rpm
        tpm: int = 15000,        # 15k tokens per minute
        context_limit: int = 131072,  # 130k context window
    ):
        self.api_key = api_key
        self.provider = provider.lower()
        self.model = model or "gemma-3-12b-it"
        self.base_url = base_url or "https://generativelanguage.googleapis.com/v1beta"
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Rate limiter for Gemma 3
        self._rate_limiter = RateLimiter(
            rpm=rpm,
            tpm=tpm,
            context_limit=context_limit,
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _build_gemini_tools(self, tools: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        Build inline tool definitions for Gemma 3.
        Gemma 3 uses function_calling_config with inline tool definitions,
        not the separate function_calling_messages format.
        """
        if not tools:
            return None
        
        # Gemma 3 / Gemini format for tools
        return {
            "function_declarations": [
                {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "OBJECT", "properties": {}}),
                }
                for tool in tools
            ]
        }

    def _convert_messages_to_gemini_format(
        self, 
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Convert OpenAI-style messages to Gemini v1beta format.
        Gemma 3 expects user/model role alternation with inline tool definitions.
        """
        contents = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Map roles to Gemini format
            if role == "system":
                # System messages become the first user message prefix
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"System instruction: {content}"}]
                })
            elif role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": content}]
                })
            elif role == "assistant":
                contents.append({
                    "role": "model",
                    "parts": [{"text": content}]
                })
            elif role == "tool":
                # Tool responses become user messages with function results
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"Function result: {content}"}]
                })
        
        return contents

    async def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send completion request to Google's v1beta endpoint with inline tool support.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions for inline function calling
            tool_choice: 'auto', 'any', or 'none' (default: 'auto')
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
        """
        session = await self._get_session()
        
        # Estimate tokens for rate limiting (rough: 4 chars ≈ 1 token)
        total_text = sum(len(m.get("content", "")) for m in messages)
        estimated_tokens = max(100, total_text // 4)
        
        # Apply rate limiting
        await self._rate_limiter.acquire(estimated_tokens)
        
        url = f"{self.base_url}/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        
        # Convert messages to Gemini format
        contents = self._convert_messages_to_gemini_format(messages, tools)
        
        # Build generation config
        generation_config = {
            "temperature": kwargs.get("temperature", 0.7),
            "maxOutputTokens": min(kwargs.get("max_tokens", 8192), 8192),
            "topP": kwargs.get("top_p", 0.95),
            "topK": kwargs.get("top_k", 40),
        }
        
        # Build request payload
        payload = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        
        # Add inline tools if provided (Gemma 3 function calling)
        if tools:
            gemini_tools = self._build_gemini_tools(tools)
            payload["tools"] = [{"function_declarations": gemini_tools["function_declarations"]}]
            
            # Tool choice configuration
            if tool_choice == "any":
                payload["tool_config"] = {"function_calling_config": {"mode": "ANY"}}
            elif tool_choice == "none":
                payload["tool_config"] = {"function_calling_config": {"mode": "NONE"}}
            else:  # 'auto' or default
                payload["tool_config"] = {"function_calling_config": {"mode": "AUTO"}}
        
        # Make API request
        async with session.post(url, params=params, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                
                # Handle rate limit errors specifically
                if resp.status == 429:
                    raise Exception(f"Rate limit exceeded. Wait before retrying. {text}")
                
                raise Exception(f"Gemini API error {resp.status}: {text}")
            
            result = await resp.json()
            
            # Parse response
            try:
                candidate = result.get("candidates", [{}])[0]
                content = candidate.get("content", {})
                parts = content.get("parts", [])
                
                # Check for function calls
                function_calls = []
                text_parts = []
                
                for part in parts:
                    if "functionCall" in part:
                        function_calls.append(part["functionCall"])
                    elif "text" in part:
                        text_parts.append(part["text"])
                
                response_text = "\n".join(text_parts)
                
                return {
                    "text": response_text,
                    "function_calls": function_calls,
                    "raw": result,
                    "usage": {
                        "prompt_tokens": estimated_tokens,
                        "completion_tokens": len(response_text) // 4,
                        "total_tokens": estimated_tokens + (len(response_text) // 4),
                    }
                }
                
            except (KeyError, IndexError) as e:
                return {"text": "", "function_calls": [], "raw": result, "error": str(e)}

    async def complete_with_retry(
        self,
        messages: List[Dict[str, str]],
        max_retries: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """Complete with exponential backoff retry logic"""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self.complete(messages, **kwargs)
            except Exception as e:
                last_error = e
                
                # Don't retry on certain errors
                if "Rate limit" in str(e):
                    wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                elif "quota" in str(e).lower():
                    wait_time = (attempt + 1) * 5  # 5, 10, 15 seconds
                else:
                    wait_time = (attempt + 1) * 1  # 1, 2, 3 seconds
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
        
        raise Exception(f"Failed after {max_retries} retries: {last_error}")

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class UnifiedMemory:
    """Unified memory system combining all backends"""

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        obsidian_path: Optional[str] = None,
        firebase_project: Optional[str] = None,
        agent_api_key: Optional[str] = None,
        agent_provider: str = "gemini",
        agent_model: Optional[str] = None,
        embedding_url: Optional[str] = None,
        embedding_dims: int = 1024,
        gemini_api_key: Optional[str] = None,
        gemini_embedding_model: str = "text-embedding-004",
        use_gemini_embeddings: bool = False,
    ):
        self.qdrant = QdrantMemory(
            host=qdrant_host,
            port=qdrant_port,
            vector_size=embedding_dims,
        )
        self.firebase = FirebaseMemory(project_id=firebase_project)

        self.obsidian: Optional[ObsidianMemory] = None
        if obsidian_path:
            self.obsidian = ObsidianMemory(obsidian_path)

        # Gemini embeddings take priority if enabled
        self.embedder: Optional[LocalEmbeddingClient | GeminiEmbeddingClient] = None
        if use_gemini_embeddings and gemini_api_key:
            self.embedder = GeminiEmbeddingClient(
                api_key=gemini_api_key,
                model=gemini_embedding_model,
                dims=embedding_dims,
            )
            print(f"✅ Using Gemini Embeddings ({gemini_embedding_model}) at {embedding_dims} dims")
        elif embedding_url:
            self.embedder = LocalEmbeddingClient(url=embedding_url, dims=embedding_dims)
            print(f"✅ Using local embedding server at {embedding_url}")

        # Agent for model completions
        self.agent: Optional[AgentClient] = None
        if agent_api_key:
            self.agent = AgentClient(
                api_key=agent_api_key,
                provider=agent_provider,
                model=agent_model
            )

    async def initialize(self):
        """Initialize all backends"""
        await self.qdrant.initialize()
        self.firebase.initialize()

    async def store(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        backends: Optional[List[MemoryBackend]] = None,
        tags: Optional[List[str]] = None,
    ):
        """Store memory across specified backends"""

        # Deterministic UUID from content hash
        entry_id = str(uuid.UUID(hashlib.sha256(content.encode()).hexdigest()[:32]))

        entry = MemoryEntry(
            id=entry_id, content=content, metadata=metadata or {}, tags=tags or []
        )

        # Generate embedding
        if self.embedder:
            try:
                entry.embedding = await self.embedder.generate_embedding(content)
            except Exception as e:
                print(f"Warning: Failed to generate embedding: {e}")

        # Default to all backends
        if backends is None:
            backends = [MemoryBackend.QDRANT, MemoryBackend.FIREBASE]

        tasks = []

        if MemoryBackend.QDRANT in backends and entry.embedding:
            tasks.append(self.qdrant.store(entry))

        if MemoryBackend.FIREBASE in backends:
            tasks.append(self.firebase.store("memories", entry))

        if MemoryBackend.OBSIDIAN in backends and self.obsidian:
            tasks.append(self.obsidian.store(entry))

        if tasks:
            await asyncio.gather(*tasks)

    async def recall(
        self, query: str, backends: Optional[List[MemoryBackend]] = None, limit: int = 5,
        filter_tags: Optional[List[str]] = None
    ) -> List[MemoryEntry]:
        """Recall memory from backends"""

        results = []

        if backends is None:
            backends = [
                MemoryBackend.QDRANT,
                MemoryBackend.FIREBASE,
                MemoryBackend.OBSIDIAN,
            ]

        # Search vector store
        if MemoryBackend.QDRANT in backends and self.embedder:
            try:
                query_embedding = await self.embedder.generate_embedding(query)
                vector_results = await self.qdrant.query_points(
                    query_embedding=query_embedding,
                    limit=limit,
                    filter_tags=filter_tags
                )
                results.extend(vector_results)
            except Exception as e:
                print(f"Warning: Vector search failed: {e}")

        # Search Firebase
        if MemoryBackend.FIREBASE in backends:
            try:
                fb_results = await self.firebase.query(
                    "memories",
                    filters={},
                    limit=limit,
                )
                results.extend(fb_results)
            except Exception as e:
                print(f"Warning: Firebase search failed: {e}")

        # Search Obsidian
        if MemoryBackend.OBSIDIAN in backends and self.obsidian:
            try:
                obsidian_results = await self.obsidian.search(query)
                results.extend(obsidian_results)
            except Exception as e:
                print(f"Warning: Obsidian search failed: {e}")

        # Deduplicate
        seen = set()
        unique_results = []
        for entry in results:
            if entry.id not in seen:
                seen.add(entry.id)
                unique_results.append(entry)

        return unique_results[:limit]
