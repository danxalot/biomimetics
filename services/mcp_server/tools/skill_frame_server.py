#!/usr/bin/env python3
"""
ARCA Skill Frame Server

Provides contextual skill frames to agents based on:
1. Primary skill title from task instructions
2. Task content for geometric marker matching
3. Live service state from Redis/Docker
4. Neo4j skill graph relationships

The system is SELF-DESCRIBING: terrain markers auto-update from codebase.
"""

import os
import re
import json
import logging
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import yaml
import redis
import httpx
from neo4j import GraphDatabase

# Initialize logging
logger = logging.getLogger(__name__)

# Configuration
SKILLS_PATH = Path(os.getenv("MCP_SKILLS_DIR", os.getenv("SKILLS_PATH", "/app/skills")))
if not SKILLS_PATH.exists() and Path("/app/mcp_skills").exists():
    SKILLS_PATH = Path("/app/mcp_skills")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_password")
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://embedding_service:8005/v1/embeddings")
HSE_ENCODER_URL = os.getenv("HSE_ENCODER_URL", "http://hse_encoder:8095/encode")
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8080")

# Geometric similarity thresholds
THRESHOLDS = {
    "immediate": 0.85,   # Same orbital zone
    "related": 0.70,     # Adjacent orbit
    "distant": 0.55      # Visible but separate
}

# =============================================================================
# STANDARDIZED 1024-DIM EMBEDDING ARCHITECTURE (JEPA Compatible)
# =============================================================================
# All modalities project to 1024-dim for unified latent space:
# - HSE: 10,000 → 1024 (sparse projection)
# - Text (Qwen3): 1024 (native)
# - Vision (SigLIP): 1152 → 1024 (linear projection)
# - VAE/Transformer: 1024
# - JEPA: 1024 (incoming integration)
#
# This enables:
# - Direct modality comparison via cosine similarity
# - Unified skill frame embeddings
# - JEPA predictor/target compatibility

EMBEDDING_DIM = 1024  # Universal embedding dimension

EMBEDDING_SCHEMA = {
    "universal_dim": 1024,        # All modalities project to this
    "raw_dims": {
        "text_qwen3": 1024,       # Native 1024
        "vision_siglip": 1152,    # Needs 1152 → 1024 projection
        "hse_binary": 10000,      # Needs 10000 → 1024 projection
        "vae_latent": 1024        # Native 1024
    },
    "projections": {
        "vision": {"from": 1152, "to": 1024},
        "hse": {"from": 10000, "to": 1024}
    },
    # For skill frames, we use semantic (text) embeddings primarily
    # HSE can be fused via addition for solution-aware embeddings
    "fusion_mode": "additive"  # semantic + hse_projected for composite
}

# Solution trajectory templates - encoded via HSE for task-aware embeddings
SOLUTION_VECTORS = {
    "container_restart": "restart container health check logs docker ps",
    "model_routing": "llm gateway model alias route port 8080 11435",
    "git_recovery": "git reset checkout stash clean branch conflict",
    "config_fix": "environment variable config yaml json env",
    "permission_fix": "firewall auth header genesis chain 403 forbidden",
    "memory_issue": "redis neo4j cache flush reconnect ping timeout",
    "embedding_issue": "vector dimension mismatch similarity cosine normalize"
}


@dataclass
class TouchPoint:
    """A connection point to a service, workflow, or skill"""
    type: str  # "service", "workflow", "skill", "pattern"
    name: str
    port: Optional[int] = None
    status: Optional[str] = None  # Live status from Redis/Docker
    path: Optional[str] = None


@dataclass
class SkillFrame:
    """Assembled contextual frame for agent consumption"""
    skill_id: str
    layer: str
    domain: str
    primary_content: str
    
    # Layer 2: Service context
    service_context: List[TouchPoint] = field(default_factory=list)
    
    # Layer 3: Workflow integration
    workflow_context: List[TouchPoint] = field(default_factory=list)
    
    # Layer 4: Geometrically related skills
    related_skills: List[Tuple[str, float]] = field(default_factory=list)
    
    # Quick reference
    touchpoint_summary: str = ""
    
    # Metadata
    assembled_at: str = field(default_factory=lambda: datetime.now().isoformat())
    cache_key: str = ""


class SkillFrameServer:
    """
    Assembles contextual skill frames from:
    - Skill documents (mcp_skills/*.md)
    - Neo4j skill graph
    - Redis live state
    - Embedding similarity
    """
    
    def __init__(self):
        self.redis_client = None
        self.neo4j_driver = None
        self.skill_cache: Dict[str, Dict] = {}
        self._init_connections()
        self._load_skill_index()
    
    def _init_connections(self):
        """Initialize Redis and Neo4j connections"""
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST, 
                port=REDIS_PORT, 
                decode_responses=True
            )
            self.redis_client.ping()
            logger.info("SkillFrameServer: Redis connected")
        except Exception as e:
            logger.warning(f"SkillFrameServer: Redis unavailable: {e}")
        
        try:
            self.neo4j_driver = GraphDatabase.driver(
                NEO4J_URI, 
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            logger.info("SkillFrameServer: Neo4j connected")
        except Exception as e:
            logger.warning(f"SkillFrameServer: Neo4j unavailable: {e}")
    
    def _load_skill_index(self):
        """Load and parse all skill documents into index"""
        if not SKILLS_PATH.exists():
            logger.warning(f"Skills path not found: {SKILLS_PATH}")
            return
        
        for skill_file in SKILLS_PATH.glob("*.md"):
            try:
                content = skill_file.read_text()
                metadata = self._extract_frontmatter(content)
                
                # Auto-generate skill_id from filename if not in frontmatter
                skill_id = metadata.get("skill_id", skill_file.stem)
                
                # Auto-discover markers from content
                markers = self._auto_discover_markers(content, skill_file.stem)
                
                self.skill_cache[skill_id] = {
                    "file_path": str(skill_file),
                    "content": content,
                    "metadata": metadata,
                    "markers": markers,
                    "layer": metadata.get("layer", self._infer_layer(skill_file.stem)),
                    "domain": metadata.get("domain", self._infer_domain(content))
                }
                
            except Exception as e:
                logger.error(f"Failed to load skill {skill_file}: {e}")
        
        logger.info(f"SkillFrameServer: Loaded {len(self.skill_cache)} skills")
    
    def _extract_frontmatter(self, content: str) -> Dict:
        """Extract YAML frontmatter from markdown"""
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                return {}
        return {}
    
    def _auto_discover_markers(self, content: str, filename: str) -> Dict:
        """
        AUTO-DISCOVERY: Extract markers from document content.
        This is what makes the system self-describing.
        """
        markers = {
            "services": [],
            "ports": [],
            "files": [],
            "patterns": [],
            "embedding_anchors": []
        }
        
        # Extract service names (common patterns)
        service_pattern = r'\b(llm_gateway|mcp_server|maintainer_agents|agent_service|redis|neo4j|user_interaction_agent|embedding_service|memory_system)\b'
        markers["services"] = list(set(re.findall(service_pattern, content, re.IGNORECASE)))
        
        # Extract port numbers
        port_pattern = r'\b(80[0-9]{2}|11435|7687|6379|5432)\b'
        markers["ports"] = list(set(re.findall(port_pattern, content)))
        
        # Extract file paths
        file_pattern = r'`([^`]+\.(?:py|md|yaml|json|sh))`'
        markers["files"] = list(set(re.findall(file_pattern, content)))[:10]  # Limit
        
        # Extract reasoning patterns
        pattern_pattern = r'(error[_\s]recovery|health[_\s]check|restart|troubleshoot|audit|validate)'
        markers["patterns"] = list(set(re.findall(pattern_pattern, content, re.IGNORECASE)))
        
        # Generate embedding anchors from headers and key phrases
        headers = re.findall(r'^#{1,3}\s+(.+)$', content, re.MULTILINE)
        key_phrases = [filename.replace("_", " ")]
        key_phrases.extend([h.lower() for h in headers[:5]])
        markers["embedding_anchors"] = key_phrases
        
        return markers
    
    def _infer_layer(self, filename: str) -> str:
        """Infer layer from filename patterns"""
        filename_lower = filename.lower()
        if any(x in filename_lower for x in ["docker", "git", "file", "security", "ops"]):
            return "execution"
        if any(x in filename_lower for x in ["gateway", "port", "routing", "server"]):
            return "routing"
        if any(x in filename_lower for x in ["genesis", "reasoning", "agent"]):
            return "reasoning"
        if any(x in filename_lower for x in ["geometry", "kernel", "embedding"]):
            return "geometry"
        return "core"
    
    def _infer_domain(self, content: str) -> str:
        """Infer domain from content patterns"""
        content_lower = content.lower()
        if "docker" in content_lower or "container" in content_lower:
            return "container_management"
        if "git" in content_lower or "version control" in content_lower:
            return "version_control"
        if "llm" in content_lower or "model" in content_lower:
            return "model_routing"
        if "agent" in content_lower or "workflow" in content_lower:
            return "agent_orchestration"
        return "general"
    
    async def get_service_status(self, service_name: str) -> Optional[str]:
        """Get live service status from Redis blackboard"""
        if not self.redis_client:
            return None
        try:
            status = self.redis_client.get(f"arca:health:{service_name}")
            return status or "unknown"
        except Exception:
            return None
    
    async def get_embedding(self, text: str, headers: Optional[Dict[str, str]] = None) -> Optional[List[float]]:
        """Get embedding vector for text"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                final_headers = {"X-Genesis-Chain": "true", "X-Genesis-Agent": "skill_frame_server"}
                if headers:
                    genesis_headers = {k: v for k, v in headers.items() if k.lower().startswith("x-genesis-")}
                    final_headers.update(genesis_headers)

                response = await client.post(
                    EMBEDDING_URL,
                    json={"input": [text]},
                    headers=final_headers
                )
                if response.status_code == 200:
                    data = response.json()
                    # OpenAI format
                    if "data" in data and len(data["data"]) > 0:
                        return data["data"][0].get("embedding")
                    return data.get("embedding")
        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
        return None
    
    def query_neo4j_skill_graph(self, skill_id: str) -> Dict:
        """Query Neo4j for skill relationships"""
        if not self.neo4j_driver:
            return {"touchpoints": [], "prerequisites": [], "related": []}
        
        try:
            with self.neo4j_driver.session() as session:
                result = session.run("""
                    MATCH (s:Skill {id: $skill_id})
                    OPTIONAL MATCH (s)-[:TOUCHES]->(svc:Service)
                    OPTIONAL MATCH (s)-[:REQUIRES]->(prereq:Skill)
                    OPTIONAL MATCH (s)-[:SIMILAR_TO]->(related:Skill)
                    RETURN s, 
                           collect(DISTINCT svc) as services,
                           collect(DISTINCT prereq) as prerequisites,
                           collect(DISTINCT related) as related
                """, skill_id=skill_id)
                
                record = result.single()
                if record:
                    return {
                        "touchpoints": [dict(s) for s in record["services"] if s],
                        "prerequisites": [dict(p)["id"] for p in record["prerequisites"] if p],
                        "related": [dict(r)["id"] for r in record["related"] if r]
                    }
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")
        
        return {"touchpoints": [], "prerequisites": [], "related": []}
    
    def query_universal_frame(self, anchor_id: str, depth: int = 5) -> Dict:
        """
        Universal 5-Hop Crawler: Expands from anchor node to build a comprehensive frame.
        Layers are mapped by hop distance and relationship type.
        """
        if not self.neo4j_driver:
            return {"error": "Neo4j unavailable"}

        frame = {
            "query": anchor_id,
            "anchor": anchor_id,
            "layers": {
                "0_center": [], 
                "1_config": [], 
                "2_code": [], 
                "3_tools": [], 
                "4_sops": [], 
                "5_memory": []
            }
        }

        query = """
            MATCH (start {id: $anchor_id})
            CALL apoc.path.spanningTree(start, {
                minLevel: 1,
                maxLevel: $depth,
                labelFilter: '+Service|File|Tool|Workflow|Skill|Vector',
                limit: 100
            })
            YIELD path
            RETURN path
        """
        # Fallback if APOC is not available: Standard variable expansion
        basic_query = """
            MATCH p=(start {id: $anchor_id})-[*1..5]-(m)
            RETURN p as path
            LIMIT 100
        """

        try:
            with self.neo4j_driver.session() as session:
                # Attempt basic query first (safer than APOC dependency)
                result = session.run(basic_query, anchor_id=anchor_id)
                
                visited = set()
                
                for record in result:
                    path = record["path"]
                    for node in path.nodes:
                        if node.id in visited:
                            continue
                        visited.add(node.id)
                        
                        # Map node to frame layer based on labels/properties
                        props = dict(node)
                        labels = list(node.labels)
                        item = {"id": props.get("id", str(node.id)), "labels": labels, "props": props}
                        
                        # Layer Logic
                        if "File" in labels:
                             if props.get("type") in ["yaml", "json", "env"]:
                                 frame["layers"]["1_config"].append(item)
                             else:
                                 frame["layers"]["2_code"].append(item)
                        elif "Tool" in labels:
                             frame["layers"]["3_tools"].append(item)
                        elif "Workflow" in labels or "SOP" in labels:
                             frame["layers"]["4_sops"].append(item)
                        elif "Vector" in labels or "Event" in labels:
                             frame["layers"]["5_memory"].append(item)
                        elif "Service" in labels and item["id"] == anchor_id:
                             frame["layers"]["0_center"].append(item)
                        
                return frame
                
        except Exception as e:
            logger.error(f"Universal Frame Query failed: {e}")
            return {"error": str(e), "layers": {}}
    
    async def find_geometric_neighbors(
        self, 
        task_content: str, 
        current_skill_id: str,
        top_k: int = 5,
        headers: Optional[Dict[str, str]] = None
    ) -> List[Tuple[str, float]]:
        """
        Find geometrically similar skills based on embedding similarity.
        This is the "solar system" discovery mechanism.
        """
        neighbors = []
        
        # Get embedding for task content
        task_embedding = await self.get_embedding(task_content, headers=headers)
        if not task_embedding:
            return neighbors
        
        # Compare with cached skill embeddings
        for skill_id, skill_data in self.skill_cache.items():
            if skill_id == current_skill_id:
                continue
            
            # Use embedding anchors if available
            anchors = skill_data.get("markers", {}).get("embedding_anchors", [])
            anchor_text = " ".join(anchors)
            
            if anchor_text:
                skill_embedding = await self.get_embedding(anchor_text, headers=headers)
                if skill_embedding:
                    similarity = self._cosine_similarity(task_embedding, skill_embedding)
                    if similarity >= THRESHOLDS["distant"]:
                        neighbors.append((skill_id, similarity))
        
        # Sort by similarity and return top_k
        neighbors.sort(key=lambda x: x[1], reverse=True)
        return neighbors[:top_k]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors"""
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    async def assemble_frame(
        self,
        primary_skill: str,
        task_content: str = "",
        include_layers: List[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> SkillFrame:
        """
        Assemble complete skill frame for agent consumption.
        This is the main entry point.
        """
        include_layers = include_layers or ["service", "workflow", "related"]
        
        # Get skill from cache
        skill_data = self.skill_cache.get(primary_skill)
        if not skill_data:
            # Try fuzzy match
            for skill_id in self.skill_cache:
                if primary_skill.lower() in skill_id.lower():
                    skill_data = self.skill_cache[skill_id]
                    primary_skill = skill_id
                    break
        
        if not skill_data:
            return SkillFrame(
                skill_id=primary_skill,
                layer="unknown",
                domain="unknown",
                primary_content=f"Skill '{primary_skill}' not found.",
                touchpoint_summary="No touchpoints available."
            )
        
        # Initialize frame
        frame = SkillFrame(
            skill_id=primary_skill,
            layer=skill_data.get("layer", "core"),
            domain=skill_data.get("domain", "general"),
            primary_content=skill_data.get("content", "")
        )
        
        # Layer 2: Service context with LIVE status
        if "service" in include_layers:
            markers = skill_data.get("markers", {})
            for service in markers.get("services", []):
                status = await self.get_service_status(service)
                port = self._get_service_port(service)
                frame.service_context.append(TouchPoint(
                    type="service",
                    name=service,
                    port=port,
                    status=status
                ))
        
        # Layer 3: Workflow context from Neo4j
        if "workflow" in include_layers:
            neo4j_data = self.query_neo4j_skill_graph(primary_skill)
            for svc in neo4j_data.get("touchpoints", []):
                frame.workflow_context.append(TouchPoint(
                    type="workflow",
                    name=svc.get("name", "unknown"),
                    port=svc.get("port")
                ))
        
        # Layer 4: Geometric similarity (solar system neighbors)
        if "related" in include_layers and task_content:
            neighbors = await self.find_geometric_neighbors(
                task_content, 
                primary_skill,
                top_k=5,
                headers=headers
            )
            frame.related_skills = neighbors
        
        # Generate touchpoint summary
        frame.touchpoint_summary = self._generate_summary(frame)
        
        # Cache key for future reference
        cache_input = f"{primary_skill}:{task_content[:100]}"
        frame.cache_key = hashlib.md5(cache_input.encode()).hexdigest()[:8]
        
        return frame
    
    def _get_service_port(self, service: str) -> Optional[int]:
        """Get known port for service"""
        port_map = {
            "llm_gateway": 8080,
            "mcp_server": 8086,
            "maintainer_agents": 8090,
            "agent_service": 8088,
            "user_interaction_agent": 8084,
            "embedding_service": 8089,
            "memory_system": 8091,
            "redis": 6379,
            "neo4j": 7687,
            "postgres": 5432
        }
        return port_map.get(service)
    
    def _generate_summary(self, frame: SkillFrame) -> str:
        """Generate quick reference summary"""
        lines = [f"**{frame.skill_id}** [{frame.layer}/{frame.domain}]"]
        
        if frame.service_context:
            services = ", ".join([
                f"{tp.name}:{tp.port}({tp.status or '?'})" 
                for tp in frame.service_context
            ])
            lines.append(f"Services: {services}")
        
        if frame.related_skills:
            related = ", ".join([
                f"{skill}({score:.2f})" 
                for skill, score in frame.related_skills[:3]
            ])
            lines.append(f"Related: {related}")
        
        return "\n".join(lines)


# Singleton instance
_server: Optional[SkillFrameServer] = None

def get_server() -> SkillFrameServer:
    global _server
    if _server is None:
        _server = SkillFrameServer()
    return _server


# MCP Tool Interface
async def get_skill_frame(
    primary_skill: str,
    task_content: str = "",
    include_layers: List[str] = None,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    MCP Tool: Assemble contextual skill frame for agent consumption.
    
    Args:
        primary_skill: First-layer skill title (e.g., "DOCKER_OPS_SOP")
        task_content: Optional task description for geometric matching
        include_layers: Layers to include ["service", "workflow", "related"]
    
    Returns:
        SkillFrame as dict with primary_content, service_context, related_skills, etc.
    """
    server = get_server()
    frame = await server.assemble_frame(
        primary_skill=primary_skill,
        task_content=task_content,
        include_layers=include_layers or ["service", "workflow", "related"],
        headers=headers
    )
    return asdict(frame)


async def get_universal_frame(anchor_id: str, depth: int = 5, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    MCP Tool: Get Universal 5-Hop Skill Frame.
    """
    server = get_server()
    return server.query_universal_frame(anchor_id, depth) # Logic updated in core server if needed, but here we just pass headers if we add it to query


async def refresh_skill_index(headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    MCP Tool: Refresh the skill index from disk.
    Call after modifying mcp_skills/*.md files.
    """
    server = get_server()
    server._load_skill_index()
    return {
        "status": "refreshed",
        "skill_count": len(server.skill_cache),
        "skills": list(server.skill_cache.keys())
    }


async def get_skill_graph(headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    MCP Tool: Get overview of skill graph relationships.
    """
    server = get_server()
    
    graph = {
        "nodes": [],
        "layers": {}
    }
    
    for skill_id, data in server.skill_cache.items():
        layer = data.get("layer", "core")
        domain = data.get("domain", "general")
        markers = data.get("markers", {})
        
        graph["nodes"].append({
            "id": skill_id,
            "layer": layer,
            "domain": domain,
            "services": markers.get("services", []),
            "patterns": markers.get("patterns", [])
        })
        
        if layer not in graph["layers"]:
            graph["layers"][layer] = []
        graph["layers"][layer].append(skill_id)
    
    return graph
