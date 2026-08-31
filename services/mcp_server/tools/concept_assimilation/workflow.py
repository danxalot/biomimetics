# Orchestrator for Concept Assimilation
import os
import redis
import logging

logger = logging.getLogger(__name__)

from .internal.gateway import classify_intent
from .internal.atomizer import DocumentAtomizer
from .internal.reality_anchor import RealityAnchor
from .internal.physics import ParticlePhysicsEngine
from .internal.architect import SystemArchitect
from .internal.gateway_client import GatewayClient
from .internal.atomizer import DocumentAtomizer
from .internal.reality_anchor import RealityAnchor
from .internal.physics import ParticlePhysicsEngine
from .internal.architect import SystemArchitect

# Embedding utility - using the one from mcp_server if available, or lightweight local
# For now, we reuse the Atomizer's scheduler logic or a simple placeholder 
# since we don't have a dedicated "mcp_embedding" module exposed easily yet.
# We will use the 'embed_text' tool logic if we can, or just mock it for V1.
# Actually, the user asked for using "Qwen 0.6B (Local)" or similar. 
# We'll use the existing 'mcp_vision_encoder' or simply fetch embeddings from the gateway.

def get_embedding_mock(text):
    # Placeholder: In production, call real embedding model
    # Returning random vector for structure verify
    import numpy as np
    return np.random.rand(384).tolist()

def run_granular_assimilation(doc_files, current_state_atoms, redis_url="redis://redis:6379"):
    """
    Main Pipeline Entry Point.
    Returns: The final synthesized markdown.
    """
    
    # 1. Initialize Tools / Clients
    r = redis.from_url(redis_url, decode_responses=True)
    
    # Neo4j Config
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_pass = os.environ.get("NEO4J_PASSWORD", "password")
    
    # LLM Config (Architect) - Routes through LLM Gateway (Gemma/Qwen)
    architect_llm = GatewayClient()
    
    atomizer = DocumentAtomizer()
    physics = ParticlePhysicsEngine(r)
    architect = SystemArchitect(architect_llm)
    reality_check = RealityAnchor(neo4j_uri, (neo4j_user, neo4j_pass))
    
    future_atoms_pool = []
    outdated_reports = []
    
    # 2. Ingest & Atomize All Documents
    for doc in doc_files:
        content = doc['text']
        filename = doc['name']
        
        # A. Gateway Check
        intent = classify_intent(content, filename)
        
        if intent == "REALITY_CHECK":
            # Strict Mode
            check_result = reality_check.enforce_truth(content)
            if check_result['status'] == "OUTDATED":
                # We do not add outdated reality docs to the pool
                outdated_reports.append(f"Doc {filename} rejected: {check_result['report']}")
                continue
        
        # B. Atomization (Explosion)
        try:
            atoms = atomizer.explode_document(content, filename)
            logger.info(f"Atomizer produced {len(atoms)} atoms from {filename}")
        except Exception as e:
            logger.error(f"Atomization failed for {filename}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            outdated_reports.append(f"Atomization error for {filename}: {str(e)}")
            continue
        
        # C. Vectorization
        for atom in atoms:
            # TODO: Replace with real embedding call
            atom['vector'] = get_embedding_mock(atom['concept']) 
            future_atoms_pool.append(atom)

    # 3. Physics Simulation (The Collision)
    try:
        logger.info(f"Starting physics simulation with {len(future_atoms_pool)} atoms")
        simulation_result = physics.assimilate_atoms(current_state_atoms, future_atoms_pool)
        logger.info(f"Physics simulation complete: {len(simulation_result['accepted'])} accepted, {len(simulation_result['rejected'])} rejected")
    except Exception as e:
        logger.error(f"Physics simulation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"## Physics Simulation Error\n\n{str(e)}"
    
    # 4. Synthesis (The Report)
    try:
        logger.info("Starting architect synthesis...")
        final_doc = architect.synthesize_solution(
            winning_atoms=simulation_result['accepted'], 
            rejected_log=simulation_result['rejected']
        )
        logger.info(f"Synthesis complete: {len(final_doc)} chars")
    except Exception as e:
        logger.error(f"Architect synthesis failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"## Synthesis Error\n\n{str(e)}"

    
    # Add any outdated reports to the top
    if outdated_reports:
        prefix = "## ⚠️ Outdated Documents Excluded\n" + "\n".join(outdated_reports) + "\n\n---\n\n"
        final_doc = prefix + final_doc
        
    return final_doc

# Cleanup
# reality_check.close() # Handle in finally block in production
