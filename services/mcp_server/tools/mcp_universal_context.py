import os
import json
import logging
from neo4j import GraphDatabase
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("universal-context")
logger = logging.getLogger(__name__)

class UniversalContextEngine:
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

    def get_context(self, subject: str, radius: int = 4) -> dict:
        """
        Retrieve specialized context frame around a subject.
        """
        driver = self._get_driver()
        
        # Cypher to find subject (Fuzzy Match) and traverse
        query = f"""
        MATCH (start)
        WHERE (start.name CONTAINS $subject OR start.path CONTAINS $subject)
        WITH start LIMIT 1
        CALL apoc.path.subgraphAll(start, {{maxLevel: {radius}}})
        YIELD nodes, relationships
        RETURN start, nodes, relationships
        """
        
        with driver.session() as session:
            try:
                result = session.run(query, subject=subject).single()
                if not result:
                    return {"error": f"Subject '{subject}' not found in Knowledge Graph."}
                
                start_node = dict(result["start"])
                all_nodes = [dict(n) for n in result["nodes"]]
                all_rels = [{
                    "start": r.start_node["name"] if "name" in r.start_node else r.start_node.get("path", "unknown"),
                    "type": r.type,
                    "end": r.end_node["name"] if "name" in r.end_node else r.end_node.get("path", "unknown")
                } for r in result["relationships"]]
                
                # Structure the output
                frame = {
                    "subject": start_node.get("name") or start_node.get("path"),
                    "type": list(result["start"].labels)[0],
                    "context": {
                        "nodes": len(all_nodes),
                        "radius": radius
                    },
                    "graph": {
                        "nodes": all_nodes,
                        "relationships": all_rels
                    }
                }
                
                return frame
            except Exception as e:
                logger.error(f"Context query failed: {e}")
                return {"error": str(e)}

@mcp.tool()
def get_universal_context(subject: str, radius: int = 4) -> str:
    """
    Retrieve specialized context frame around a subject.
    Radius determines the depth of the graph traversal (default 4).
    """
    engine = UniversalContextEngine()
    # Headers should be passed if available in context, but following the pattern for now:
    frame = engine.get_context(subject, radius)
    return json.dumps(frame, indent=2)
