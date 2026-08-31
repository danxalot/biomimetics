import numpy as np

class CorpusCallosum:
    """
    The 'Corpus Callosum' acts as the translation layer between the
    Geometric/Holographic Mind (Right Hemisphere) and the 
    Symbolic/LLM Mind (Left Hemisphere).
    
    It converts high-dimensional vector states into "Somatic Markers"
    (feelings/intuitions) that the LLM can understand.
    """
    def __init__(self, accumulator):
        self.acc = accumulator
        self.hdc = accumulator.hdc
        self.encoder = accumulator.encoder
        
        # Archetypes: Improving specific emotional/state anchors
        # In a real system, these would be learned from feedback.
        self.archetypes = {
            "Confusion": self.encoder.encode_text("confusion unclear unknown wtf error help"),
            "Agreement": self.encoder.encode_text("agreement yes correct understood affirmative good"),
            "Conflict": self.encoder.encode_text("conflict no wrong bad incorrect stop halt"),
            "Progress": self.encoder.encode_text("progress moving forward next step done success"),
            "Stagnation": self.encoder.encode_text("stagnation stuck loop waiting repeating same"),
            "Technical": self.encoder.encode_text("code function variable class import return"),
            "Conceptual": self.encoder.encode_text("idea concept philosophy meaning why how")
        }

    def get_intuition(self):
        """
        Returns the current 'Somatic State' of the conversation.
        """
        # 1. Volatility (Momentum Magnitude)
        # ----------------------------------
        # Momentum is stored as a list of 4 floats (Quaternion) in the history
        history = self.acc.history
        volatility = 0.0
        momentum_desc = "Stable"
        
        if len(history) > 0:
            last_turn = history[-1]
            if "momentum" in last_turn and last_turn["momentum"]:
                # Momentum is a rotor (Quaternion). 
                # Pure rotation has norm 1. 
                # If we tracked velocity magnitude separately, we'd use that.
                # Currently, our momentum IS a rotation, so magnitude is always ~1.
                # However, the "Angle" of rotation represents the "Amount of Change".
                # Angle = 2 * acos(w)
                
                q = last_turn["momentum"] # [w, x, y, z]
                w = q[0]
                # Clamp for safety
                w = max(-1.0, min(1.0, w))
                angle = 2 * np.arccos(w) 
                
                # Normalize angle (0 to Pi) to 0-1 scale
                volatility = angle / np.pi
                
                if volatility < 0.1: momentum_desc = "Static"
                elif volatility < 0.3: momentum_desc = "Steady"
                elif volatility < 0.6: momentum_desc = "Active"
                else: momentum_desc = "Volatile"

        # 2. Resonance (Archetype Similarity)
        # -----------------------------------
        # We check the CURRENT state vector against archetypes.
        # Note: The global state vector is a history accumulation.
        # We might also want to check the LAST TURN only for immediate feeling.
        
        current_resonance = {}
        last_turn_resonance = {}
        
        # Global State
        v_global = self.acc.global_vector
        for name, archetype_vec in self.archetypes.items():
            sim = self.hdc.similarity(v_global, archetype_vec)
            current_resonance[name] = float(sim)
            
        # Sort by strength
        dominant_state = max(current_resonance, key=current_resonance.get)
        dominant_score = current_resonance[dominant_state]

        # 3. Construct "Somatic Marker"
        # -----------------------------
        
        intuition = {
            "volatility": {
                "score": float(volatility),
                "description": momentum_desc
            },
            "emotional_resonance": {
                "dominant": dominant_state,
                "score": dominant_score,
                "all_scores": current_resonance
            },
            "summary": f"The conversation is {momentum_desc.lower()}. I feel a sense of {dominant_state}."
        }
        
        return intuition
