import os
import logging
from neo4j import GraphDatabase
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Tool (Can be called to trigger linking manually)
mcp = FastMCP("graph-linker")
logger = logging.getLogger(__name__)

class GraphLinker:
    """
    Bridges the gap between Infrastructure (Service) and Code (Module) graphs in Neo4j.
    Creates semantic relationships:
    - (:Service)-[:IMPLEMENTED_BY]->(:Module)
    - (:Service)-[:CONFIGURED_BY]->(:EnvVar) (Already in infra, but ensuring consistency)
    """
    
    def __init__(self):
        self.neo4j_uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
        self.neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        self.neo4j_password = os.environ.get("NEO4J_PASSWORD", "arca_password")
        self.driver = None

    def _get_driver(self):
        if self.driver is None:
            try:
                self.driver = GraphDatabase.driver(
                    self.neo4j_uri,
                    auth=(self.neo4j_user, self.neo4j_password)
                )
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise
        return self.driver

    def link_services_to_code(self):
        """
        Heuristic: Link Service to Code based on Volume Mounts.
        If Service mounts ./services/foo:/app, and Module has path .../services/foo/main.py,
        Then Service IMPLEMENTED_BY Module.
        """
        query = """
        MATCH (s:Service)-[:MOUNTS]->(v:Volume)
        MATCH (m:Module)
        WHERE v.host_path IS NOT NULL AND (CASE WHEN m.path IS NOT NULL THEN m.path ELSE "" END) CONTAINS v.host_path
        MERGE (s)-[:IMPLEMENTED_BY]->(m)
        RETURN count(*) as links
        """
        
        # Fallback Heuristic: Name Matching
        # If Service name "neural_system" appears in Module path "services/neural_system/api.py"
        query_name = """
        MATCH (s:Service), (m:Module)
        WHERE (CASE WHEN m.path IS NOT NULL THEN m.path ELSE "" END) CONTAINS s.name
        MERGE (s)-[:IMPLEMENTED_BY]->(m)
        RETURN count(*) as links
        """
        
        driver = self._get_driver()
        with driver.session() as session:
            r1 = session.run(query).single()["links"]
            r2 = session.run(query_name).single()["links"]
            logger.info(f"Graph Linker: Created {r1} volume-based links and {r2} name-based links.")
            return {"volume_links": r1, "name_links": r2}

@mcp.tool()
def run_graph_linking() -> str:
    """
    Trigger the Graph Linker to update relationships between Infrastructure and Code.
    Run this after infrastructure discovery or code crawling.
    """
    try:
        linker = GraphLinker()
        stats = linker.link_services_to_code()
        return f"Linker Complete: {stats}"
    except Exception as e:
        return f"Linker Failed: {str(e)}"

if __name__ == "__main__":
    # Allow running as standalone script
    logging.basicConfig(level=logging.INFO)
    print(run_graph_linking())
