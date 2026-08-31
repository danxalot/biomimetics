import dataclasses

# wrappers for local components
from geometry_kernel.components import GATr_Wrapper, EB_JEPA_Wrapper
from geometry_kernel.llm_interface import LocalQwenVL

@dataclasses.dataclass
class VectorMap:
    has_image: bool = False
    image_path: str = None

class HolisticAuditor:
    def __init__(self):
        self.physicist = GATr_Wrapper()   # Handles 3D/Geometric Logic
        self.conscience = EB_JEPA_Wrapper() # Handles Energy/Stability
        self.narrator = LocalQwenVL()     # Your Qwen 2B instance
        
        # System Prompt for Qwen to act as the synthesis engine
        self.narrator_prompt = """
        You are the Voice of the System. 
        I will give you a GEOMETRIC STRESS SCORE (from GATr) and an ENTROPY SCORE (from EB-JEPA).
        Your job: Translate these numbers into a 'Project Risk Assessment' for the User.
        If Entropy is High (>0.7), you must REJECT the plan.
        Be concise.
        """

    def audit_proposal(self, proposal_text, blackboard_vector_map=None):
        """
        Replaces 'mcp_robotics.analyze()'
        """
        if blackboard_vector_map is None:
            blackboard_vector_map = VectorMap()

        print(f"Auditing: {proposal_text[:50]}...")

        # 1. THE PHYSICS CHECK (GATr)
        # Does this change break the geometry? (e.g., Circular dependencies?)
        # GATr is E(3) equivariant - it sees the 'shape' of the logic.
        geo_stress = self.physicist.calculate_stress(blackboard_vector_map)
        # Output: float 0.0 (Perfect) to 1.0 (Broken)

        # 2. THE ENERGY CHECK (EB-JEPA)
        # Does this change feel 'heavy' or 'chaotic'?
        # We feed the GATr latent state + Proposal Vector into EB-JEPA
        energy_score = self.conscience.predict_energy(
            state=geo_stress.latent_vector, 
            action=proposal_text
        )
        # Output: float 0.0 (Stable) to 1.0 (High Entropy/Risk)

        # 3. THE NARRATIVE SYNTHESIS (Qwen VL 2B)
        # We construct a prompt that includes the raw math
        audit_packet = f"""
        PROPOSAL: {proposal_text}
        ---
        TELEMETRY:
        Geometric Stress: {geo_stress.value} (Threshold: 0.4)
        System Entropy: {energy_score.value} (Threshold: 0.6)
        """
        
        # If Qwen sees a diagram, we pass that too (Vision capability)
        if blackboard_vector_map.has_image:
            verdict = self.narrator.generate(
                prompt=self.narrator_prompt + f"\nDATA: {audit_packet}",
                image=blackboard_vector_map.image_path
            )
        else:
            verdict = self.narrator.generate(
                prompt=self.narrator_prompt + f"\nDATA: {audit_packet}"
            )

        return verdict
