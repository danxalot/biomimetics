"""
Three-Tier Memory System Implementation
Implements working memory, episodic memory (vector DB), and structural memory (Neo4j graph)
"""

import asyncio
import json
import uuid
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib

import aiosqlite
import numpy as np
try:
    from sentence_transformers import SentenceTransformer
except Exception:
    # Compatibility fallback when sentence-transformers / huggingface_hub are incompatible or not available.
    # Provide a lightweight deterministic stub so the service can start and basic workflows can run.
    SentenceTransformer = None
    class _DummySentenceTransformer:
        def __init__(self, *args, **kwargs):
            pass
        def encode(self, texts, convert_to_numpy=True):
            # Deterministic, small embedding based on sha256 digest (not semantically meaningful)
            if isinstance(texts, str):
                texts = [texts]
            import hashlib
            import numpy as _np
            vectors = []
            for t in texts:
                h = hashlib.sha256(t.encode('utf-8')).digest()
                # Use the raw bytes as uint8 then cast to float32 and normalize
                arr = _np.frombuffer(h, dtype=_np.uint8).astype(_np.float32)
                arr = arr / 255.0
                vectors.append(arr)
            result = _np.vstack(vectors)
            return result if convert_to_numpy else result.tolist()
    SentenceTransformer = _DummySentenceTransformer
from neo4j import AsyncGraphDatabase
import logging

# Import ReasoningBank for agent learning
try:
    from .langgraph_agent import ReasoningBankFramework, ReasoningTrajectory
except ImportError:
    # Fallback for when langgraph_agent is not available
    ReasoningBankFramework = None
    ReasoningTrajectory = None

logger = logging.getLogger(__name__)


@dataclass
class MemoryItem:
    """Base class for memory items across all tiers"""
    id: str
    content: str
    timestamp: datetime
    source: str
    metadata: Dict[str, Any]


@dataclass
class ConversationMemory(MemoryItem):
    """Working memory item for conversation context"""
    session_id: str
    user_id: str
    message_type: str  # 'user' or 'assistant'
    summary: Optional[str] = None


@dataclass
class EpisodicMemory(MemoryItem):
    """Episodic memory item with vector embedding"""
    embedding: np.ndarray
    similarity_threshold: float = 0.7
    document_type: str = "conversation"
    chunk_index: int = 0


@dataclass
class StructuralMemory(MemoryItem):
    """Structural memory item for knowledge graph"""
    entity_type: str
    relationships: List[Dict[str, Any]]
    properties: Dict[str, Any]


class WorkingMemoryManager:
    """
    Layer 1: Working Memory (Conversation Summarization)
    Manages short-term conversational context with dynamic summarization
    """
    
    def __init__(self, db_path: str = "/tmp/working_memory.db", max_context_tokens: int = 4000):
        self.db_path = db_path
        self.max_context_tokens = max_context_tokens
        self.token_estimate_ratio = 4  # Rough tokens per character
        
    async def initialize(self):
        """Initialize working memory database"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    summary TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_timestamp 
                ON conversations(session_id, timestamp DESC)
            """)
            
            await db.commit()
    
    async def add_message(self, session_id: str, user_id: str, message_type: str, 
                         content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add new message to working memory"""
        try:
            message_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO conversations 
                    (id, session_id, user_id, message_type, content, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    message_id, session_id, user_id, message_type, 
                    content, timestamp, json.dumps(metadata or {})
                ))
                await db.commit()
            
            # Check if summarization is needed
            await self._check_and_summarize(session_id)
            
            logger.info(f"Added message to working memory: {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Error adding message to working memory: {e}")
            raise
    
    async def get_conversation_context(self, session_id: str, max_messages: int = 20) -> List[Dict[str, Any]]:
        """Retrieve conversation context with automatic summarization"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Get recent messages
                cursor = await db.execute("""
                    SELECT id, message_type, content, timestamp, summary, metadata
                    FROM conversations 
                    WHERE session_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (session_id, max_messages))
                
                rows = await cursor.fetchall()
                
                messages = []
                for row in rows:
                    messages.append({
                        "id": row[0],
                        "type": row[1],
                        "content": row[2],
                        "timestamp": row[3],
                        "summary": row[4],
                        "metadata": json.loads(row[5] or "{}")
                    })
                
                # Reverse to get chronological order
                messages.reverse()
                
                # Apply summarization if context is too long
                optimized_context = await self._optimize_context_length(messages)
                
                return optimized_context
                
        except Exception as e:
            logger.error(f"Error retrieving conversation context: {e}")
            return []
    
    async def _check_and_summarize(self, session_id: str):
        """Check if conversation needs summarization and perform it"""
        try:
            context = await self.get_conversation_context(session_id, max_messages=50)
            
            # Estimate token count
            total_chars = sum(len(msg["content"]) for msg in context)
            estimated_tokens = total_chars // self.token_estimate_ratio
            
            if estimated_tokens > self.max_context_tokens:
                await self._summarize_old_messages(session_id, context)
                
        except Exception as e:
            logger.error(f"Error in summarization check: {e}")
    
    async def _optimize_context_length(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Optimize context length through summarization"""
        if not messages:
            return messages
        
        # Calculate current length
        total_chars = sum(len(msg["content"]) for msg in messages)
        estimated_tokens = total_chars // self.token_estimate_ratio
        
        if estimated_tokens <= self.max_context_tokens:
            return messages
        
        # Keep recent messages, summarize older ones
        recent_messages = messages[-10:]  # Keep last 10 messages
        older_messages = messages[:-10]
        
        if older_messages:
            summary = await self._generate_summary(older_messages)
            
            summary_message = {
                "id": "summary_" + str(uuid.uuid4()),
                "type": "system",
                "content": f"[Conversation Summary]: {summary}",
                "timestamp": older_messages[0]["timestamp"],
                "summary": None,
                "metadata": {"type": "auto_summary", "message_count": len(older_messages)}
            }
            
            return [summary_message] + recent_messages
        
        return messages
    
    async def _summarize_old_messages(self, session_id: str, messages: List[Dict[str, Any]]):
        """Summarize and store old messages"""
        try:
            if len(messages) <= 10:
                return
            
            # Messages to summarize (older ones)
            to_summarize = messages[:-5]  # Keep last 5 messages unsummarized
            
            summary = await self._generate_summary(to_summarize)
            
            # Update oldest message with summary
            oldest_id = to_summarize[0]["id"]
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE conversations 
                    SET summary = ?, content = ?
                    WHERE id = ?
                """, (summary, f"[Summary of {len(to_summarize)} messages]: {summary}", oldest_id))
                
                # Delete other summarized messages except the one with summary
                ids_to_delete = [msg["id"] for msg in to_summarize[1:]]
                if ids_to_delete:
                    placeholders = ",".join(["?" for _ in ids_to_delete])
                    await db.execute(f"""
                        DELETE FROM conversations 
                        WHERE id IN ({placeholders})
                    """, ids_to_delete)
                
                await db.commit()
            
            logger.info(f"Summarized {len(to_summarize)} messages for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error summarizing old messages: {e}")
    
    async def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Generate summary of message list"""
        try:
            # Simple extractive summary - in production, use LLM
            content_parts = []
            for msg in messages:
                if msg["type"] == "user":
                    content_parts.append(f"User: {msg['content'][:100]}...")
                elif msg["type"] == "assistant":
                    content_parts.append(f"Assistant: {msg['content'][:100]}...")
            
            summary = " | ".join(content_parts)
            return summary[:500] + "..." if len(summary) > 500 else summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Summary generation failed"


class EpisodicMemoryManager:
    """
    Layer 2: Episodic Memory (Vector Database)
    Manages long-term memory with semantic similarity search
    """
    
    def __init__(self, db_path: str = "/tmp/episodic_memory.db", 
                 model_name: str = "all-MiniLM-L6-v2"):
        self.db_path = db_path
        self.embedding_model = SentenceTransformer(model_name)
        self.embedding_dim = 384  # MiniLM-L6-v2 dimension
        
    async def initialize(self):
        """Initialize episodic memory database"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    chunk_index INTEGER DEFAULT 0,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_document_type 
                ON episodic_memories(document_type, timestamp DESC)
            """)
            
            await db.commit()
    
    async def add_memory(self, content: str, source: str, document_type: str = "conversation",
                        metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add new memory with embedding"""
        try:
            memory_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # Generate embedding
            embedding = self.embedding_model.encode(content)
            embedding_blob = embedding.astype(np.float32).tobytes()
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO episodic_memories 
                    (id, content, embedding, timestamp, source, document_type, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    memory_id, content, embedding_blob, timestamp, 
                    source, document_type, json.dumps(metadata or {})
                ))
                await db.commit()
            
            logger.info(f"Added episodic memory: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"Error adding episodic memory: {e}")
            raise
    
    async def search_similar_memories(self, query: str, top_k: int = 5, 
                                    similarity_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search for semantically similar memories"""
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode(query)
            
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT id, content, embedding, timestamp, source, document_type, metadata
                    FROM episodic_memories
                    ORDER BY timestamp DESC
                """)
                
                rows = await cursor.fetchall()
                
                similar_memories = []
                for row in rows:
                    # Deserialize embedding
                    stored_embedding = np.frombuffer(row[2], dtype=np.float32)
                    
                    # Calculate cosine similarity
                    similarity = self._cosine_similarity(query_embedding, stored_embedding)
                    
                    if similarity >= similarity_threshold:
                        similar_memories.append({
                            "id": row[0],
                            "content": row[1],
                            "timestamp": row[3],
                            "source": row[4],
                            "document_type": row[5],
                            "metadata": json.loads(row[6] or "{}"),
                            "similarity": float(similarity)
                        })
                
                # Sort by similarity and return top_k
                similar_memories.sort(key=lambda x: x["similarity"], reverse=True)
                return similar_memories[:top_k]
                
        except Exception as e:
            logger.error(f"Error searching similar memories: {e}")
            return []
    
    async def add_document_chunks(self, document_content: str, source: str, 
                                 document_type: str = "document", chunk_size: int = 1000) -> List[str]:
        """Add document as chunked memories for RAG"""
        try:
            chunks = self._split_into_chunks(document_content, chunk_size)
            memory_ids = []
            
            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:  # Skip very small chunks
                    continue
                    
                metadata = {
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "chunk_size": len(chunk)
                }
                
                memory_id = await self.add_memory(
                    content=chunk,
                    source=source,
                    document_type=document_type,
                    metadata=metadata
                )
                memory_ids.append(memory_id)
            
            logger.info(f"Added {len(memory_ids)} chunks from document: {source}")
            return memory_ids
            
        except Exception as e:
            logger.error(f"Error adding document chunks: {e}")
            return []
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors"""
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    def _split_into_chunks(self, text: str, chunk_size: int) -> List[str]:
        """Split text into chunks for processing"""
        chunks = []
        sentences = text.split('. ')
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence) < chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks


class StructuralMemoryManager:
    """
    Layer 3: Structural Memory (Neo4j Knowledge Graph)
    Manages relationships and structured knowledge
    """
    
    def __init__(self, uri: str = "bolt://localhost:7687", 
                 user: str = "neo4j", password: str = "password"):
        self.driver = None
        self.uri = uri
        self.user = user
        self.password = password
        
    async def initialize(self):
        """Initialize Neo4j connection and constraints"""
        try:
            self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))
            
            # Create constraints and indexes
            async with self.driver.session() as session:
                # Entity uniqueness constraint
                await session.run("""
                    CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
                    FOR (e:Entity) REQUIRE e.id IS UNIQUE
                """)
                
                # Memory item constraint
                await session.run("""
                    CREATE CONSTRAINT memory_id_unique IF NOT EXISTS
                    FOR (m:Memory) REQUIRE m.id IS UNIQUE
                """)
                
                # Create indexes
                await session.run("""
                    CREATE INDEX entity_type_index IF NOT EXISTS
                    FOR (e:Entity) ON (e.type)
                """)
                
            logger.info("Neo4j structural memory initialized")
            
        except Exception as e:
            logger.error(f"Error initializing Neo4j: {e}")
            # For development, continue without Neo4j
            self.driver = None
    
    async def add_entity(self, entity_id: str, entity_type: str, name: str, 
                        properties: Dict[str, Any]) -> bool:
        """Add or update entity in knowledge graph"""
        if not self.driver:
            logger.warning("Neo4j not available, skipping entity addition")
            return False
            
        try:
            async with self.driver.session() as session:
                await session.run("""
                    MERGE (e:Entity {id: $entity_id})
                    SET e.type = $entity_type,
                        e.name = $name,
                        e.created_at = datetime(),
                        e.updated_at = datetime()
                    SET e += $properties
                """, {
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "name": name,
                    "properties": properties
                })
                
            logger.info(f"Added/updated entity: {entity_id} ({entity_type})")
            return True
            
        except Exception as e:
            logger.error(f"Error adding entity: {e}")
            return False
    
    async def add_relationship(self, from_entity_id: str, to_entity_id: str, 
                              relationship_type: str, properties: Optional[Dict[str, Any]] = None) -> bool:
        """Add relationship between entities"""
        if not self.driver:
            logger.warning("Neo4j not available, skipping relationship addition")
            return False
            
        try:
            async with self.driver.session() as session:
                await session.run(f"""
                    MATCH (from:Entity {{id: $from_id}})
                    MATCH (to:Entity {{id: $to_id}})
                    MERGE (from)-[r:{relationship_type}]->(to)
                    SET r.created_at = datetime()
                    SET r += $properties
                """, {
                    "from_id": from_entity_id,
                    "to_id": to_entity_id,
                    "properties": properties or {}
                })
                
            logger.info(f"Added relationship: {from_entity_id} -{relationship_type}-> {to_entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding relationship: {e}")
            return False
    
    async def query_related_entities(self, entity_id: str, relationship_type: Optional[str] = None,
                                   max_depth: int = 2) -> List[Dict[str, Any]]:
        """Query entities related to given entity"""
        if not self.driver:
            return []
            
        try:
            async with self.driver.session() as session:
                if relationship_type:
                    query = f"""
                        MATCH (start:Entity {{id: $entity_id}})-[r:{relationship_type}*1..{max_depth}]-(related:Entity)
                        RETURN related, r
                        LIMIT 20
                    """
                else:
                    query = f"""
                        MATCH (start:Entity {{id: $entity_id}})-[r*1..{max_depth}]-(related:Entity)
                        RETURN related, r
                        LIMIT 20
                    """
                
                result = await session.run(query, {"entity_id": entity_id})
                
                related_entities = []
                async for record in result:
                    entity = record["related"]
                    relationships = record["r"]
                    
                    related_entities.append({
                        "entity": dict(entity),
                        "relationships": [dict(rel) for rel in relationships] if isinstance(relationships, list) else [dict(relationships)]
                    })
                
                return related_entities
                
        except Exception as e:
            logger.error(f"Error querying related entities: {e}")
            return []
    
    async def add_latent_association(self, from_entity_id: str, to_entity_id: str, 
                                   confidence: float, source: str = "reasoning_bank") -> bool:
        """Add latent association discovered through ReasoningBank"""
        if not self.driver:
            return False
            
        try:
            properties = {
                "confidence": confidence,
                "source": source,
                "discovered_at": datetime.now().isoformat()
            }
            
            return await self.add_relationship(
                from_entity_id, to_entity_id, "HAS_LATENT_ASSOCIATION", properties
            )
            
        except Exception as e:
            logger.error(f"Error adding latent association: {e}")
            return False
    
    async def extract_entities_from_text(self, text: str, source: str) -> List[str]:
        """Extract entities from text and add to graph (simplified implementation)"""
        if not self.driver:
            return []
            
        try:
            # Simple entity extraction - in production, use NER models
            # For now, just extract capitalized words as potential entities
            words = text.split()
            entities = []
            
            for word in words:
                cleaned_word = word.strip(".,!?\"'()[]{}:;")
                if (len(cleaned_word) > 2 and 
                    cleaned_word[0].isupper() and 
                    not cleaned_word.isupper() and
                    cleaned_word.isalpha()):
                    
                    entity_id = f"entity_{hashlib.md5(cleaned_word.lower().encode()).hexdigest()[:8]}"
                    
                    await self.add_entity(
                        entity_id=entity_id,
                        entity_type="CONCEPT",
                        name=cleaned_word,
                        properties={
                            "source": source,
                            "extraction_method": "simple_capitalization"
                        }
                    )
                    entities.append(entity_id)
            
            return entities
            
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return []
    
    async def close(self):
        """Close Neo4j connection"""
        if self.driver:
            await self.driver.close()


class UnifiedMemorySystem:
    """
    Unified interface for all three memory tiers plus ReasoningBank
    Orchestrates working memory, episodic memory, structural memory, and agent learning
    """
    
    def __init__(self, working_memory_db: str = "/tmp/working_memory.db",
                 episodic_memory_db: str = "/tmp/episodic_memory.db",
                 neo4j_uri: str = "bolt://localhost:7687",
                 neo4j_user: str = "neo4j",
                 neo4j_password: str = "password"):
        
        self.working_memory = WorkingMemoryManager(working_memory_db)
        self.episodic_memory = EpisodicMemoryManager(episodic_memory_db)
        self.structural_memory = StructuralMemoryManager(neo4j_uri, neo4j_user, neo4j_password)
        
        # Layer 4: ReasoningBank for agent learning
        self.reasoning_bank = ReasoningBankFramework() if ReasoningBankFramework else None
        
    async def initialize(self):
        """Initialize all memory systems"""
        await self.working_memory.initialize()
        await self.episodic_memory.initialize()
        await self.structural_memory.initialize()
        
        # Initialize ReasoningBank if available
        if self.reasoning_bank:
            logger.info("ReasoningBank initialized for agent learning")
        
        logger.info("Unified memory system initialized")
    
    async def add_conversation_turn(self, session_id: str, user_id: str, 
                                  user_message: str, assistant_response: str,
                                  metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add complete conversation turn to all appropriate memory layers"""
        try:
            results = {}
            
            # Layer 1: Working Memory
            user_msg_id = await self.working_memory.add_message(
                session_id, user_id, "user", user_message, metadata
            )
            assistant_msg_id = await self.working_memory.add_message(
                session_id, user_id, "assistant", assistant_response, metadata
            )
            results["working_memory"] = [user_msg_id, assistant_msg_id]
            
            # Layer 2: Episodic Memory (for long-term retrieval)
            conversation_text = f"User: {user_message}\nAssistant: {assistant_response}"
            episodic_id = await self.episodic_memory.add_memory(
                content=conversation_text,
                source=f"conversation_{session_id}",
                document_type="conversation",
                metadata={**(metadata or {}), "session_id": session_id, "user_id": user_id}
            )
            results["episodic_memory"] = episodic_id
            
            # Layer 3: Structural Memory (extract entities and relationships)
            user_entities = await self.structural_memory.extract_entities_from_text(
                user_message, f"user_message_{user_msg_id}"
            )
            assistant_entities = await self.structural_memory.extract_entities_from_text(
                assistant_response, f"assistant_message_{assistant_msg_id}"
            )
            
            # Create relationships between entities mentioned in the same conversation
            for user_entity in user_entities:
                for assistant_entity in assistant_entities:
                    await self.structural_memory.add_relationship(
                        user_entity, assistant_entity, "DISCUSSED_WITH",
                        {"conversation_id": session_id, "timestamp": datetime.now().isoformat()}
                    )
            
            results["structural_memory"] = {
                "user_entities": user_entities,
                "assistant_entities": assistant_entities
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Error adding conversation turn: {e}")
            return {"error": str(e)}
    
    async def get_comprehensive_context(self, session_id: str, query: str, 
                                      user_id: str = "default") -> Dict[str, Any]:
        """Get comprehensive context from all memory layers"""
        try:
            context = {}
            
            # Layer 1: Working Memory
            context["working_memory"] = await self.working_memory.get_conversation_context(session_id)
            
            # Layer 2: Episodic Memory
            context["episodic_memory"] = await self.episodic_memory.search_similar_memories(query, top_k=5)
            
            # Layer 3: Structural Memory
            # Extract entities from query and find related information
            query_entities = await self.structural_memory.extract_entities_from_text(query, f"query_{session_id}")
            
            structural_context = []
            for entity_id in query_entities:
                related = await self.structural_memory.query_related_entities(entity_id)
                structural_context.extend(related)
            
            context["structural_memory"] = {
                "query_entities": query_entities,
                "related_entities": structural_context
            }
            
            # Add metadata
            context["retrieval_metadata"] = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "query": query,
                "layers_queried": ["working_memory", "episodic_memory", "structural_memory"]
            }
            
            return context
            
        except Exception as e:
            logger.error(f"Error getting comprehensive context: {e}")
            return {"error": str(e)}
    
    async def add_document(self, document_content: str, source: str, 
                          document_type: str = "document") -> Dict[str, Any]:
        """Add document to episodic and structural memory"""
        try:
            results = {}
            
            # Add to episodic memory as chunks
            episodic_ids = await self.episodic_memory.add_document_chunks(
                document_content, source, document_type
            )
            results["episodic_chunks"] = len(episodic_ids)
            
            # Extract entities and add to structural memory
            entities = await self.structural_memory.extract_entities_from_text(
                document_content, source
            )
            results["extracted_entities"] = len(entities)
            
            # Create co-occurrence relationships between entities
            for i, entity1 in enumerate(entities):
                for entity2 in entities[i+1:]:
                    await self.structural_memory.add_relationship(
                        entity1, entity2, "CO_OCCURS_WITH",
                        {"source": source, "document_type": document_type}
                    )
            
            return results
            
        except Exception as e:
            logger.error(f"Error adding document: {e}")
            return {"error": str(e)}
    
    async def record_agent_trajectory(self, trajectory: ReasoningTrajectory) -> Dict[str, Any]:
        """Record agent execution trajectory for learning"""
        try:
            if not self.reasoning_bank:
                return {"error": "ReasoningBank not available"}
            
            results = {}
            
            # Judge the trajectory
            judgment = await self.reasoning_bank.judge_trajectory(trajectory)
            results["judgment"] = judgment
            
            # Distill memory items
            memory_items = await self.reasoning_bank.distill_memory_items(trajectory, judgment)
            results["memory_items"] = len(memory_items)
            
            # Consolidate into ReasoningBank
            consolidation_success = await self.reasoning_bank.consolidate_memory(memory_items)
            results["consolidation_success"] = consolidation_success
            
            # Store trajectory in episodic memory for long-term analysis
            trajectory_content = f"""
            Agent Trajectory Analysis:
            Task: {trajectory.initial_state.get('task_input', 'Unknown')}
            Actions: {json.dumps(trajectory.actions_taken, indent=2)}
            Outcome: {trajectory.outcome}
            Execution Time: {trajectory.execution_time}s
            Success Score: {judgment.get('success_score', 0.0)}
            Lessons: {json.dumps(judgment.get('lessons_learned', []), indent=2)}
            """
            
            episodic_id = await self.episodic_memory.add_memory(
                content=trajectory_content,
                source=f"agent_trajectory_{trajectory.agent_id}",
                document_type="agent_learning",
                metadata={
                    "agent_id": trajectory.agent_id,
                    "task_type": trajectory.initial_state.get('task_type'),
                    "success_score": judgment.get('success_score', 0.0),
                    "execution_time": trajectory.execution_time,
                    "judgment": judgment
                }
            )
            results["episodic_memory_id"] = episodic_id
            
            # Extract entities from trajectory and add to structural memory
            trajectory_text = f"{trajectory.initial_state.get('task_input', '')} {' '.join(trajectory.actions_taken)}"
            entities = await self.structural_memory.extract_entities_from_text(
                trajectory_text, f"trajectory_{trajectory.agent_id}"
            )
            results["extracted_entities"] = len(entities)
            
            logger.info(f"Recorded agent trajectory for learning: {trajectory.agent_id}")
            return results
            
        except Exception as e:
            logger.error(f"Error recording agent trajectory: {e}")
            return {"error": str(e)}
    
    async def get_reasoning_strategies(self, task_context: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant reasoning strategies from ReasoningBank"""
        try:
            if not self.reasoning_bank:
                return []
            
            strategies = await self.reasoning_bank.retrieve_relevant_strategies(task_context, top_k)
            
            # Also search episodic memory for similar past trajectories
            similar_trajectories = await self.episodic_memory.search_similar_memories(
                task_context, top_k=3, similarity_threshold=0.6
            )
            
            # Combine and deduplicate
            combined_strategies = []
            strategy_titles = set()
            
            # Add ReasoningBank strategies
            for strategy in strategies:
                if strategy.get('title') not in strategy_titles:
                    combined_strategies.append(strategy)
                    strategy_titles.add(strategy.get('title'))
            
            # Add trajectory-based strategies
            for trajectory in similar_trajectories:
                trajectory_strategy = {
                    "type": "trajectory_pattern",
                    "title": f"Past trajectory: {trajectory.get('content', '')[:100]}...",
                    "description": f"Similar past execution with {trajectory.get('similarity', 0):.2f} relevance",
                    "content": trajectory,
                    "confidence": trajectory.get('similarity', 0.0),
                    "source": "episodic_memory"
                }
                if trajectory_strategy['title'] not in strategy_titles:
                    combined_strategies.append(trajectory_strategy)
                    strategy_titles.add(trajectory_strategy['title'])
            
            return combined_strategies[:top_k]
            
        except Exception as e:
            logger.error(f"Error retrieving reasoning strategies: {e}")
            return []
    
    async def get_agent_learning_context(self, agent_id: str, task_context: str) -> Dict[str, Any]:
        """Get comprehensive learning context for an agent"""
        try:
            context = {}
            
            # Get reasoning strategies
            context["reasoning_strategies"] = await self.get_reasoning_strategies(task_context)
            
            # Get similar past trajectories for this agent
            agent_trajectories = await self.episodic_memory.search_similar_memories(
                f"agent_{agent_id} {task_context}", top_k=5
            )
            context["agent_history"] = agent_trajectories
            
            # Get related entities from structural memory
            query_entities = await self.structural_memory.extract_entities_from_text(
                task_context, f"learning_query_{agent_id}"
            )
            
            structural_context = []
            for entity_id in query_entities:
                related = await self.structural_memory.query_related_entities(entity_id, max_depth=1)
                structural_context.extend(related)
            
            context["structural_insights"] = {
                "query_entities": query_entities,
                "related_entities": structural_context
            }
            
            # Add metadata
            context["learning_metadata"] = {
                "agent_id": agent_id,
                "task_context": task_context,
                "timestamp": datetime.now().isoformat(),
                "reasoning_bank_available": self.reasoning_bank is not None
            }
            
            return context
            
        except Exception as e:
            logger.error(f"Error getting agent learning context: {e}")
            return {"error": str(e)}
    
    async def close(self):
        """Close all memory systems"""
        await self.structural_memory.close()
        logger.info("Unified memory system closed")