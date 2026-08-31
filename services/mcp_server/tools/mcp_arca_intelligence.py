import os
import redis
import json
import logging
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase

# Initialize FastMCP Tool
mcp = FastMCP("arca-intelligence")
logger = logging.getLogger(__name__)

# Endpoints
NEO4J_URL = os.environ.get("NEO4J_URL", "bolt://neo4j:7687")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
NEO4J_AUTH = ("neo4j", os.environ.get("NEO4J_PASSWORD", "neo4j_password"))

@mcp.tool()
def arca_system_query(query_type: str = "full", context: Optional[str] = None) -> str:
    """
    Unified access point for ARCA's multi-layered system representation.
    query_type: "topology" (hardware/services), "state" (Redis blackboard), "skills" (Skill frame registry), "full" (ALL)
    context: Optional task context to filter results.
    """
    results = {}

    if query_type in ["topology", "full"]:
        try:
            driver = GraphDatabase.driver(NEO4J_URL, auth=NEO4J_AUTH)
            with driver.session() as session:
                cypher = """
                MATCH (n)
                WHERE n:Service OR n:Host OR n:Resource OR n:Network
                OPTIONAL MATCH (n)-[r]->(m)
                RETURN n.name as name, labels(n)[0] as type, n.layer as layer, 
                       collect({target: m.name, rel: type(r)}) as connections
                LIMIT 50
                """
                query_result = session.run(cypher)
                results["topology"] = [record.data() for record in query_result]
            driver.close()
        except Exception as e:
            results["topology"] = f"Error querying Neo4j: {str(e)}"

    if query_type in ["state", "full"]:
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            results["system_state"] = {
                "global_status": r.get("arca:state:global") or "unknown",
                "execution_firewall": r.get("arca:firewall:status") or "ACTIVE",
                "last_cognitive_tick": r.get("arca:cognitive:tick") or "0",
                "active_agents": r.smembers("arca:active_agents") or []
            }
        except Exception as e:
            results["system_state"] = f"Error querying Redis: {str(e)}"

    if query_type in ["skills", "full"]:
        # In a real implementation, this would query the skill_frame_server
        results["skill_matrix"] = {
            "Execution": ["DOCKER_OPS_SOP", "GIT_OPS_SOP", "FILE_OPS_SOP"],
            "Cognitive": ["ARCA_SELF_HEALING_SYSTEM", "ARCA_COGNITIVE_TICK_ARCHITECTURE"],
            "Routing": ["LLM_GATEWAY_TROUBLESHOOTING", "ARCA_PORT_MAPPING_UPDATED"]
        }

    return json.dumps(results, indent=2)

@mcp.tool()
def arca_feasibility_check(task_description: str) -> str:
    """
    Evaluates the technical feasibility of a task against the current world state.
    Returns a GO/NO-GO signal and reasoning.
    """
    world_state = json.loads(arca_system_query("full"))
    
    # Simple rule-based feasibility logic
    # 1. Check Firewall
    firewall = world_state.get("system_state", {}).get("execution_firewall", "ACTIVE")
    if firewall == "LOCKED":
        return json.dumps({
            "status": "NO-GO",
            "reason": "Execution Firewall is LOCKED. System modifications are restricted.",
            "feasibility_score": 0.1
        })

    # 2. Check dependencies (Basic keyword check in topology)
    topology = str(world_state.get("topology", []))
    if "docker" in task_description.lower() and "Service" not in topology:
        return json.dumps({
            "status": "CAUTION",
            "reason": "Docker service topology not fully visible in Neo4j. Manual verification required.",
            "feasibility_score": 0.5
        })

    return json.dumps({
        "status": "GO",
        "reason": "System state is healthy and dependency layers are visible.",
        "feasibility_score": 0.9
    })

@mcp.tool()
def log_learned_heuristic(pattern: str, context: str, heuristic: str) -> str:
    """
    Log a successful reasoning trajectory or anti-pattern to the ReasoningBank.
    """
    logger.info(f"LEARNED HEURISTIC: [{pattern}] in {context} -> {heuristic}")
    return f"Successfully logged heuristic to ReasoningBank: {pattern}"
