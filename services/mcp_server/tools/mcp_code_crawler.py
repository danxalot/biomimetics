import os
import ast
import logging
import json
from typing import Dict, List, Any, Set
from pathlib import Path
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

class CodeCrawler:
    """
    Crawls codeb

ase to build dependency graph in Neo4j (Phase 3).
    Extracts modules, classes, functions, imports, and relationships.
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
    
    def _create_code_schema(self, tx):
        """Create constraints for Code Graph."""
        constraints = [
            "CREATE CONSTRAINT module_path IF NOT EXISTS FOR (m:Module) REQUIRE m.path IS UNIQUE",
            "CREATE INDEX class_name IF NOT EXISTS FOR (c:Class) ON (c.name)",
            "CREATE INDEX import_name IF NOT EXISTS FOR (i:Import) ON (i.module_name)",
        ]
        
        for constraint in constraints:
            try:
                tx.run(constraint)
            except Exception as e:
                logger.warning(f"Constraint setup warning: {e}")
    
    def _clear_code_graph(self, tx):
        """Clear existing Code graph nodes."""
        tx.run("""
            MATCH (n)
            WHERE n:Module OR n:Import
            DETACH DELETE n
        """)
        logger.info("Cleared existing Code graph.")
    
    def crawl_codebase(self, start_dir: str = "/app") -> Dict[str, Any]:
        """
        Crawl codebase and build dependency graph.
        
        Args:
            start_dir: Root directory to start crawling
            
        Returns:
            Summary of crawled code
        """
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                session.execute_write(self._create_code_schema)
                session.execute_write(self._clear_code_graph)
                
                summary = {
                    "modules_found": 0,
                    "imports_found": 0,
                    "classes_found": 0
                }
                
                # Walk directory
                for root, dirs, files in os.walk(start_dir):
                    # Skip common non-code directories
                    dirs[:] = [d for d in dirs if d not in {
                        '__pycache__', '.git', 'node_modules', 'venv', '.venv', 
                        'build', 'dist', '.pytest_cache'
                    }]
                    
                    for file in files:
                        if file.endswith('.py'):
                            filepath = os.path.join(root, file)
                            module_summary = self._process_module(session, filepath, start_dir)
                            summary["modules_found"] += 1
                            summary["imports_found"] += module_summary.get("imports", 0)
                            summary["classes_found"] += module_summary.get("classes", 0)
                
                logger.info(f"Code crawl complete: {summary}")
                return summary
                
        except Exception as e:
            logger.error(f"Code crawl failed: {e}")
            raise
    
    def _process_module(self, session, filepath: str, base_dir: str) -> Dict[str, int]:
        """Process a single Python module."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            
            # Get module path relative to base_dir
            rel_path = os.path.relpath(filepath, base_dir)
            module_name = rel_path.replace('/', '.').replace('.py', '')
            
            # Create module node
            self._create_module_node(session, module_name, filepath)
            
            summary = {"imports": 0, "classes": 0}
            
            # Extract imports and classes
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports = self._extract_imports(node)
                    for imp in imports:
                        self._create_import_relationship(session, module_name, imp)
                        summary["imports"] += 1
                
                elif isinstance(node, ast.ClassDef):
                    # Just count classes for now (detailed class graph later)
                    summary["classes"] += 1
            
            return summary
            
        except Exception as e:
            logger.warning(f"Failed to process {filepath}: {e}")
            return {"imports": 0, "classes": 0}
    
    def _create_module_node(self, session, module_name: str, filepath: str):
        """Create Module node."""
        def create_node(tx, name, path):
            tx.run("""
                MERGE (m:Module {path: $path})
                SET m.name = $name,
                    m.updated_at = timestamp()
            """, name=module_name, path=filepath)
        
        session.execute_write(create_node, module_name, filepath)
    
    def _extract_imports(self, node) -> List[str]:
        """Extract import module names from AST node."""
        imports = []
        
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        
        return imports
    
    def _create_import_relationship(self, session, from_module: str, to_module: str):
        """Create IMPORTS relationship."""
        def create_rel(tx, from_m, to_m):
            tx.run("""
                MATCH (from:Module {name: $from_m})
                MERGE (to:Import {module_name: $to_m})
                MERGE (from)-[:IMPORTS]->(to)
            """, from_m=from_module, to_m=to_module)
        
        session.execute_write(create_rel, from_module, to_module)
    
    def query_code_graph(self, query: str) -> List[Dict]:
        """Query the Code graph."""
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(query)
            return [dict(record) for record in result]


# Singleton
code_crawler = CodeCrawler()

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("code-crawler")

@mcp.tool()
def crawl_codebase(start_dir: str = "/app") -> str:
    """Crawl codebase and build dependency graph."""
    try:
        summary = code_crawler.crawl_codebase(start_dir)
        return f"Code Crawl Complete: {summary}"
    except Exception as e:
        return f"Crawl failed: {e}"
