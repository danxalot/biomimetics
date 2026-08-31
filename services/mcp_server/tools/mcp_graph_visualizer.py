import os
import logging
import json
from typing import Dict, List, Any, Optional
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

class GraphVisualizer:
    """
    Generates Mermaid diagram syntax from Neo4j graph queries.
    Optionally enriches with episodic memory context.
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
    
    def generate_mermaid(self, focus: str, graph_type: str = "infrastructure") -> str:
        """
        Generate Mermaid diagram for a specific focus area.
        
        Args:
            focus: Entity to focus on (e.g., 'mcp_server', 'UserInteractionAgent')
            graph_type: 'infrastructure', 'logic', 'full'
            
        Returns:
            Mermaid diagram syntax as string
        """
        try:
            if graph_type == "infrastructure":
                return self._generate_infrastructure_diagram(focus)
            elif graph_type == "logic":
                return self._generate_logic_diagram(focus)
            elif graph_type == "full":
                return self._generate_full_diagram(focus)
            else:
                return "graph TD\n    A[Unknown graph type]"
                
        except Exception as e:
            logger.error(f"Mermaid generation failed: {e}")
            return f"graph TD\n    Error[\"Generation failed: {e}\"]"
    
    def _generate_infrastructure_diagram(self, service_name: str) -> str:
        """Generate diagram for Infrastructure layer (Service -> Port/Volume)."""
        driver = self._get_driver()
        
        with driver.session() as session:
            # Query for service and its relationships
            result = session.run("""
                MATCH (s:Service {name: $name})
                OPTIONAL MATCH (s)-[:EXPOSES]->(p:Port)
                OPTIONAL MATCH (s)-[:MOUNTS]->(v:Volume)
                OPTIONAL MATCH (s)-[:CONFIGURED_BY]->(e:EnvVar)
                RETURN s, collect(DISTINCT p) as ports, 
                       collect(DISTINCT v) as volumes,
                       count(DISTINCT e) as env_count
            """, name=service_name)
            
            record = result.single()
            if not record:
                return f"graph TD\n    NotFound[\"Service '{service_name}' not found\"]"
            
            service = record["s"]
            ports = record["ports"]
            volumes = record["volumes"]
            env_count = record["env_count"]
            
            # Build Mermaid syntax
            lines = ["graph TD"]
            lines.append(f"    S[\"{service['name']}<br/>Container\"]")
            lines.append(f"    style S fill:#f9f,stroke:#333,stroke-width:3px")
            
            # Add ports
            for i, port in enumerate(ports):
                if port:
                    port_id = f"P{i}"
                    lines.append(f"    {port_id}[\"Port {port['number']}\"]")
                    lines.append(f"    S -->|EXPOSES| {port_id}")
                    lines.append(f"    style {port_id} fill:#bbf,stroke:#333")
            
            # Add volumes (limit to first 3)
            for i, vol in enumerate(volumes[:3]):
                if vol:
                    vol_id = f"V{i}"
                    host_path = vol.get('host_path', 'unknown')[:20]
                    lines.append(f"    {vol_id}[\"📁 {host_path}...\"]")
                    lines.append(f"    S -->|MOUNTS| {vol_id}")
                    lines.append(f"    style {vol_id} fill:#afa,stroke:#333")
            
            # Add env vars summary
            if env_count > 0:
                lines.append(f"    E[\"⚙️ {env_count} Env Vars\"]")
                lines.append(f"    S -.-|CONFIGURED_BY| E")
                lines.append(f"    style E fill:#ffa,stroke:#333")
            
            return "\n".join(lines)
    
    def _generate_logic_diagram(self, entity_name: str) -> str:
        """Generate diagram for Logic layer (Service -> Tool -> Function or Agent -> Workflow)."""
        driver = self._get_driver()
        
        with driver.session() as session:
            # Try as Service first
            result = session.run("""
                MATCH (s:Service {name: $name})-[:PROVIDES_TOOL]->(t:Tool)
                OPTIONAL MATCH (t)-[:IMPLEMENTED_BY]->(f:Function)
                RETURN s, collect({tool: t, func: f}) as tools
                LIMIT 10
            """, name=entity_name)
            
            record = result.single()
            if record and record["tools"]:
                return self._build_service_tools_diagram(record)
            
            # Try as Agent
            result = session.run("""
                MATCH (a:Agent {name: $name})-[:HAS_WORKFLOW]->(w:WorkflowNode)
                OPTIONAL MATCH (w)-[:TRANSITIONS_TO]->(next:WorkflowNode)
                RETURN a, collect({node: w, next: collect(next)}) as workflow
            """, name=entity_name)
            
            record = result.single()
            if record and record["workflow"]:
                return self._build_agent_workflow_diagram(record)
            
            return f"graph TD\n    NotFound[\"Entity '{entity_name}' not found in Logic layer\"]"
    
    def _build_service_tools_diagram(self, record) -> str:
        """Build diagram for Service -> Tools -> Functions."""
        lines = ["graph TD"]
        service = record["s"]
        tools = record["tools"]
        
        lines.append(f"    S[\"{service['name']}\"]")
        lines.append(f"    style S fill:#f9f,stroke:#333,stroke-width:3px")
        
        for i, item in enumerate(tools[:10]):  # Limit to 10 tools
            tool = item.get("tool")
            func = item.get("func")
            
            if tool:
                tool_id = f"T{i}"
                tool_name = tool.get("name", "unknown")
                lines.append(f"    {tool_id}[\"{tool_name}\"]")
                lines.append(f"    S -->|PROVIDES| {tool_id}")
                lines.append(f"    style {tool_id} fill:#bbf,stroke:#333")
                
                if func:
                    func_id = f"F{i}"
                    func_name = func.get("name", "unknown")
                    lines.append(f"    {func_id}[\"{func_name}()\"]")
                    lines.append(f"    {tool_id} -->|IMPL| {func_id}")
                    lines.append(f"    style {func_id} fill:#afa,stroke:#333")
        
        return "\n".join(lines)
    
    def _build_agent_workflow_diagram(self, record) -> str:
        """Build diagram for Agent -> WorkflowNodes -> Transitions."""
        lines = ["graph LR"]
        agent = record["a"]
        workflow = record["workflow"]
        
        lines.append(f"    A[\"{agent['name']} Agent\"]")
        lines.append(f"    style A fill:#f9f,stroke:#333,stroke-width:3px")
        
        node_ids = {}
        for i, item in enumerate(workflow):
            node = item.get("node")
            if node:
                node_id = f"N{i}"
                node_name = node.get("name", "unknown")
                node_ids[node_name] = node_id
                lines.append(f"    {node_id}[\"{node_name}\"]")
                lines.append(f"    style {node_id} fill:#bbf,stroke:#333")
        
        # Add transitions
        for item in workflow:
            node = item.get("node")
            next_nodes = item.get("next", [])
            if node and node.get("name") in node_ids:
                from_id = node_ids[node.get("name")]
                for next_node in next_nodes:
                    if next_node and next_node.get("name") in node_ids:
                        to_id = node_ids[next_node.get("name")]
                        lines.append(f"    {from_id} --> {to_id}")
        
        return "\n".join(lines)
    
    def _generate_full_diagram(self, focus: str) -> str:
        """Generate full multi-layer diagram."""
        # TODO: Combine Infrastructure + Logic layers
        return self._generate_logic_diagram(focus)


# Singleton
graph_visualizer = GraphVisualizer()
