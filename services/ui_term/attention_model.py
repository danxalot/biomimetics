"""
ARCA Attention Model
====================
Redis-backed topic tracking with decay and hierarchical refresh.

Topics decay in importance if not mentioned. Mentioning a parent refreshes all children.
This provides ARCA with persistent conversational context that fades over time.
"""

import json
import time
import threading
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import redis

logger = logging.getLogger(__name__)

# Constants
DECAY_INTERVAL_SECONDS = 60  # How often to run decay
DECAY_RATE = 0.1  # 10% decay per interval
MIN_IMPORTANCE = 0.1  # Below this, topic is considered "forgotten"
MAX_TOPICS = 50  # Maximum topics per session
REDIS_PREFIX = "arca:attention:"
FIELD_PREFIX = "arca:field:"

@dataclass
class HolographicField:
    """
    Represents an active background field (e.g., from an Image or Diagram).
    Acts as a 'Physics Law' modifier for the conversation manifold.
    """
    id: str
    source_type: str # IMAGE, DIAGRAM, AUDIO
    vector_ref: str # Reference to stored GATr/SigLIP vector
    description: str
    strength: float = 1.0
    active: bool = True


class AttentionModel:
    """
    Persistent attention model that tracks conversation topics with decay.
    
    Features:
    - Topics decay in importance if not mentioned
    - Mentioning a topic refreshes its importance to 1.0
    - Mentioning a parent topic refreshes all children
    - Topics are linked hierarchically (parent-child)
    """
    
    def __init__(self, redis_client: redis.Redis = None, redis_host: str = "redis", redis_port: int = 6379):
        """Initialize the attention model with Redis connection."""
        if redis_client:
            self.redis = redis_client
        else:
            try:
                self.redis = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
                self.redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed for AttentionModel: {e}")
                self.redis = None
        
        self._decay_thread = None
        self._decay_active = False
        
    def _key(self, session_id: str) -> str:
        """Get Redis key for session's attention data."""
        return f"{REDIS_PREFIX}{session_id}"
    
    def _get_session_data(self, session_id: str) -> Dict:
        """Get attention data for a session."""
        if not self.redis:
            return {"topics": {}, "decay_rate": DECAY_RATE}
        
        try:
            data = self.redis.get(self._key(session_id))
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Failed to get attention data: {e}")
        
        return {"topics": {}, "decay_rate": DECAY_RATE}
    
    def _save_session_data(self, session_id: str, data: Dict):
        """Save attention data for a session."""
        if not self.redis:
            return
        
        try:
            self.redis.set(self._key(session_id), json.dumps(data))
            self.redis.expire(self._key(session_id), 86400)  # 24 hour TTL
        except Exception as e:
            logger.warning(f"Failed to save attention data: {e}")
    
    def mention_topic(
        self, 
        session_id: str, 
        topic_name: str, 
        parent: str = None,
        description: str = None
    ) -> Dict:
        """
        Register that a topic was mentioned in conversation.
        
        - Creates the topic if new
        - Refreshes importance to 1.0
        - If parent is specified, links this topic as child of parent
        - Also refreshes all child topics of this topic
        
        Args:
            session_id: User session identifier
            topic_name: Name of the topic (e.g., "kitchen", "tiles")
            parent: Optional parent topic name (e.g., "tiles" -> parent="kitchen")
            description: Optional description of the topic
            
        Returns:
            Updated topic data
        """
        data = self._get_session_data(session_id)
        topics = data.get("topics", {})
        
        current_time = time.time()
        
        # Create or update the topic
        if topic_name not in topics:
            topics[topic_name] = {
                "importance": 1.0,
                "last_mentioned": current_time,
                "parent": parent,
                "children": [],
                "description": description or topic_name,
                "mention_count": 1
            }
        else:
            # Refresh importance
            topics[topic_name]["importance"] = 1.0
            topics[topic_name]["last_mentioned"] = current_time
            topics[topic_name]["mention_count"] = topics[topic_name].get("mention_count", 0) + 1
            if description:
                topics[topic_name]["description"] = description
        
        # Link to parent if specified
        if parent:
            topics[topic_name]["parent"] = parent
            # Ensure parent exists
            if parent not in topics:
                topics[parent] = {
                    "importance": 1.0,
                    "last_mentioned": current_time,
                    "parent": None,
                    "children": [topic_name],
                    "description": parent,
                    "mention_count": 1
                }
            else:
                # Add to parent's children if not already there
                if topic_name not in topics[parent]["children"]:
                    topics[parent]["children"].append(topic_name)
        
        # Refresh all children of this topic (hierarchical refresh)
        self._refresh_children(topics, topic_name, current_time)
        
        # Prune old topics if exceeding max
        if len(topics) > MAX_TOPICS:
            self._prune_topics(topics)
        
        data["topics"] = topics
        self._save_session_data(session_id, data)
        
        return topics[topic_name]
    
    def _refresh_children(self, topics: Dict, parent_name: str, current_time: float):
        """Recursively refresh importance of all child topics."""
        if parent_name not in topics:
            return
        
        children = topics[parent_name].get("children", [])
        for child_name in children:
            if child_name in topics:
                # Refresh child (but slightly less than parent)
                topics[child_name]["importance"] = min(1.0, topics[child_name]["importance"] + 0.5)
                topics[child_name]["last_mentioned"] = current_time
                # Recurse for grandchildren
                self._refresh_children(topics, child_name, current_time)
    
    def _prune_topics(self, topics: Dict):
        """Remove lowest-importance topics when exceeding max."""
        if len(topics) <= MAX_TOPICS:
            return
        
        # Sort by importance and remove lowest
        sorted_topics = sorted(topics.items(), key=lambda x: x[1].get("importance", 0))
        remove_count = len(topics) - MAX_TOPICS
        
        for i in range(remove_count):
            topic_name = sorted_topics[i][0]
            del topics[topic_name]
            # Also remove from any parent's children list
            for t in topics.values():
                if topic_name in t.get("children", []):
                    t["children"].remove(topic_name)
    
    def get_attention_context(self, session_id: str, top_n: int = 10) -> str:
        """
        Get a formatted attention context string for prompt injection.
        
        This returns the top-N most relevant topics as a context block
        that can be prepended to ARCA's prompt.
        
        Args:
            session_id: User session identifier
            top_n: Number of top topics to include
            
        Returns:
            Formatted context string for LLM prompt
        """
        data = self._get_session_data(session_id)
        topics = data.get("topics", {})
        
        if not topics:
            return "[Attention Context: No topics tracked yet. The conversation is fresh.]"
        
        # Sort by importance (descending)
        sorted_topics = sorted(
            topics.items(), 
            key=lambda x: x[1].get("importance", 0), 
            reverse=True
        )[:top_n]
        
        # Filter out very low importance topics
        relevant_topics = [(name, info) for name, info in sorted_topics 
                          if info.get("importance", 0) >= MIN_IMPORTANCE]
        
        if not relevant_topics:
            return "[Attention Context: All previous topics have faded from focus. The conversation can take a new direction.]"
        
        # Build context
        lines = ["[Attention Context - Topics the user has been discussing:]"]
        
        for name, info in relevant_topics:
            importance = info.get("importance", 0)
            parent = info.get("parent")
            children = info.get("children", [])
            desc = info.get("description", name)
            
            # Format importance as qualitative
            if importance >= 0.8:
                focus = "ACTIVE FOCUS"
            elif importance >= 0.5:
                focus = "Recent"
            else:
                focus = "Fading"
            
            parent_str = f" (part of: {parent})" if parent else ""
            children_str = f" [contains: {', '.join(children[:3])}]" if children else ""
            
            lines.append(f"- {name} ({focus}){parent_str}{children_str}: {desc[:100]}")
        
        lines.append("\nUse this context to understand what the user cares about. Don't explicitly mention 'attention' or 'importance scores'.")
        
        return "\n".join(lines)
    
    def decay_topics(self, session_id: str) -> int:
        """
        Apply decay to all topics in a session.
        
        Called periodically to reduce importance of unused topics.
        
        Args:
            session_id: User session identifier
            
        Returns:
            Number of topics that were decayed
        """
        data = self._get_session_data(session_id)
        topics = data.get("topics", {})
        decay_rate = data.get("decay_rate", DECAY_RATE)
        
        decayed_count = 0
        topics_to_remove = []
        
        for name, info in topics.items():
            current_importance = info.get("importance", 1.0)
            new_importance = current_importance * (1 - decay_rate)
            
            if new_importance < MIN_IMPORTANCE:
                topics_to_remove.append(name)
            else:
                topics[name]["importance"] = new_importance
                decayed_count += 1
        
        # Remove forgotten topics
        for name in topics_to_remove:
            del topics[name]
            # Clean up parent references
            for t in topics.values():
                if name in t.get("children", []):
                    t["children"].remove(name)
        
        data["topics"] = topics
        self._save_session_data(session_id, data)
        
        return decayed_count
    
    def decay_all_sessions(self):
        """Apply decay to all active sessions. Called by background thread."""
        if not self.redis:
            return
        
        try:
            # Find all attention keys
            keys = self.redis.keys(f"{REDIS_PREFIX}*")
            for key in keys:
                session_id = key.replace(REDIS_PREFIX, "")
                self.decay_topics(session_id)
        except Exception as e:
            logger.warning(f"Failed to decay all sessions: {e}")
    
    def start_decay_thread(self):
        """Start background thread for periodic decay."""
        if self._decay_thread and self._decay_thread.is_alive():
            return  # Already running
        
        self._decay_active = True
        self._decay_thread = threading.Thread(target=self._decay_loop, daemon=True)
        self._decay_thread.start()
        logger.info("Attention decay thread started")
    
    def stop_decay_thread(self):
        """Stop background decay thread."""
        self._decay_active = False
        if self._decay_thread:
            self._decay_thread.join(timeout=5)
            logger.info("Attention decay thread stopped")
    
    def _decay_loop(self):
        """Background loop for periodic decay."""
        while self._decay_active:
            time.sleep(DECAY_INTERVAL_SECONDS)
            if self._decay_active:
                self.decay_all_sessions()
    
    def clear_session(self, session_id: str):
        """Clear all attention data for a session."""
        if self.redis:
            try:
                self.redis.delete(self._key(session_id))
            except Exception as e:
                logger.warning(f"Failed to clear session: {e}")
    
    def get_topic_tree(self, session_id: str) -> Dict:
        """
        Get a hierarchical view of topics for debugging/visualization.
        
        Returns a tree structure where root topics contain their children.
        """
        data = self._get_session_data(session_id)
        topics = data.get("topics", {})
        
        # Find root topics (no parent)
        roots = {name: info for name, info in topics.items() if not info.get("parent")}
        
        def build_tree(name: str, info: Dict) -> Dict:
            children = info.get("children", [])
            return {
                "name": name,
                "importance": info.get("importance", 0),
                "description": info.get("description", ""),
                "children": [
                    build_tree(child, topics.get(child, {}))
                    for child in children if child in topics
                ]
            }
        
        return {
            "session_id": session_id,
            "topic_count": len(topics),
            "roots": [build_tree(name, info) for name, info in roots.items()]
        }


# Singleton instance for global access
_attention_model: Optional[AttentionModel] = None


def get_attention_model(redis_client: redis.Redis = None) -> AttentionModel:
    """Get or create the global attention model instance."""
    global _attention_model
    if _attention_model is None:
        _attention_model = AttentionModel(redis_client=redis_client)
    return _attention_model


    def project_field(self, session_id: str, source_path: str, description: str, strength: float = 1.0) -> Dict[str, Any]:
        """
        Projects a new Holographic Field (e.g. Image) onto the Manifold.
        """
        if not self.redis:
            return {"error": "Redis not available"}
            
        field_id = f"FIELD_{int(time.time())}"
        
        # Mock Vector Logic (In production: Qwen-VL -> GATr)
        vector_ref = f"vec_{field_id}"
        
        field = HolographicField(
            id=field_id,
            source_type="IMAGE" if any(x in source_path.lower() for x in ['.png', '.jpg', '.jpeg']) else "DOCUMENT",
            vector_ref=vector_ref,
            description=description,
            strength=strength
        )
        
        # Store active fields in a separate Redis hash or list
        key = f"{FIELD_PREFIX}{session_id}"
        self.redis.hset(key, field_id, json.dumps(asdict(field)))
        self.redis.expire(key, 86400) # 24h TTL
        
        logger.info(f"Projected Holographic Field: {description} ({field_id})")
        return asdict(field)

    def get_active_fields(self, session_id: str) -> List[Dict]:
        """Results all active holographic fields for the session."""
        if not self.redis:
            return []
            
        key = f"{FIELD_PREFIX}{session_id}"
        fields_raw = self.redis.hgetall(key)
        
        fields = []
        for fid, fjson in fields_raw.items():
            fields.append(json.loads(fjson))
        return fields

# Helper functions for easy integration
def mention(session_id: str, topic: str, parent: str = None, desc: str = None):
    """Convenience function to mention a topic."""
    return get_attention_model().mention_topic(session_id, topic, parent, desc)

def project(session_id: str, path: str, desc: str):
    """Convenience function to project a field."""
    return get_attention_model().project_field(session_id, path, desc)

def get_context(session_id: str, top_n: int = 10) -> str:
    """Convenience function to get attention context for prompt."""
    model = get_attention_model()
    text_context = model.get_attention_context(session_id, top_n)
    
    # Append Fields
    fields = model.get_active_fields(session_id)
    if fields:
        field_lines = ["\n[Active Holographic Fields - These define the 'Physics' of the conversation:]"]
        for f in fields:
            field_lines.append(f"- {f['description']} (Type: {f['source_type']}, Strength: {f['strength']})")
        text_context += "\n".join(field_lines)
        
    return text_context
