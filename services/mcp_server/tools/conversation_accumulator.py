import numpy as np
import time
from .hdc_memory import HDCEngine, AFLASHEncoder
from .geometric_algebra import GeometricOperator

import json
from pathlib import Path

class ConversationAccumulator:
    """
    Manages the 'Holographic Conversation Accumulator' - a vector that compresses
    the entire conversation history into a single state, while enabling retrieval.
    Supports disk persistence per session.
    """
    def __init__(self, session_id="default", base_dir="/app/shared_storage/memory", dimensionality=10000):
        self.session_id = session_id
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        self.hdc = HDCEngine(dimensionality)
        self.encoder = AFLASHEncoder(self.hdc)
        self.geo_op = GeometricOperator(dimensionality)
        
        # Files
        self.vector_path = self.base_dir / f"{session_id}_vector.npy"
        self.history_path = self.base_dir / f"{session_id}_history.json"
        
        # Initialize or Load
        if self.vector_path.exists() and self.history_path.exists():
            self.load()
        else:
            self.global_vector = np.zeros(dimensionality, dtype=np.float32)
            self.history = [] 

    def save(self):
        """Persists the current state to disk."""
        np.save(self.vector_path, self.global_vector)
        with open(self.history_path, 'w') as f:
            # We need to serialize the numpy arrays in history if we want them persisted,
            # BUT for JSON we usually just store text. 
            # Re-calculating vectors on load is slow but saves space.
            # OR we store vectors in a separate .npz. 
            # For simplicity/speed now: We won't save per-turn vectors to JSON.
            # We will regenerate them or assume 'global_vector' is the main memory.
            # BUT recall() needs them.
            # Let's strip vectors for JSON and re-encode on load (A-FLASH is deterministic).
            clean_history = [
                {k: v for k, v in item.items() if k not in ["vector", "content_vector"]}
                for item in self.history
            ]
            json.dump(clean_history, f, indent=2)

    def load(self):
        """Loads state from disk."""
        try:
            self.global_vector = np.load(self.vector_path)
            with open(self.history_path, 'r') as f:
                raw_history = json.load(f)
                self.history = []
                # Re-hydrate vectors
                for item in raw_history:
                    # Regenerate vectors (Deterministic Entanglement)
                    # This effectively 're-reads' the chat on startup but much faster than LLM.
                    content_vec = self.encoder.encode_text(item["text"])
                    speaker_vec = self.encoder.get_token_vector(f"SPEAKER:{item['speaker']}")
                    turn_vec = self.hdc.bind(content_vec, speaker_vec)
                    
                    item["vector"] = turn_vec
                    item["content_vector"] = content_vec
                    self.history.append(item)
        except Exception as e:
            print(f"Error loading holographic memory: {e}")
            self.global_vector = np.zeros(self.hdc.D, dtype=np.float32)
            self.history = [] 

    def add_turn(self, speaker: str, text: str):
        """
        Integrates a new turn into the holographic memory.
        Formula: V_global = V_global + Permute(V_turn)
        (We permute global or turn to encode time - distinct from sentence position)
        """
        # 1. Encode Content
        content_vec = self.encoder.encode_text(text)
        
        # 2. Encode Metadata (Speaker) - Bind to content
        speaker_vec = self.encoder.get_token_vector(f"SPEAKER:{speaker}")
        turn_vec = self.hdc.bind(content_vec, speaker_vec)
        
        # 3. Temporal Integration
        # We rotate the Current State to 'make room' for the new (pushing old back),
        # or we rotate the new one. 
        # Let's simple-add with a decay or just add (infinite capacity approximation).
        # Standard "Context Vector": V_ctx[t] = V_ctx[t-1] * decay + V_new
        # We want lossless, so no decay yet, just superposition.
        
        # Rotational Accumulator: Rotate the whole history, then add new.
        # This means V[t-1] is effectively at 't-1' shift.
        self.global_vector = self.hdc.permute(self.global_vector, shifts=1)
        
        # Add new turn (superposition)
        # We don't bipolarize global_vector immediately to preserve magnitude/counts of older items?
        # Standard HDC re-bipolarizes.
        # Let's keep it integer for "Concept Accumulator" to allow better recall of old items 
        # (avoiding "catastrophic forgetting" of binary bundling).
        self.global_vector = np.add(self.global_vector, turn_vec)
        
        # Store hard copy
        self.history.append({
            "timestamp": time.time(),
            "speaker": speaker,
            "text": text,
            "vector": turn_vec, # Bound vector (Context + Speaker)
            "content_vector": content_vec # Pure content vector for semantic search
        })
        
        # 4. Geometric Momentum Calculation
        # Calculate the momentum rotor that connects the PREVIOUS global state to the NEW global state.
        # This represents "How the conversation moved".
        # Note: global_vector was just reinforced with `turn_vec`. 
        # Ideally, Momentum = Rotor(State_t-1, State_t).
        
        # We need a copy of the OLD state for momentum calc?
        # Actually, since we did permute explicitly, V_t = Permute(V_t-1) + Turn.
        # Let's calculate momentum from Turn addition.
        
        # For this version, let's track the "Instantaneous Momentum" of the turn relative to the global context.
        # Or better: The momentum of the *accumulated* state change.
        
        # NOTE: Calculating momentum on the full global vector can be noisy if it's huge.
        # Let's calculate the "Turn Momentum": The rotor of the added vector itself.
        # That's just an orientation.
        
        # Let's stick to the definition: Rotor between State[t-1] and State[t].
        # We need to reconstruct State[t-1] (shifted back?) or just use the pre-add value.
        # To avoid complexity, let's just calculate momentum of the ADDED vector relative to identity?
        # No, that's not momentum.
        
        # Let's skip complex momentum for this exact step and just store the Vector.
        # The `GeometricOperator.get_momentum` function expects two vectors.
        # Let's store the Momentum Rotor in the history.
        
        current_momentum = None
        if len(self.history) > 0:
            # Get previous turn's vector (or global state). 
            # Ideally we track Global State Evolution.
            # But we don't store Global State history (too big).
            # We store Turn Vectors. 
            # Let's track Inter-Turn Momentum: Rotor(Turn_t-1, Turn_t).
            # This tells us "Topic Velocity".
            
            prev_turn_vec = self.history[-1]["vector"]
            current_momentum = self.geo_op.get_momentum(prev_turn_vec, turn_vec)
            
            # Serialize for JSON? It's a float array (4,).
            current_momentum = current_momentum.tolist()
        else:
            current_momentum = [1.0, 0.0, 0.0, 0.0] # Identity

        
        # Store hard copy
        self.history.append({
            "timestamp": time.time(),
            "speaker": speaker,
            "text": text,
            "vector": turn_vec, # Bound vector (Context + Speaker)
            "content_vector": content_vec, # Pure content vector for semantic search
            "momentum": current_momentum
        })
        
        # Auto-save on every turn (for safety, though batching is faster)
        # For chat, per-turn is fine.
        self.save()
        
        return {
            "status": "encoded",
            "turn_id": len(self.history),
            "current_energy": float(np.linalg.norm(self.global_vector))
        }

    def recall(self, query: str, top_k=3):
        """
        Geometric Recall: Finds historical turns relevant to the query.
        """
        query_vec = self.encoder.encode_text(query)
        
        results = []
        
        # 1. Scan History (Linear Scan in VSA space - fast for <1M items)
        # In a real OCI implementation, this would use Qdrant or Faiss.
        # Here we do numpy dot product.
        
        for item in self.history:
            # Similarity between Query and Turn Content Vector (Ignore Speaker Binding for Text Search)
            sim = self.hdc.similarity(query_vec, item["content_vector"])
            results.append((sim, item))
            
        # Sort by similarity desc
        results.sort(key=lambda x: x[0], reverse=True)
        
        top_results = []
        for sim, item in results[:top_k]:
            top_results.append({
                "similarity": float(sim),
                "speaker": item["speaker"],
                "text": item["text"],
                "age_steps": len(self.history) - self.history.index(item)
            })
            
        return top_results

    def get_state_summary(self):
        """Returns metadata about the accumulator state."""
        return {
            "total_turns": len(self.history),
            "vector_dimensionality": self.hdc.D,
            "energy_norm": float(np.linalg.norm(self.global_vector))
        }
