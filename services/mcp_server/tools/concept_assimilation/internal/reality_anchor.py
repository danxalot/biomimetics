from neo4j import GraphDatabase
import json
import logging
from tools.geometry_kernel.model_engine import CognitiveScheduler

logger = logging.getLogger(__name__)

class RealityAnchor:
    def __init__(self, neo4j_uri, neo4j_auth):
        self.driver = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
        self.scheduler = CognitiveScheduler()

    def enforce_truth(self, doc_text):
        """
        Scans a document for configuration claims and verifies them.
        """
        # 1. Extraction via DeepSeek
        prompt = """
        Extract system configuration details (Ports, IPs, Model Names, Services) from this text.
        Output ONLY JSON: [{"component": "service_name", "attribute": "port/ip/model", "value": "value"}]
        """
        response = self.scheduler.run_reasoning_phase(context_text=doc_text[:4000], prompt_template=prompt)
        
        try:
            # Clean markdown
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:-3]
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:-3]
                
            claims = json.loads(cleaned_response)
        except:
            return {"status": "SKIPPED", "report": "Could not parse document claims."}
        
        corrections = []
        
        # 2. Verification via Neo4j
        try:
            with self.driver.session() as session:
                for claim in claims:
                    # Cypher query: "Find Component X, return Attribute Y"
                    # Note: This implies a specific graph schema. 
                    # We use a broad generic match for robustness in this V1 implementation.
                    cypher = f"""
                    MATCH (c:Component {{name: '{claim['component']}'}}) 
                    RETURN c.{claim['attribute']} as actual
                    """
                    result = session.run(cypher).single()
                    
                    if result:
                        actual = result['actual']
                        claimed = claim['value']
                        
                        if str(actual) != str(claimed) and actual is not None:
                                corrections.append(
                                    f"❌ MISMATCH: {claim['component']} {claim['attribute']} "
                                    f"(Doc: {claimed} vs Reality: {actual})"
                                )
        except Exception as e:
            logger.error(f"Neo4j Verification Failed: {e}")
            return {"status": "ERROR", "report": f"Neo4j Error: {str(e)}"}
        
        if corrections:
            return {"status": "OUTDATED", "report": corrections}
        return {"status": "VERIFIED", "report": "Document aligns with Live System."}

    def close(self):
        self.driver.close()
