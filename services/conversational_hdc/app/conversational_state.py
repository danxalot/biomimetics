import logging
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger("ConversationalHDCState")

# NumPy-based Hyperdimensional Computing Operations (replacing torchhd)
class HDCOps:
    """NumPy-based HDC operations for bipolar {-1, +1} vectors."""
    
    @staticmethod
    def random(dim: int = 10000, seed: Optional[int] = None) -> np.ndarray:
        """Generate a random bipolar hypervector."""
        if seed is not None:
            rng = np.random.RandomState(seed)
            return rng.choice([-1, 1], size=dim)
        return np.random.choice([-1, 1], size=dim)
    
    @staticmethod
    def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Bind two hypervectors (element-wise multiplication for bipolar)."""
        return a * b
    
    @staticmethod
    def bundle(vectors: List[np.ndarray]) -> np.ndarray:
        """Bundle hypervectors using element-wise sum and threshold."""
        if not vectors:
            return np.zeros(10000, dtype=np.float32)
        
        stacked = np.vstack(vectors)
        bundled = np.sum(stacked, axis=0)
        
        # Threshold to bipolar: positive -> +1, negative -> -1, zero -> random
        bundled = np.sign(bundled)
        zeros = (bundled == 0)
        if np.any(zeros):
            bundled[zeros] = np.random.choice([-1, 1], size=np.sum(zeros))
        
        return bundled.astype(np.float32)
    
    @staticmethod
    def permute(hv: np.ndarray, n: int = 1) -> np.ndarray:
        """Circular shift (permutation) for sequence encoding."""
        return np.roll(hv, shift=n)
    
    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between hypervectors."""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        # Avoid division by zero
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return dot_product / (norm_a * norm_b)

# Global HDC operations instance
_hdc_ops = HDCOps()

class ConversationalHDCState:
    """
    Encodes an entire conversation into a single hypervector that
    accumulates understanding without storing raw text.
    """

    def __init__(self, encoder=None, hv_dim: int = 10000):
        self.hv_dim = hv_dim
        # Default Random Projection Encoder if none provided (placeholder)
        self.encoder = encoder
        
        # Replace torchhd functions with numpy equivalents
        self.bind = _hdc_ops.bind
        self.bundle = _hdc_ops.bundle
        self.permute = _hdc_ops.permute
        self.role_user = _hdc_ops.random(1, hv_dim)[0]
        self.role_assistant = _hdc_ops.random(1, hv_dim)[0]
        self.role_system = _hdc_ops.random(1, hv_dim)[0]
        self.role_topics = _hdc_ops.random(1, hv_dim)[0]
        self.role_sentiment = _hdc_ops.random(1, hv_dim)[0]
        self.role_intents = _hdc_ops.random(1, hv_dim)[0]
        
        # Initialize codebooks with random vectors
        self.emotion_codebook = {
            "positive": _hdc_ops.random(1, hv_dim)[0],
            "negative": _hdc_ops.random(1, hv_dim)[0],
            "neutral": _hdc_ops.random(1, hv_dim)[0]
        }
        
        self.topic_codebook = {
            'technical': _hdc_ops.random(1, hv_dim)[0],
            'problem_solving': _hdc_ops.random(1, hv_dim)[0],
            'casual': _hdc_ops.random(1, hv_dim)[0],
            'learning': _hdc_ops.random(1, hv_dim)[0],
            'planning': _hdc_ops.random(1, hv_dim)[0]
        }
        
        self.intent_codebook = {}
        self.conversation_hv = np.zeros(hv_dim, dtype=np.float32)
        self.topics_hv = np.zeros(hv_dim, dtype=np.float32)
        self.sentiments_hv = np.zeros(hv_dim, dtype=np.float32)
        self.intents_hv = np.zeros(hv_dim, dtype=np.float32)
        
        # Counters for averaging
        self.topic_count = defaultdict(int)
        self.sentiment_count = defaultdict(int)
        self.intent_count = defaultdict(int)
        
        # Timestamp for decay
        self.last_updated = datetime.now()

    def add_user_input(self, text: str):
        """Process user input and update state."""
        # Simple keyword-based emotion detection (would be enhanced with NLP)
        text_lower = text.lower()
        
        # Detect emotions
        if any(word in text_lower for word in ['happy', 'good', 'great', 'excellent', 'awesome']):
            emotion = 'positive'
        elif any(word in text_lower for word in ['sad', 'bad', 'terrible', 'awful', 'hate']):
            emotion = 'negative'
        else:
            emotion = 'neutral'
        
        # Update emotion vector using bundling
        emotion_hv = self.emotion_codebook[emotion]
        self.emotion_codebook[emotion] = self.bundle([emotion_hv, self.role_user])
        
        # Update conversation state
        self.conversation_hv = self.bundle([self.conversation_hv, self.role_user, emotion_hv])
        self.last_updated = datetime.now()

    def add_assistant_response(self, text: str):
        """Process assistant response and update state."""
        # Update with assistant role
        self.conversation_hv = self.bundle([self.conversation_hv, self.role_assistant])
        self.last_updated = datetime.now()

    def add_topic(self, topic: str):
        """Add a topic to the conversation state."""
        if topic not in self.topic_codebook:
            self.topic_codebook[topic] = _hdc_ops.random(1, self.hv_dim)[0]
        
        # Update topic vector
        topic_hv = self.topic_codebook[topic]
        self.topics_hv = self.bundle([self.topics_hv, topic_hv])
        self.topic_count[topic] += 1
        self.last_updated = datetime.now()

    def add_intent(self, intent: str):
        """Add an intent to the conversation state."""
        if intent not in self.intent_codebook:
            self.intent_codebook[intent] = _hdc_ops.random(1, self.hv_dim)[0]
        
        # Update intent vector
        intent_hv = self.intent_codebook[intent]
        self.intents_hv = self.bundle([self.intents_hv, intent_hv])
        self.intent_count[intent] += 1
        self.last_updated = datetime.now()

    def get_conversation_summary_vector(self) -> np.ndarray:
        """Get the current conversation state vector."""
        return self.conversation_hv.copy()

    def get_topics_vector(self) -> np.ndarray:
        """Get the aggregated topics vector."""
        return self.topics_hv.copy()

    def get_sentiments_vector(self) -> np.ndarray:
        """Get the aggregated sentiments vector."""
        return self.sentiments_hv.copy()

    def get_intents_vector(self) -> np.ndarray:
        """Get the aggregated intents vector."""
        return self.intents_hv.copy()

    def get_similarity_scores(self, query_hv: np.ndarray) -> Dict[str, float]:
        """Get similarity scores between query and various state components."""
        return {
            'content_relevance': _hdc_ops.cosine_similarity(query_hv, self.conversation_hv),
            'topic_relevance': _hdc_ops.cosine_similarity(query_hv, self.topics_hv),
            'sentiment_relevance': _hdc_ops.cosine_similarity(query_hv, self.sentiments_hv),
            'intent_relevance': _hdc_ops.cosine_similarity(query_hv, self.intents_hv)
        }
    
    def reset(self):
        """Reset the conversation state."""
        self.conversation_hv = np.zeros(self.hv_dim, dtype=np.float32)
        self.topics_hv = np.zeros(self.hv_dim, dtype=np.float32)
        self.sentiments_hv = np.zeros(self.hv_dim, dtype=np.float32)
        self.intents_hv = np.zeros(self.hv_dim, dtype=np.float32)
        self.topic_count.clear()
        self.sentiment_count.clear()
        self.intent_count.clear()
        self.last_updated = datetime.now()

