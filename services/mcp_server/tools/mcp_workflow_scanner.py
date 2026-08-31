import os
import logging
from typing import Dict, List
from neo4j import GraphDatabase
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("workflow-scanner")
logger = logging.getLogger(__name__)

class WorkflowScanner:
    """
    Scans project workflows from shared_storage and .agent directories.
    Maps them to the Knowledge Graph.
    Nodes: (Workflow {path, title})
    Rels: (Workflow)-[:REFERENCES]->(Service|Module|File)
    """
    
    def __init__(self):
        self.neo4j_uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
        self.neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        self.neo4j_password = os.environ.get("NEO4J_PASSWORD", "arca_password")
        self.driver = None
        # User requested shared_storage as primary location
        self.scan_dirs = [
            "/app/shared_storage",
            "/app/.agent/workflows"  # Keep legacy support
        ]

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

    def ingest_workflows(self):
        """Scan directories and populate graph."""
        summary = {"workflows": 0, "references": 0}
        driver = self._get_driver()
        
        with driver.session() as session:
            # Clear old workflows to avoid stale data
            # session.run("MATCH (w:Workflow) DETACH DELETE w") # Optional: risky if run concurrently
            
            for d in self.scan_dirs:
                if not os.path.exists(d):
                    logger.warning(f"Workflow directory not found: {d}")
                    continue
                    
                for root, _, files in os.walk(d):
                    for file in files:
                        if file.endswith(".md"):
                            path = os.path.join(root, file)
                            refs = self._process_workflow_file(session, path)
                            summary["workflows"] += 1
                            summary["references"] += refs
                            
        return summary

    def _process_workflow_file(self, session, path: str) -> int:
        """Parse MD file and create Node + Rels."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple title extraction (First H1)
            title = os.path.basename(path)
            for line in content.split('\n'):
                if line.startswith('# '):
                    title = line[2:].strip()
                    break
            
            # Create Node
            session.run("""
                MERGE (w:Workflow {path: $path})
                SET w.title = $title, w.updated_at = timestamp()
            """, path=path, title=title)
            
            # Extract References using Linker logic
            # 1. Mentions of Service references (e.g. `service: redis` or just `neural_system`)
            # 2. File references `[link](file://...)`
            
            refs_count = 0
            
            # Heuristic: Find words that match known Services
            # This requires fetching all services first
            services = [r["name"] for r in session.run("MATCH (s:Service) RETURN s.name as name")]
            
            for svc in services:
                if svc in content:
                    session.run("""
                        MATCH (w:Workflow {path: $path})
                        MATCH (s:Service {name: $svc})
                        MERGE (w)-[:REFERENCES]->(s)
                    """, path=path, svc=svc)
                    refs_count += 1
                    
            return refs_count
            
        except Exception as e:
            logger.error(f"Failed to process workflow {path}: {e}")
            return 0

@mcp.tool()
def scan_workflows() -> str:
    """Scan and index workflows from shared_storage into the graph."""
    scanner = WorkflowScanner()
    stats = scanner.ingest_workflows()
    return f"Scanned Workflows: {stats}"
