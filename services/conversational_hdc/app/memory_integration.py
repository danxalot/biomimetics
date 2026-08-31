import logging`
import uuid`
from typing import List, Dict, Any`
from datetime import datetime`
import numpy as np`

from qdrant_client import QdrantClient`
from qdrant_client.models import VectorParams, Distance, PointStruct`

from .conversational_state import ConversationalHDCState`
from .genesis_chain import HDCGenesisChain`
from .conversational_state import _hdc_ops  # NumPy HDC operations`

logger = logging.getLogger("ConversationMemoryIntegration")`


class ConversationMemoryIntegration:
    """
    Integrates ConversationalHDCState with Qdrant for long-term memory.
    """
    
    def __init__(self, qdrant_host: str = "qdrant", qdrant_port: int = 6333, hv_dim: int = 10000):
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.hv_dim = hv_dim
        
        # Create collection if not exists
        try:
            self.qdrant.get_collection("conversation_memories")
        except:
            logger.info("Creating conversation_memories collection")
            self.qdrant.recreate_collection(
                collection_name="conversation_memories",
                vectors_config={
                    "conversation_state": VectorParams(size=hv_dim, distance=Distance.COSINE),
                    "final_intent": VectorParams(size=hv_dim, distance=Distance.COSINE)
                }
            )
        
        self.user_profiles: Dict[str, np.ndarray] = {}
    
    async def save_conversation(self, user_id: str,
                                 conversation_state: ConversationalHDCState,
                                 metadata: dict):
        """
        Save a completed conversation to long-term memory.
        """
        summary_hv = conversation_state.get_conversation_summary_vector()
        intent_hv = conversation_state.get_intents_vector()
        
        # Convert to list for Qdrant
        summary_list = summary_hv.flatten().tolist()
        intent_list = intent_hv.flatten().tolist()
        
        point_id = str(uuid.uuid4())
        
        # Store in Qdrant
        self.qdrant.upsert(
            collection_name="conversation_memories",
            points=[PointStruct(
                id=point_id,
                vector={
                    "conversation_state": summary_list,
                    "final_intent": intent_list
                },
                payload={
                    "user_id": user_id,
                    "timestamp": datetime.now().isoformat(),
                    "message_count": conversation_state.message_count,
                    **metadata
                }
            )]
        )
        logger.info(f"Saved conversation {point_id} for user {user_id}")
        
        # Update User Profile (Weighted Bundle)
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = summary_hv.copy()
        else:
            # Weighted bundle - recent conversations matter more (Double weight)
            # user_profile = bundle([old_profile, new_summary, new_summary])
            self.user_profiles[user_id] = _hdc_ops.bundle([
                self.user_profiles[user_id],
                summary_hv,
                summary_hv  # Double weight for new
            ])
    
    async def get_relevant_past_conversations(self,
                                               current_state: ConversationalHDCState,
                                               user_id: str,
                                               top_k: int = 3) -> List[dict]:
        """Find past conversations."""
        current_hv = current_state.get_conversation_summary_vector()
        
        results = self.qdrant.search(
            collection_name="conversation_memories",
            query_vector=("conversation_state", current_hv.flatten().tolist()),
            query_filter=None,  # In real app, filter by user_id via Filter/FieldCondition
            limit=top_k
        )
        return [r.payload for r in results]
    
    async def predict_user_intent(self, user_id: str,
                                   current_state: ConversationalHDCState) -> dict:
        """
        Predict what the user might want based on their profile
        and current conversation state.
        """
        if user_id not in self.user_profiles:
            return {"prediction": "unknown_user", "confidence": 0.0}
        
        profile_hv = self.user_profiles[user_id]
        current_hv = current_state.get_conversation_summary_vector()
        
        # Combine profile with current state (Contextual Binding)
        combined = _hdc_ops.bind(profile_hv, current_hv)
        
        # In a real implementation, we would compare 'combined' against
        # a Codebook of Known Intents. Since we don't have the Intent Codebook passed in here,
        # we'll return a placeholder that acknowledges the binding happened.
        
        # Simulated lookup
        return {
            "prediction": "inferred_intent_from_history", 
            "confidence": 0.8,
            "vector_stat": f"Bound Magnitude: {np.linalg.norm(combined):.2f}"
        }
