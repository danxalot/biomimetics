import os
import ast
import logging
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

class LogicGraphDiscovery:
    """
    Discovers and maps MCP Tools and Skills into Neo4j Logic Graph.
    Links functional architecture to Infrastructure Layer.
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
    
    def _create_logic_schema(self, tx):
        """Create constraints and indexes for Logic Graph including LangGraph entities."""
        constraints = [
            "CREATE CONSTRAINT tool_name IF NOT EXISTS FOR (t:Tool) REQUIRE t.name IS UNIQUE",
            "CREATE CONSTRAINT function_signature IF NOT EXISTS FOR (f:Function) REQUIRE (f.name, f.file) IS UNIQUE",
            "CREATE INDEX skill_name IF NOT EXISTS FOR (s:Skill) ON (s.name)",
            "CREATE CONSTRAINT agent_name IF NOT EXISTS FOR (a:Agent) REQUIRE a.name IS UNIQUE",
            "CREATE INDEX workflow_node IF NOT EXISTS FOR (w:WorkflowNode) ON (w.name)",
        ]
        
        for constraint in constraints:
            try:
                tx.run(constraint)
            except Exception as e:
                logger.warning(f"Constraint setup warning: {e}")
    
    def _clear_logic_graph(self, tx):
        """Clear existing Logic nodes including LangGraph structures."""
        tx.run("""
            MATCH (n)
            WHERE n:Tool OR n:Function OR n:Skill OR n:Agent OR n:WorkflowNode OR n:WorkflowEdge
            DETACH DELETE n
        """)
        logger.info("Cleared existing Logic graph.")
    
    def discover_tools(self, tools_dir: str = "/app/tools") -> Dict[str, Any]:
        """
        Scan tools directory and extract function metadata using AST.
        
        Args:
            tools_dir: Path to mcp_server/tools directory
            
        Returns:
            Summary of discovered tools and functions
        """
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                session.execute_write(self._create_logic_schema)
                session.execute_write(self._clear_logic_graph)
                
                summary = {
                    "files_scanned": 0,
                    "functions_discovered": 0,
                    "classes_discovered": 0
                }
                
                # Scan all Python files
                for root, dirs, files in os.walk(tools_dir):
                    for file in files:
                        if file.endswith('.py') and not file.startswith('__'):
                            filepath = os.path.join(root, file)
                            summary["files_scanned"] += 1
                            
                            file_summary = self._process_tool_file(session, filepath)
                            summary["functions_discovered"] += file_summary.get("functions", 0)
                            summary["classes_discovered"] += file_summary.get("classes", 0)
                
                # Link tools to mcp_server service
                self._link_tools_to_service(session)
                
                logger.info(f"Logic graph discovery complete: {summary}")
                return summary
                
        except Exception as e:
            logger.error(f"Tool discovery failed: {e}")
            raise
    
    def _process_tool_file(self, session, filepath: str) -> Dict[str, int]:
        """Parse a Python file using AST and extract metadata."""
        try:
            with open(filepath, 'r') as f:
                source = f.read()
            
            tree = ast.parse(source)
            summary = {"functions": 0, "classes": 0}
            
            # Extract module docstring
            module_doc = ast.get_docstring(tree) or ""
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self._create_function_node(session, node, filepath, module_doc)
                    summary["functions"] += 1
                    
                    # If this is a tool function (has specific decorator or naming pattern)
                    if self._is_tool_function(node):
                        self._create_tool_from_function(session, node, filepath)
                
                elif isinstance(node, ast.ClassDef):
                    summary["classes"] += 1
                    # Future: Extract class metadata
            
            return summary
            
        except Exception as e:
            logger.warning(f"Failed to parse {filepath}: {e}")
            return {"functions": 0, "classes": 0}
    
    def _is_tool_function(self, node: ast.FunctionDef) -> bool:
        """Heuristic to detect tool functions."""
        # Look for @tool decorator or specific naming patterns
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == 'tool':
                return True
        
        # Tool functions often have specific prefixes
        if node.name.startswith('mcp_') or node.name.endswith('_tool'):
            return True
            
        return False
    
    def _create_function_node(self, session, node: ast.FunctionDef, filepath: str, module_doc: str):
        """Create a Function node in Neo4j."""
        def create_node(tx, name, file, sig, doc):
            tx.run("""
                MERGE (f:Function {name: $name, file: $file})
                SET f.signature = $sig,
                    f.docstring = $doc,
                    f.line_start = $line,
                    f.updated_at = timestamp()
            """, name=name, file=file, sig=sig, doc=doc, line=node.lineno)
        
        # Extract function signature
        args = [arg.arg for arg in node.args.args]
        signature = f"{node.name}({', '.join(args)})"
        docstring = ast.get_docstring(node) or module_doc
        
        session.execute_write(create_node, node.name, filepath, signature, docstring)
    
    def _create_tool_from_function(self, session, node: ast.FunctionDef, filepath: str):
        """Create a Tool node and link to Function."""
        def create_tool_and_link(tx, tool_name, func_name, file, doc):
            # Create Tool node
            tx.run("""
                MERGE (t:Tool {name: $name})
                SET t.description = $desc,
                    t.source_file = $file,
                    t.updated_at = timestamp()
            """, name=tool_name, desc=doc, file=file)
            
            # Link Tool to Function
            tx.run("""
                MATCH (t:Tool {name: $tool_name})
                MATCH (f:Function {name: $func_name, file: $file})
                MERGE (t)-[:IMPLEMENTED_BY]->(f)
            """, tool_name=tool_name, func_name=func_name, file=file)
        
        tool_name = node.name.replace('_tool', '').replace('mcp_', '')
        docstring = ast.get_docstring(node) or f"Tool: {node.name}"
        
        session.execute_write(create_tool_and_link, tool_name, node.name, filepath, docstring)
    
    def _link_tools_to_service(self, session):
        """Link all discovered Tools to mcp_server Service."""
        def create_service_links(tx):
            tx.run("""
                MATCH (s:Service {name: 'mcp_server'})
                MATCH (t:Tool)
                WHERE NOT (s)-[:PROVIDES_TOOL]->(t)
                MERGE (s)-[:PROVIDES_TOOL]->(t)
            """)
        
        session.execute_write(create_service_links)
        logger.info("Linked Tools to mcp_server Service.")
    
    def query_logic_graph(self, query: str) -> List[Dict]:
        """Run a Cypher query against the Logic graph."""
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(query)
            return [dict(record) for record in result]
    
    def discover_agents(self, agents_dir: str = "/app/../agent_service") -> Dict[str, Any]:
        """
        Scan agent files and extract LangGraph workflow structures.
        
        Args:
            agents_dir: Path to agent_service directory
            
        Returns:
            Summary of discovered agents and workflows
        """
        try:
            driver = self._get_driver()
            
            with driver.session() as session:
                summary = {
                    "agents_discovered": 0,
                    "workflow_nodes": 0,
                    "workflow_edges": 0
                }
                
                # Scan agent files
                agent_files = [
                    "user_interaction_agent.py",
                    "langgraph_agent.py"
                ]
                
                for agent_file in agent_files:
                    filepath = os.path.join(agents_dir, agent_file)
                    if os.path.exists(filepath):
                        agent_summary = self._process_agent_file(session, filepath)
                        summary["agents_discovered"] += agent_summary.get("agents", 0)
                        summary["workflow_nodes"] += agent_summary.get("nodes", 0)
                        summary["workflow_edges"] += agent_summary.get("edges", 0)
                
                logger.info(f"Agent discovery complete: {summary}")
                return summary
                
        except Exception as e:
            logger.error(f"Agent discovery failed: {e}")
            raise
    
    def _process_agent_file(self, session, filepath: str) -> Dict[str, int]:
        """Parse an agent file and extract LangGraph workflow structures."""
        try:
            with open(filepath, 'r') as f:
                source = f.read()
            
            tree = ast.parse(source)
            summary = {"agents": 0, "nodes": 0, "edges": 0}
            
            # Find agent class definitions
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Look for classes that define agents (have workflow methods)
                    if self._is_agent_class(node):
                        agent_name = node.name.replace("Agent", "")
                        self._create_agent_node(session, agent_name, filepath)
                        summary["agents"] += 1
                        
                        # Extract workflow nodes from _build_workflow or similar methods
                        workflow_summary = self._extract_workflow(session, node, agent_name, source)
                        summary["nodes"] += workflow_summary.get("nodes", 0)
                        summary["edges"] += workflow_summary.get("edges", 0)
            
            return summary
            
        except Exception as e:
            logger.warning(f"Failed to parse agent file {filepath}: {e}")
            return {"agents": 0, "nodes": 0, "edges": 0}
    
    def _is_agent_class(self, node: ast.ClassDef) -> bool:
        """Check if class is an agent definition."""
        return "Agent" in node.name or any(
            isinstance(base, ast.Name) and "Agent" in base.id
            for base in node.bases
        )
    
    def _create_agent_node(self, session, agent_name: str, filepath: str):
        """Create Agent node in Neo4j."""
        def create_node(tx, name, file):
            tx.run("""
                MERGE (a:Agent {name: $name})
                SET a.source_file = $file,
                    a.updated_at = timestamp()
            """, name=name, file=file)
        
        session.execute_write(create_node, agent_name, filepath)
    
    def _extract_workflow(self, session, class_node: ast.ClassDef, agent_name: str, source: str) -> Dict[str, int]:
        """Extract workflow nodes and edges from agent class."""
        summary = {"nodes": 0, "edges": 0}
        
        # Look for add_node calls in source code (simple heuristic)
        # In production, we'd use more sophisticated AST analysis
        if "add_node" in source:
            # Extract node names from add_node calls
            import re
            node_matches = re.findall(r'add_node\(["\'](\w+)["\']', source)
            edge_matches = re.findall(r'add_edge\(["\'](\w+)["\'],\s*["\'](\w+)["\']', source)
            
            # Create workflow nodes
            for node_name in set(node_matches):
                self._create_workflow_node(session, agent_name, node_name)
                summary["nodes"] += 1
            
            # Create edges
            for from_node, to_node in edge_matches:
                self._create_workflow_edge(session, agent_name, from_node, to_node)
                summary["edges"] += 1
        
        return summary
    
    def _create_workflow_node(self, session, agent_name: str, node_name: str):
        """Create WorkflowNode and link to Agent."""
        def create_and_link(tx, agent, node):
            tx.run("""
                MERGE (w:WorkflowNode {name: $node, agent: $agent})
                SET w.updated_at = timestamp()
            """, agent=agent, node=node)
            
            tx.run("""
                MATCH (a:Agent {name: $agent})
                MATCH (w:WorkflowNode {name: $node, agent: $agent})
                MERGE (a)-[:HAS_WORKFLOW]->(w)
            """, agent=agent, node=node)
        
        session.execute_write(create_and_link, agent_name, node_name)
    
    def _create_workflow_edge(self, session, agent_name: str, from_node: str, to_node: str):
        """Create edge between workflow nodes."""
        def create_edge(tx, agent, from_node_name, to_node_name):
            tx.run("""
                MATCH (from:WorkflowNode {name: $from_node, agent: $agent})
                MATCH (to:WorkflowNode {name: $to_node, agent: $agent})
                MERGE (from)-[:TRANSITIONS_TO]->(to)
            """, agent=agent, from_node=from_node_name, to_node=to_node_name)
        
        session.execute_write(create_edge, agent_name, from_node, to_node)


# Singleton
logic_discovery = LogicGraphDiscovery()
