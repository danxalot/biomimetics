import os
import logging
import yaml
from typing import Dict, List, Any
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

class InfrastructureDiscovery:
    """
    Discovers and maps infrastructure from docker-compose to Neo4j.
    Creates a comprehensive system graph of Services, Ports, Volumes, and Environment Variables.
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
    
    def _create_schema(self, tx):
        """Create constraints and indexes for the Infrastructure Graph."""
        # Constraints ensure uniqueness
        constraints = [
            "CREATE CONSTRAINT service_name IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE",
            "CREATE CONSTRAINT port_number IF NOT EXISTS FOR (p:Port) REQUIRE p.number IS UNIQUE",
            "CREATE INDEX service_image IF NOT EXISTS FOR (s:Service) ON (s.image)",
        ]
        
        for constraint in constraints:
            try:
                tx.run(constraint)
            except Exception as e:
                logger.warning(f"Constraint already exists or failed: {e}")
    
    def _clear_infrastructure_graph(self, tx):
        """Clear existing Infrastructure nodes to ensure fresh data."""
        tx.run("""
            MATCH (n)
            WHERE n:Service OR n:Port OR n:Volume OR n:EnvVar
            DETACH DELETE n
        """)
        logger.info("Cleared existing Infrastructure graph.")
    
    def discover_from_compose(self, compose_path: str, env_path: str = None) -> Dict[str, Any]:
        """
        Parse docker-compose file and populate Neo4j.
        
        Args:
            compose_path: Path to docker-compose.yml
            env_path: Optional path to .env file
            
        Returns:
            Summary of discovered infrastructure
        """
        try:
            # Load docker-compose
            with open(compose_path, 'r') as f:
                compose_data = yaml.safe_load(f)
            
            # Load .env if provided
            env_vars = {}
            if env_path and os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip()
            
            driver = self._get_driver()
            
            with driver.session() as session:
                # Create schema
                session.execute_write(self._create_schema)
                
                # Clear old data
                session.execute_write(self._clear_infrastructure_graph)
                
                # Process services
                services = compose_data.get('services', {})
                summary = {
                    "services_discovered": 0,
                    "ports_mapped": 0,
                    "volumes_mapped": 0,
                    "env_vars_mapped": 0
                }
                
                for service_name, service_config in services.items():
                    self._process_service(session, service_name, service_config, env_vars)
                    summary["services_discovered"] += 1
                    
                    # Count ports
                    if 'ports' in service_config:
                        summary["ports_mapped"] += len(service_config['ports'])
                    
                    # Count volumes
                    if 'volumes' in service_config:
                        summary["volumes_mapped"] += len(service_config['volumes'])
                    
                    # Count env vars
                    if 'environment' in service_config:
                        summary["env_vars_mapped"] += len(service_config['environment'])
                
                logger.info(f"Infrastructure discovery complete: {summary}")
                return summary
                
        except Exception as e:
            logger.error(f"Infrastructure discovery failed: {e}")
            raise
    
    def _process_service(self, session, service_name: str, config: Dict, global_env: Dict):
        """Process a single service and create its graph."""
        
        def create_service_node(tx, name, config):
            tx.run("""
                MERGE (s:Service {name: $name})
                SET s.image = $image,
                    s.container_name = $container_name,
                    s.updated_at = timestamp()
            """, name=name, 
                image=config.get('image', 'unknown'),
                container_name=config.get('container_name', name))
        
        session.execute_write(create_service_node, service_name, config)
        
        # Process ports
        if 'ports' in config:
            for port_mapping in config['ports']:
                self._process_port(session, service_name, port_mapping)
        
        # Process volumes
        if 'volumes' in config:
            for volume_mapping in config['volumes']:
                self._process_volume(session, service_name, volume_mapping)
        
        # Process environment variables
        if 'environment' in config:
            env_list = config['environment']
            if isinstance(env_list, list):
                for env_entry in env_list:
                    if '=' in env_entry:
                        key, value = env_entry.split('=', 1)
                        self._process_env_var(session, service_name, key, value)
            elif isinstance(env_list, dict):
                for key, value in env_list.items():
                    self._process_env_var(session, service_name, key, str(value))
    
    def _process_port(self, session, service_name: str, port_mapping: str):
        """Create Port node and link to Service."""
        
        def create_port_relationship(tx, service, port_str):
            # Parse port mapping (e.g., "8080:80" or "8080")
            parts = str(port_str).split(':')
            host_port = parts[0]
            container_port = parts[1] if len(parts) > 1 else parts[0]
            
            tx.run("""
                MATCH (s:Service {name: $service})
                MERGE (p:Port {number: $port})
                SET p.container_port = $container_port,
                    p.protocol = 'tcp'
                MERGE (s)-[:EXPOSES]->(p)
            """, service=service, port=host_port, container_port=container_port)
        
        session.execute_write(create_port_relationship, service_name, port_mapping)
    
    def _process_volume(self, session, service_name: str, volume_mapping: str):
        """Create Volume node and link to Service."""
        
        def create_volume_relationship(tx, service, vol_str):
            # Parse volume mapping (e.g., "./data:/app/data:ro")
            parts = str(vol_str).split(':')
            if len(parts) >= 2:
                host_path = parts[0]
                container_path = parts[1]
                mode = parts[2] if len(parts) > 2 else "rw"
                
                tx.run("""
                    MATCH (s:Service {name: $service})
                    MERGE (v:Volume {host_path: $host_path, container_path: $container_path})
                    SET v.mode = $mode
                    MERGE (s)-[:MOUNTS]->(v)
                """, service=service, host_path=host_path, container_path=container_path, mode=mode)
        
        session.execute_write(create_volume_relationship, service_name, volume_mapping)
    
    def _process_env_var(self, session, service_name: str, key: str, value: str):
        """Create EnvVar node and link to Service."""
        
        def create_env_relationship(tx, service, k, v):
            tx.run("""
                MATCH (s:Service {name: $service})
                MERGE (e:EnvVar {key: $key, service: $service})
                SET e.value = $value
                MERGE (s)-[:CONFIGURED_BY]->(e)
            """, service=service, key=k, value=str(v))
        
        session.execute_write(create_env_relationship, service_name, key, value)
    
    def query_infrastructure(self, query: str) -> List[Dict]:
        """Run a Cypher query against the Infrastructure graph."""
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(query)
            return [dict(record) for record in result]


# Singleton
infra_discovery = InfrastructureDiscovery()

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("infra-discovery")

@mcp.tool()
def discover_infrastructure(compose_path: str = "/app/docker-compose.yml", env_path: str = "/app/.env") -> str:
    """Discover infrastructure from docker-compose."""
    try:
        if not os.path.exists(compose_path):
            return f"Error: {compose_path} not found"
        summary = infra_discovery.discover_from_compose(compose_path, env_path)
        return f"Infrastructure Discovered: {summary}"
    except Exception as e:
        return f"Discovery failed: {e}"
