import os
import logging
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

class Neo4jAdminTool:
    """
    MCP Tool for Neo4j Administration.
    Supports connectivity verification and Cypher query execution.
    """
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "arca_secure_password_change_me")

    def verify_connectivity(self) -> str:
        """Verify connectivity to the Neo4j database."""
        try:
            driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            driver.verify_connectivity()
            driver.close()
            return "Connected to Neo4j successfully"
        except Exception as e:
            return f"Failed to connect to Neo4j: {e}"

    def run_cypher(self, query: str) -> str:
        """Run a Cypher query against the Neo4j database."""
        try:
            driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            with driver.session() as session:
                result = session.run(query)
                data = [record.data() for record in result]
            driver.close()
            return str(data)
        except Exception as e:
            return f"Query failed: {e}"
