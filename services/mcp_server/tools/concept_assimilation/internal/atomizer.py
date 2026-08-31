import json
import logging
# Adjusted import path for MCP server environment
from tools.geometry_kernel.model_engine import CognitiveScheduler

logger = logging.getLogger(__name__)

class DocumentAtomizer:
    def __init__(self):
        # Uses the existing 'Cognitive Tick' scheduler from your kernel
        self.scheduler = CognitiveScheduler()

    def explode_document(self, doc_text, doc_source_id):
        """
        Breaks a document into atomic 'Idea Nodes' with separated code.
        """
        prompt = """
        Analyze the following text. Break it down into ATOMIC functional components.
        For each component, extract:
        1. 'Concept': A 1-sentence summary of the logic/idea.
        2. 'Code': Any associated code blocks (preserve exact syntax).
        3. 'Type': [ARCHITECTURAL | FUNCTIONAL | THEORETICAL]
        
        Output strictly a JSON List of objects: 
        [{"Concept": "...", "Code": "...", "Type": "..."}]
        """
        
        # Run local DeepSeek via the scheduler
        # Limit context to avoid overflow, adjust as needed
        response = self.scheduler.run_reasoning_phase(context_text=doc_text[:6000], prompt_template=prompt)
        
        try:
            # Clean possible markdown formatting from response
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:-3]
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:-3]
                
            raw_nodes = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.warning(f"Atomizer JSON parse failed: {e}. Output was: {response[:100]}...")
            # Fallback for simple parsing if model output is messy - return empty or try regex
            return []

        atoms = []
        for node in raw_nodes:
            # Code is heavy (Real). Theory is light (Abstract).
            # Safety check for keys
            code_snippet = node.get('Code', '')
            mass = 10.0 if code_snippet and len(code_snippet) > 10 else 5.0
            
            concept = node.get('Concept', 'Unknown')
            # Create a deterministic ID
            node_id_suffix = concept[:30].replace(' ','_')
            
            atoms.append({
                "id": f"{doc_source_id}::{node_id_suffix}",
                "source_doc": doc_source_id,
                "concept": concept,
                "code_snippet": code_snippet,
                "type": node.get('Type', 'FUNCTIONAL'),
                "mass": mass,
                "vector": None # Will be populated by Embedding Engine later
            })
            
        return atoms
