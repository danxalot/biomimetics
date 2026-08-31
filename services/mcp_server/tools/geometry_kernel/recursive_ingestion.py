"""
Recursive Ingestion Module (RLM Walker)
Implements the recursive document assimilation logic described in V2.1 Implementation Doc.
"""
import json
import re
import logging
from typing import Dict, Any, List

# Import scheduler from internal module (or will be passed in)
try:
    from .model_engine import CognitiveScheduler
except ImportError:
    from model_engine import CognitiveScheduler

logger = logging.getLogger(__name__)

class RecursiveIngestion:
    """
    Handles the "Recursive Loop" (RLM) to walk files and convert them into a 3D Solar System.
    """
    
    def __init__(self, scheduler: CognitiveScheduler):
        self.scheduler = scheduler

    def ingest_content(self, file_path: str, objective: str, content_type: str = "AUTO") -> Dict[str, Any]:
        """
        Uses Recursive Loop to walk file and convert to Solar System.
        """
        # 1. PROBE PHASE
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            head_sample = f.read(2000)
            
        if content_type == "AUTO":
            if re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', head_sample):
                content_type = "LOGS" 
            else:
                content_type = "NARRATIVE"
                
        # 2. DECOMPOSITION
        chunks = []
        if content_type == "LOGS":
            chunks = self._split_logs(file_path) 
        else:
            chunks = self._split_narrative(file_path)

        # 3. RECURSIVE WALKING (The Loop)
        running_state = {
            "trajectory_vector": [0,0,0], 
            "objects": {},                
            "current_context": ""         
        }
        
        logger.info(f"🚀 Starting RLM Walk on {content_type} file: {file_path}")

        for i, chunk in enumerate(chunks):
            prompt = f"""
            Objective: {objective}
            Previous Context: {running_state['current_context']}
            
            Task: detailed conceptual analysis.
            Treat the concepts in the text as REAL things in a real world. Discuss their implications, relationships, and contradictions.
            
            CRITICAL INSTRUCTIONS:
            1. In 'summary', write a purely qualitative narrative. Do NOT mention "vectors", "numbers", "representation", "JSON", or "processing". Speak ONLY of the ideas.
            2. In 'objects', extract key entities with a descriptive 'desc' field.
            3. 'vector' field is for internal use only - estimate the conceptual direction [x,y,z].
            
            Return VALID JSON ONLY with this exact schema:
            {{
                "summary": "The text explores [concept] which suggests that...",
                "vector": [0.1, 0.2, 0.3], 
                "objects": [
                    {{ "id": "ConceptName", "type": "concept", "mass": 1.0, "desc": "Detailed qualitative description of what this is and why it matters." }}
                ]
            }}
            """
            
            # Use Reasoning Phase (DeepSeek)
            tick_result = self.scheduler.run_reasoning_phase(context_text=chunk, prompt_template=prompt)
            self._update_state(running_state, tick_result)

        # 4. FINAL AGGREGATION
        solar_system = {
            "system_id": file_path,
            "gravity_well": {"concept": objective, "mass": len(chunks)}, 
            "objects": list(running_state['objects'].values()),
            "trajectory": running_state['trajectory_vector']
        }

        return solar_system

    def _split_logs(self, file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        return ["".join(lines[i:i+100]) for i in range(0, len(lines), 100)]

    def _split_narrative(self, file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        return text.split("\n\n")

    def _update_state(self, state, new_data):
        try:
            logger.info(f"LLM Raw Output for Chunk: {new_data[:500]}") # Debug logging
            # 1. Robust JSON extraction
            # Handle markdown blocks
            if "```json" in new_data:
                new_data = new_data.split("```json")[1].split("```")[0]
            elif "```" in new_data:
                new_data = new_data.split("```")[1].split("```")[0]
            
            # Handle Thinking process (DeepSeek specific)
            if "</think>" in new_data:
                new_data = new_data.split("</think>")[-1]
            
            # Clean up potential leading/trailing junk
            new_data = new_data.strip()
            
            # If still empty or definitely not JSON, try regex
            if not (new_data.startswith('{') or new_data.startswith('[')):
                matches = re.findall(r'\{.*\}', new_data, re.DOTALL)
                if matches:
                    new_data = matches[0]

            data = json.loads(new_data)
            
            # 2. Normalize data structure
            # If it's a list, assume it's the objects list
            if isinstance(data, list):
                logger.debug("LLM returned a list, normalizing to dictionary")
                data = {"objects": data}
            elif not isinstance(data, dict):
                logger.warning(f"Extracted data is not a dictionary or list: {type(data)}")
                return

            # Update trajectory
            state['trajectory_vector'] = data.get('vector', state['trajectory_vector'])
            state['current_context'] = data.get('summary', state['current_context'])
            
            # Update objects safely
            objs = data.get('objects', [])
            if isinstance(objs, list):
                logger.info(f"Ingested {len(objs)} objects from chunk")
                for obj in objs:
                    if isinstance(obj, dict):
                        # Ensure we have an ID
                        obj_id = obj.get('id') or obj.get('name') or f"concept_{len(state['objects'])}"
                        state['objects'][obj_id] = obj
            
        except Exception as e:
            logger.warning(f"RLM State Update failed: {e}")
            logger.info(f"Problematic JSON string: {new_data[:500]}...")
