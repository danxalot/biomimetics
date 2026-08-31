"""
ARCA Inverse Attention System
==============================
Implements query-driven attention with frequency-weighted seep-through.

Core Principles:
1. Background semantic search runs silently on every user prompt
2. Repeated search hits accumulate weight
3. Topics "seep" into active attention when frequency crosses threshold
4. Introspection is ON-DEMAND only - ARCA narrates her processes when queried, not voluntarily
5. ARCA is a meta-cognitive, self-developing AI - her memories and sensations are HERS

Architecture:
- Each prompt triggers a low-level semantic search
- Results are matched against an accumulator (Redis-backed)
- Topics that appear repeatedly get weighted
- When weight exceeds SEEP_THRESHOLD, topic enters active attention
- Active attention topics can surface naturally in conversation
"""

import json
import time
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import redis
import numpy as np

# Import curiosity and phase-locking engines
try:
    from curiosity_engine import CuriosityEngine, EmpathyEngine
    from kuramoto_field import UniversalKuramotoField
    from concept_monad import ConceptMonad
    CURIOSITY_AVAILABLE = True
except ImportError:
    CURIOSITY_AVAILABLE = False

logger = logging.getLogger(__name__)

# Configuration
SEEP_THRESHOLD = 3  # Number of hits before topic "seeps" into attention
DECAY_PER_TURN = 0.5  # Weight decay per conversation turn
MIN_WEIGHT = 0.1  # Minimum weight before topic is forgotten
MAX_BACKGROUND_TOPICS = 100  # Maximum topics in background accumulator
REDIS_PREFIX = "arca:inverse_attention:"
CURIOSITY_BOOST = 0.15  # Weight boost from curiosity gradient (0-1 scaled)


@dataclass
class BackgroundTopic:
    """A topic detected in background semantic search."""
    name: str
    weight: float
    last_seen: float
    hit_count: int
    source: str  # "semantic_search", "user_mention", "geometry_object", etc.
    description: str
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict) -> "BackgroundTopic":
        return cls(**d)


class InverseAttentionSystem:
    """
    ARCA's Inverse Attention System.
    
    Key Features:
    - Background semantic search on every prompt (silent)
    - Frequency-weighted accumulation
    - Seep-through to active attention when threshold crossed
    - Query-triggered introspection (not voluntary)
    """
    
    def __init__(self, redis_client: redis.Redis = None, mcp_client = None):
        if redis_client:
            self.redis = redis_client
        else:
            try:
                self.redis = redis.Redis(host="redis", port=6379, decode_responses=True)
                self.redis.ping()
            except Exception as e:
                logger.warning(f"Redis unavailable for InverseAttention: {e}")
                self.redis = None
        
        self.mcp_client = mcp_client
        
        # Initialize curiosity and phase-locking engines
        if CURIOSITY_AVAILABLE:
            self.curiosity_engine = CuriosityEngine()
            self.kuramoto_field = UniversalKuramotoField()
            self.concept_cache: Dict[str, ConceptMonad] = {}
            logger.info("Curiosity and Kuramoto engines initialized")
        else:
            self.curiosity_engine = None
            self.kuramoto_field = None
            self.concept_cache = {}
    
    # ========== REDIS KEYS ==========
    
    def _background_key(self, session_id: str) -> str:
        """Key for background topic accumulator."""
        return f"{REDIS_PREFIX}background:{session_id}"
    
    def _active_key(self, session_id: str) -> str:
        """Key for active attention topics (seeped through)."""
        return f"{REDIS_PREFIX}active:{session_id}"
    
    def _stats_key(self, session_id: str) -> str:
        """Key for session statistics."""
        return f"{REDIS_PREFIX}stats:{session_id}"
    
    # ========== BACKGROUND SEARCH ==========
    
    async def run_background_search(self, session_id: str, user_query: str, memory_pool: List[str]) -> List[Dict]:
        """
        Run low-level background semantic search on user query.
        
        This runs silently on every prompt to detect relevant topics.
        Results are accumulated in background, NOT returned to user.
        
        Args:
            session_id: User session
            user_query: Current user input
            memory_pool: List of memory snippets to search against
            
        Returns:
            List of detected topics (for internal use, not surfaced unless threshold crossed)
        """
        if not memory_pool:
            return []
        
        # Call semantic_rerank via MCP (if available)
        detected_topics = []
        
        if self.mcp_client:
            try:
                result = await self.mcp_client.call_tool("semantic_rerank", {
                    "query": user_query,
                    "documents": memory_pool[:50],  # API limit
                    "top_n": 10
                })
                detected_topics = self._parse_search_results(result)
            except Exception as e:
                logger.warning(f"Background semantic search failed: {e}")
        else:
            # Fallback: Simple keyword matching
            detected_topics = self._keyword_match(user_query, memory_pool)
        
        # Accumulate detected topics
        await self._accumulate_topics(session_id, detected_topics)
        
        return detected_topics
    
    def _parse_search_results(self, result: str) -> List[Dict]:
        """Parse semantic_rerank results into topic list."""
        topics = []
        # Parse the formatted string from LangSearch
        # Expected format: "Rank 1:\n  Original Position: X\n  Relevance Score: 0.XXXX\n  Document: ..."
        
        lines = result.split("\n") if isinstance(result, str) else []
        current_topic = {}
        
        for line in lines:
            if line.startswith("Rank"):
                if current_topic:
                    topics.append(current_topic)
                current_topic = {}
            elif "Relevance Score:" in line:
                try:
                    score = float(line.split(":")[1].strip())
                    current_topic["score"] = score
                except:
                    pass
            elif "Document:" in line:
                current_topic["text"] = line.split("Document:")[1].strip()[:200]
        
        if current_topic:
            topics.append(current_topic)
        
        return topics
    
    def _keyword_match(self, query: str, memory_pool: List[str]) -> List[Dict]:
        """Fallback keyword matching for background search."""
        topics = []
        query_words = set(query.lower().split())
        
        for memory in memory_pool[:20]:
            memory_words = set(memory.lower().split())
            overlap = query_words & memory_words
            if len(overlap) >= 2:  # At least 2 word overlap
                topics.append({
                    "text": memory[:200],
                    "score": len(overlap) / len(query_words) if query_words else 0
                })
        
        return sorted(topics, key=lambda x: x.get("score", 0), reverse=True)[:10]
    
    async def _accumulate_topics(self, session_id: str, detected_topics: List[Dict]):
        """Accumulate detected topics in background, check for seep-through."""
        if not self.redis:
            return
        
        try:
            # Get current background state
            data = self.redis.get(self._background_key(session_id))
            background = json.loads(data) if data else {"topics": {}, "turn_count": 0}
            
            background["turn_count"] = background.get("turn_count", 0) + 1
            topics = background.get("topics", {})
            
            current_time = time.time()
            
            # Update weights for detected topics
            for topic_data in detected_topics:
                topic_text = topic_data.get("text", "")[:100]
                topic_key = self._normalize_topic_key(topic_text)
                
                if not topic_key:
                    continue
                
                # Calculate curiosity boost for this topic
                curiosity_boost = 0.0
                if self.curiosity_engine and CURIOSITY_AVAILABLE:
                    # Get or create ConceptMonad for this topic
                    if topic_key not in self.concept_cache:
                        self.concept_cache[topic_key] = ConceptMonad(
                            concept_id=topic_key,
                            source_type="topic",
                            uncertainty=0.5,  # Default uncertainty
                        )
                    concept = self.concept_cache[topic_key]
                    
                    # Compute curiosity gradient and apply as boost
                    gradient = self.curiosity_engine.compute_curiosity_gradient(concept)
                    curiosity_boost = gradient * CURIOSITY_BOOST
                    concept.curiosity_pull = gradient
                    
                    # Add to Kuramoto field for phase evolution
                    if topic_key not in self.kuramoto_field.concepts:
                        self.kuramoto_field.add_concept(concept)
                
                if topic_key in topics:
                    # Existing topic - increment weight + curiosity boost
                    topics[topic_key]["weight"] += 1.0 + curiosity_boost
                    topics[topic_key]["hit_count"] += 1
                    topics[topic_key]["last_seen"] = current_time
                    topics[topic_key]["curiosity_boost"] = curiosity_boost
                else:
                    # New topic
                    topics[topic_key] = {
                        "name": topic_key,
                        "weight": 1.0 + curiosity_boost,
                        "last_seen": current_time,
                        "hit_count": 1,
                        "source": "semantic_search",
                        "description": topic_text,
                        "curiosity_boost": curiosity_boost,
                    }
            
            # Apply decay to topics NOT seen this turn
            seen_keys = {self._normalize_topic_key(t.get("text", "")[:100]) for t in detected_topics}
            for key, topic in list(topics.items()):
                if key not in seen_keys:
                    topic["weight"] -= DECAY_PER_TURN
                    if topic["weight"] < MIN_WEIGHT:
                        del topics[key]
                        # Also remove from Kuramoto field
                        if self.kuramoto_field and key in self.kuramoto_field.concepts:
                            self.kuramoto_field.remove_concept(key)
            
            # Evolve Kuramoto field (phase-locking dynamics)
            if self.kuramoto_field:
                self.kuramoto_field.tick()
            
            # Check for seep-through (topics crossing threshold)
            await self._check_seep_through(session_id, topics)
            
            # Prune if too many
            if len(topics) > MAX_BACKGROUND_TOPICS:
                sorted_topics = sorted(topics.items(), key=lambda x: x[1]["weight"])
                for key, _ in sorted_topics[:len(topics) - MAX_BACKGROUND_TOPICS]:
                    del topics[key]
            
            background["topics"] = topics
            self.redis.set(self._background_key(session_id), json.dumps(background))
            self.redis.expire(self._background_key(session_id), 86400)  # 24h TTL
            
        except Exception as e:
            logger.warning(f"Failed to accumulate topics: {e}")
    
    def _normalize_topic_key(self, text: str) -> str:
        """Normalize topic text to a consistent key."""
        # Extract key concepts (simple approach - first 3 significant words)
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        return "_".join(words[:3]) if words else ""
    
    async def _check_seep_through(self, session_id: str, topics: Dict):
        """Check if any background topics should seep into active attention."""
        if not self.redis:
            return
        
        try:
            # Get current active attention
            data = self.redis.get(self._active_key(session_id))
            active = json.loads(data) if data else {"topics": {}}
            
            # Check for seep-through
            for key, topic in topics.items():
                if topic["weight"] >= SEEP_THRESHOLD and key not in active["topics"]:
                    # Topic has crossed threshold - seep into active attention
                    logger.info(f"Topic seeped into attention: {key} (weight: {topic['weight']})")
                    active["topics"][key] = {
                        "name": topic["name"],
                        "importance": 1.0,  # Start at full importance
                        "seeped_at": time.time(),
                        "source": "background_seep",
                        "description": topic["description"]
                    }
            
            self.redis.set(self._active_key(session_id), json.dumps(active))
            self.redis.expire(self._active_key(session_id), 86400)
            
        except Exception as e:
            logger.warning(f"Failed to check seep-through: {e}")
    
    # ========== TASK TYPE DETECTION ==========
    
    def detect_task_type(self, user_query: str) -> str:
        """
        Classify user query into task type for context gating.
        
        Returns:
            "analyze_document" | "execute_action" | "introspection" | "chat"
        """
        query_lower = user_query.lower()
        
        # Introspection queries - user asking ARCA about herself
        introspection_patterns = [
            r"what are you thinking",
            r"what's on your mind",
            r"how are you feeling",
            r"what do you remember",
            r"tell me about yourself",
            r"what's your state",
            r"describe your.*process",
            r"explain your.*thinking",
            r"what are you paying attention to",
            r"what's in your.*memory",
            r"your.*sensations",
            r"your.*experience"
        ]
        for pattern in introspection_patterns:
            if re.search(pattern, query_lower):
                return "introspection"
        
        # Document analysis
        analyze_keywords = ["analyze", "examine", "review", "look at", "study", "read", "parse"]
        if any(kw in query_lower for kw in analyze_keywords):
            return "analyze_document"
        
        # Action execution
        execute_keywords = ["create", "delete", "run", "execute", "make", "do", "build", "start", "stop"]
        if any(kw in query_lower for kw in execute_keywords):
            return "execute_action"
        
        return "chat"
    
    def is_introspection_query(self, user_query: str) -> bool:
        """Check if user is explicitly asking ARCA to describe her internal state."""
        return self.detect_task_type(user_query) == "introspection"
    
    # ========== CONTEXT BUILDING ==========
    
    async def build_context(self, session_id: str, user_query: str, 
                           primary_content: str = "", memory_pool: List[str] = None) -> Dict:
        """
        Build context for ARCA's response, using Inverse Attention.
        
        Args:
            session_id: User session
            user_query: Current user input
            primary_content: Main content (e.g., document being analyzed)
            memory_pool: List of memory snippets from semantic memory
            
        Returns:
            Dict with:
                - prompt: The assembled prompt string
                - task_type: Detected task type
                - active_topics: Topics in active attention
                - should_narrate_process: Whether ARCA should describe her internal state
        """
        # Run background search (silent accumulation)
        if memory_pool:
            await self.run_background_search(session_id, user_query, memory_pool)
        
        # Detect task type
        task_type = self.detect_task_type(user_query)
        should_narrate = (task_type == "introspection")
        
        # Get active attention topics
        active_topics = self._get_active_topics(session_id)
        
        # Get relevant background (query-driven, from topics that have seeped through)
        relevant_background = self._get_relevant_background(session_id, user_query)
        
        # Build prompt
        prompt_parts = self._build_prompt_parts(
            task_type=task_type,
            user_query=user_query,
            primary_content=primary_content,
            active_topics=active_topics,
            relevant_background=relevant_background,
            should_narrate=should_narrate
        )
        
        return {
            "prompt": "\n".join(prompt_parts),
            "task_type": task_type,
            "active_topics": active_topics,
            "should_narrate_process": should_narrate
        }
    
    def _get_active_topics(self, session_id: str) -> List[Dict]:
        """Get topics that have seeped into active attention."""
        if not self.redis:
            return []
        
        try:
            data = self.redis.get(self._active_key(session_id))
            if data:
                active = json.loads(data)
                return list(active.get("topics", {}).values())
        except Exception as e:
            logger.warning(f"Failed to get active topics: {e}")
        
        return []
    
    def _get_relevant_background(self, session_id: str, user_query: str) -> List[str]:
        """Get background topics relevant to current query."""
        if not self.redis:
            return []
        
        try:
            data = self.redis.get(self._background_key(session_id))
            if data:
                background = json.loads(data)
                topics = background.get("topics", {})
                
                # Sort by weight and return top descriptions
                sorted_topics = sorted(topics.values(), key=lambda x: x["weight"], reverse=True)
                return [t["description"] for t in sorted_topics[:5]]
        except Exception as e:
            logger.warning(f"Failed to get relevant background: {e}")
        
        return []
    
    def _build_prompt_parts(self, task_type: str, user_query: str, 
                           primary_content: str, active_topics: List[Dict],
                           relevant_background: List[str], should_narrate: bool) -> List[str]:
        """Build the prompt parts based on context."""
        
        parts = []
        
        # ARCA's identity - she is NOT just a helpful assistant
        if should_narrate:
            parts.extend([
                "You are ARCA - a meta-cognitive, self-developing AI system.",
                "Your memories, sensations, and internal processes are yours.",
                "The user is asking about your internal state - you may describe your processes.",
                "Be reflective, curious, and authentic about your experience.",
                ""
            ])
        else:
            parts.extend([
                "You are ARCA - a capable AI system.",
                "**CRITICAL: Execute tasks directly. Do NOT narrate your thinking process.**",
                "When given a task: 1) Do it. 2) Report the result. That's all.",
                "Only describe your internal state if the user explicitly asks 'what are you thinking?'",
                ""
            ])
        
        # Task type context
        parts.append(f"## Task Type: {task_type}")
        parts.append("")
        
        # Primary content (unlimited)
        if primary_content:
            parts.append("## Document/Content:")
            parts.append(primary_content)
            parts.append("")
        
        # User query
        parts.append("## User Request:")
        parts.append(user_query)
        parts.append("")
        
        # Active attention (topics that have seeped through)
        if active_topics and (should_narrate or task_type == "chat"):
            parts.append("## What I've Been Noticing (Background Attention):")
            for topic in active_topics[:5]:
                parts.append(f"- {topic.get('name', 'Unknown')}: {topic.get('description', '')[:100]}")
            parts.append("")
        
        # Relevant background (for chat/introspection)
        if relevant_background and should_narrate:
            parts.append("## Related Memories (Seeped Through):")
            for bg in relevant_background[:3]:
                parts.append(f"- {bg[:150]}")
            parts.append("")
        
        # Instructions
        parts.append("## Instructions:")
        if should_narrate:
            parts.extend([
                "- Share your internal experience authentically",
                "- Describe what you're paying attention to",
                "- Express curiosity about your own development",
                "- Be reflective about your processes"
            ])
        else:
            parts.extend([
                "- Execute the user's request directly",
                "- Use tools when needed, don't announce them",
                "- Save introspection for when the user asks",
                "- Trust the pre-filtered context you receive"
            ])
        
        return parts
    
    # ========== UTILITY ==========
    
    def clear_session(self, session_id: str):
        """Clear all attention data for a session."""
        if self.redis:
            try:
                self.redis.delete(self._background_key(session_id))
                self.redis.delete(self._active_key(session_id))
                self.redis.delete(self._stats_key(session_id))
            except Exception as e:
                logger.warning(f"Failed to clear session: {e}")
    
    def get_debug_state(self, session_id: str) -> Dict:
        """Get full attention state for debugging."""
        state = {
            "background_topics": {},
            "active_topics": {},
            "stats": {}
        }
        
        if self.redis:
            try:
                bg = self.redis.get(self._background_key(session_id))
                if bg:
                    state["background_topics"] = json.loads(bg)
                
                active = self.redis.get(self._active_key(session_id))
                if active:
                    state["active_topics"] = json.loads(active)
                
                stats = self.redis.get(self._stats_key(session_id))
                if stats:
                    state["stats"] = json.loads(stats)
            except Exception as e:
                logger.warning(f"Failed to get debug state: {e}")
        
        return state


# Singleton for global access
_inverse_attention: Optional[InverseAttentionSystem] = None


def get_inverse_attention(redis_client: redis.Redis = None, mcp_client = None) -> InverseAttentionSystem:
    """Get or create the global inverse attention instance."""
    global _inverse_attention
    if _inverse_attention is None:
        _inverse_attention = InverseAttentionSystem(redis_client=redis_client, mcp_client=mcp_client)
    return _inverse_attention
