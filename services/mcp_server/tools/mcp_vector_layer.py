import os
import logging
import json
import requests
from typing import Dict, List, Any, Optional
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

class VectorLayer:
    """
    Phase 4: Add vector embeddings to all Neo4j nodes.
    Supports BOTH standard vectors (Qwen) and HSE (Hyperspherical Embeddings).
    """
    
    def __init__(self):
        self.neo4j_uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
        self.neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        self.neo4j_password = os.environ.get("NEO4J_PASSWORD", "arca_password")
        
        # Embedding services
        self.embedding_url = os.environ.get("EMBEDDING_SERVICE_URL", "http://embedding_service:8005")
        if not self.embedding_url.endswith('/v1/embeddings'):
            self.embedding_url = f"{self.embedding_url}/v1/embeddings"
        
        self.hse_url = os.environ.get("HSE_ENCODER_URL", "http://hse_encoder:8095/encode")
        
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
    
    def _generate_standard_embedding(self, text: str) -> Optional[List[float]]:
        """Generate standard Qwen embedding (1024-dim)."""
        try:
            payload = {"input": text, "model": "qwen3-embedding"}
            resp = requests.post(self.embedding_url, json=payload, timeout=10)
            
            if resp.status_code != 200:
                logger.warning(f"Embedding service error: {resp.text}")
                return None
            
            data = resp.json()
            if "data" in data and data["data"]:
                return data["data"][0]["embedding"]
            else:
                logger.warning("Empty embedding response, using fallback")
                # Fallback random vector
                import random
                return [random.uniform(-1, 1) for _ in range(1024)]
                
        except Exception as e:
            logger.error(f"Standard embedding failed: {e}")
            return None
    
    def _generate_hse_embedding(self, text: str) -> Optional[List[float]]:
        """Generate HSE hyperspherical embedding."""
        try:
            payload = {"text": text}
            resp = requests.post(self.hse_url, json=payload, timeout=10)
            
            if resp.status_code != 200:
                logger.warning(f"HSE service error: {resp.text}")
                return None
            
            data = resp.json()
            return data.get("embedding") or data.get("hse_vector")
                
        except Exception as e:
            logger.warning(f"HSE embedding failed: {e}")
            return None
    
    def embed_graph_nodes(self, node_types: List[str] = None) -> Dict[str, Any]:
        """
        Add vector and hse_vector properties to all graph nodes.
        
        Args:
            node_types: List of node types to embed (default: all)
            
        Returns:
            Summary of embedded nodes
        """
        if node_types is None:
            node_types = ["Service", "Tool", "Function", "Module", "Agent", "WorkflowNode"]
        
        try:
            driver = self._get_driver()
            summary = {"nodes_embedded": 0, "types": {}}
            
            for node_type in node_types:
                count = self._embed_node_type(driver, node_type)
                summary["types"][node_type] = count
                summary["nodes_embedded"] += count
            
            logger.info(f"Vector embedding complete: {summary}")
            return summary
            
        except Exception as e:
            logger.error(f"Node embedding failed: {e}")
            raise
    
    def _embed_node_type(self, driver, node_type: str) -> int:
        """Embed all nodes of a specific type."""
        with driver.session() as session:
            # Get nodes without embeddings
            result = session.run(f"""
                MATCH (n:{node_type})
                WHERE n.vector IS NULL OR n.hse_vector IS NULL
                RETURN n
                LIMIT 100
            """)
            
            nodes = [record["n"] for record in result]
            
            for node in nodes:
                text = self._node_to_text(node, node_type)
                if text:
                    # Generate both embedding types
                    vector = self._generate_standard_embedding(text)
                    hse_vector = self._generate_hse_embedding(text)
                    
                    # Update node
                    self._update_node_vectors(session, node, vector, hse_vector)
            
            return len(nodes)
    
    def _node_to_text(self, node, node_type: str) -> str:
        """Convert node properties to text for embedding."""
        if node_type == "Service":
            return f"Service: {node.get('name')} Image: {node.get('image', 'unknown')}"
        
        elif node_type == "Tool":
            desc = node.get('description', '')
            return f"Tool: {node.get('name')} - {desc}"
        
        elif node_type == "Function":
            sig = node.get('signature', '')
            doc = node.get('docstring', '')[:200]
            return f"Function {sig}. {doc}"
        
        elif node_type == "Module":
            return f"Python module: {node.get('name')}"
        
        elif node_type == "Agent":
            return f"Agent: {node.get('name')} - Cognitive workflow handler"
        
        elif node_type == "WorkflowNode":
            return f"Workflow node: {node.get('name')} in {node.get('agent', 'unknown')} agent"
        
        return node.get('name', 'Unknown')
    
    def _update_node_vectors(self, session, node, vector: Optional[List[float]], hse_vector: Optional[List[float]]):
        """Update node with vector embeddings."""
        node_id = node.element_id
        
        def update_vectors(tx, nid, vec, hse_vec):
            query_parts = ["MATCH (n) WHERE elementId(n) = $nid SET "]
            params = {"nid": nid}
            
            updates = []
            if vec:
                updates.append("n.vector = $vec")
                params["vec"] = vec
            if hse_vec:
                updates.append("n.hse_vector = $hse_vec")
                params["hse_vec"] = hse_vec
            
            if updates:
                query = query_parts[0] + ", ".join(updates)
                tx.run(query, **params)
        
        session.execute_write(update_vectors, node_id, vector, hse_vector)
    
    def semantic_search(self, query: str, node_types: List[str] = None, limit: int = 5, use_hse: bool = False) -> List[Dict]:
        """
        Semantic search across graph nodes.
        
        Args:
            query: Natural language query
            node_types: Types to search (default: all)
            limit: Max results
            use_hse: Use HSE vectors instead of standard
            
        Returns:
            Ranked list of nodes with similarity scores
        """
        # Generate query embedding
        if use_hse:
            query_vec = self._generate_hse_embedding(query)
            vec_field = "hse_vector"
        else:
            query_vec = self._generate_standard_embedding(query)
            vec_field = "vector"
        
        if not query_vec:
            return []
        
        # Search
        driver = self._get_driver()
        with driver.session() as session:
            # Build label filter
            if node_types:
                labels = ":".join(node_types)
                match = f"MATCH (n:{labels})"
            else:
                match = "MATCH (n)"
            
            # Cosine similarity search
            cypher = f"""
                {match}
                WHERE n.{vec_field} IS NOT NULL
                RETURN n, 
                       gds.similarity.cosine(n.{vec_field}, $query_vec) as score
                ORDER BY score DESC
                LIMIT $limit
            """
            
            result = session.run(cypher, query_vec=query_vec, limit=limit)
            return [{"node": dict(record["n"]), "score": record["score"]} for record in result]


# Singleton
vector_layer = VectorLayer()
