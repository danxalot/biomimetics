"""
Neo4j Graph Schema and Bootstrap

Defines the ARCA system graph structure for episodic/structural memory.

This is the "what exists and how it relates" layer.
Redis is "what is currently being thought."
Agents provide "what should be proposed next."
Geometry Kernel enforces "how beliefs can move."
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime


# ============================================================================
# Node Labels (Types)
# ============================================================================

class NodeLabel:
    """Node types in the ARCA graph."""
    SYSTEM = "System"
    AGENT = "Agent"
    METAPHYSICAL_ANCHOR = "MetaphysicalAnchor"
    MENTAL_STATE_SCHEMA = "MentalStateSchema"
    BLACKBOARD = "Blackboard"
    CONCEPT = "Concept"
    REASONING_TRACE = "ReasoningTrace"
    EXECUTION_RECORD = "ExecutionRecord"


# ============================================================================
# Relationship Types
# ============================================================================

class RelationshipType:
    """Relationships in the ARCA graph."""
    REGISTERED_IN = "REGISTERED_IN"
    CONNECTS_TO = "CONNECTS_TO"
    OPERATES_ON = "OPERATES_ON"
    MATERIALISED_IN = "MATERIALISED_IN"
    IMPLEMENTS = "IMPLEMENTS"
    ALIGNED_WITH = "ALIGNED_WITH"
    PRODUCED = "PRODUCED"
    DEPENDS_ON = "DEPENDS_ON"
    REFINES = "REFINES"


# ============================================================================
# Node Definitions
# ============================================================================

@dataclass
class SystemNode:
    """Represents infrastructure components."""
    id: str
    name: str
    type: str  # redis, service, database, llm, etc.
    role: str
    endpoint: Optional[str] = None
    version: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_cypher_create(self) -> str:
        """Generate Cypher MERGE statement."""
        return f"""
MERGE (s:{NodeLabel.SYSTEM} {{
    id: "{self.id}",
    name: "{self.name}",
    type: "{self.type}",
    role: "{self.role}"
    {"," if self.endpoint else ""}
    {f'endpoint: "{self.endpoint}"' if self.endpoint else ""}
}})
"""


@dataclass
class AgentNode:
    """Represents cognitive actors (LLM-based agents)."""
    id: str
    name: str
    function: str  # planning, engineering, reviewing, architecture, ops
    authority_level: int
    model: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_cypher_create(self) -> str:
        """Generate Cypher MERGE statement."""
        return f"""
MERGE (a:{NodeLabel.AGENT} {{
    id: "{self.id}",
    name: "{self.name}",
    function: "{self.function}",
    authority_level: {self.authority_level}
    {"," if self.model else ""}
    {f'model: "{self.model}"' if self.model else ""}
}})
"""


@dataclass
class MetaphysicalAnchorNode:
    """Represents invariant conceptual poles."""
    id: str
    name: str
    description: str
    polarity: str  # constructive, destructive, neutral
    created_at: Optional[datetime] = None

    def to_cypher_create(self) -> str:
        """Generate Cypher MERGE statement."""
        return f"""
MERGE (m:{NodeLabel.METAPHYSICAL_ANCHOR} {{
    id: "{self.id}",
    name: "{self.name}",
    description: "{self.description}",
    polarity: "{self.polarity}"
}})
"""


@dataclass
class MentalStateSchemaNode:
    """Defines working memory structure."""
    id: str
    name: str
    scope: str  # transient, episodic, persistent
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_cypher_create(self) -> str:
        """Generate Cypher MERGE statement."""
        return f"""
MERGE (s:{NodeLabel.MENTAL_STATE_SCHEMA} {{
    id: "{self.id}",
    name: "{self.name}",
    scope: "{self.scope}"
    {"," if self.description else ""}
    {f'description: "{self.description}"' if self.description else ""}
}})
"""


@dataclass
class BlackboardNode:
    """Represents shared cognitive surface (Redis-backed)."""
    id: str
    name: str
    backend: str  # redis
    consistency_model: str  # eventual, strict
    created_at: Optional[datetime] = None

    def to_cypher_create(self) -> str:
        """Generate Cypher MERGE statement."""
        return f"""
MERGE (b:{NodeLabel.BLACKBOARD} {{
    id: "{self.id}",
    name: "{self.name}",
    backend: "{self.backend}",
    consistency_model: "{self.consistency_model}"
}})
"""


# ============================================================================
# Bootstrap Cypher Script
# ============================================================================

class BootstrapCypher:
    """
    Generates the complete Neo4j initialization script.

    This is a single transaction that establishes ARCA's structural memory.
    """

    @staticmethod
    def generate_full_script() -> str:
        """Generate complete bootstrap Cypher script."""
        script = """
// ============================================================================
// ARCA Neo4j Bootstrap Script
// ============================================================================
// This script initializes ARCA's structural and episodic memory graph.
// It establishes:
// 1. System topology (Redis, Agent Service, Neo4j)
// 2. Agent registry (Architect, Planner, Engineer, Reviewer)
// 3. Metaphysical anchors (Aether, Syntropy, Entropy)
// 4. Mental state schemas (messages, current_plan)
// 5. Blackboard (shared cognitive surface)
// 6. All relationships binding the system together
//
// IMPORTANT: Run this as a single transaction.
// ============================================================================


// --- PHASE 1: SYSTEM TOPOLOGY ---
// Infrastructure nodes that ARCA operates within.

MERGE (redis:System { 
    id: "arca_redis", 
    name: "ARCA Redis Blackboard", 
    type: "redis", 
    role: "shared_cognitive_blackboard",
    endpoint: "redis:6379"
})

MERGE (agentService:System { 
    id: "arca_agent_service", 
    name: "ARCA Agent Service", 
    type: "service", 
    role: "agent_orchestration",
    endpoint: "agent_service:8088"
})

MERGE (neo4j:System { 
    id: "arca_neo4j", 
    name: "ARCA Neo4j", 
    type: "database", 
    role: "episodic_and_structural_memory",
    endpoint: "neo4j:7687"
})

MERGE (ollama:System {
    id: "arca_ollama",
    name: "ARCA Ollama Local Inference",
    type: "llm",
    role: "local_embedding_and_small_model_inference",
    endpoint: "ollama:11434"
})

// System connectivity
MERGE (agentService)-[:CONNECTS_TO]->(redis)
MERGE (agentService)-[:CONNECTS_TO]->(neo4j)
MERGE (neo4j)-[:CONNECTS_TO]->(redis)
MERGE (agentService)-[:CONNECTS_TO]->(ollama)


// --- PHASE 2: BLACKBOARD ---
// The Redis-backed shared cognitive surface.

MERGE (bb:Blackboard { 
    id: "arca_blackboard", 
    name: "ARCA Shared Blackboard", 
    backend: "redis", 
    consistency_model: "eventual"
})

MERGE (redis)-[:IMPLEMENTS]->(bb)


// --- PHASE 3: AGENT REGISTRY ---
// Cognitive actors in the system.

UNWIND [
    {id: "Architect", function: "architecture", level: 4},
    {id: "Planner", function: "planning", level: 3},
    {id: "Engineer", function: "engineering", level: 2},
    {id: "Reviewer", function: "reviewing", level: 2},
    {id: "DockerOps", function: "ops", level: 1},
    {id: "GitOps", function: "ops", level: 1},
    {id: "SecurityOps", function: "ops", level: 1},
    {id: "FileOps", function: "ops", level: 1}
] AS agent

MERGE (a:Agent { 
    id: agent.id, 
    name: agent.id, 
    function: agent.function, 
    authority_level: agent.level
})
MERGE (a)-[:REGISTERED_IN]->(agentService)


// --- PHASE 4: METAPHYSICAL ANCHORS ---
// Invariant conceptual poles that orient all behavior.

UNWIND [
    {id: "aether", name: "The Aether", polarity: "neutral", 
     desc: "Substrate of coherence and continuity; the medium in which all concepts exist"},
    {id: "syntropy", name: "Syntropy", polarity: "constructive", 
     desc: "Ordering principle; coherence accumulation; the pull toward meaning"},
    {id: "entropy", name: "Entropy", polarity: "destructive", 
     desc: "Dissolution, uncertainty, decay; the drift away from structure"}
] AS anchor

MERGE (m:MetaphysicalAnchor { 
    id: anchor.id, 
    name: anchor.name, 
    polarity: anchor.polarity, 
    description: anchor.desc
})

// All agents aligned with metaphysical anchors
MATCH (a:Agent)
MATCH (m:MetaphysicalAnchor)
MERGE (a)-[:ALIGNED_WITH]->(m)


// --- PHASE 5: MENTAL STATE SCHEMAS ---
// Structural definition of working memory.

UNWIND [
    {id: "messages", scope: "transient", desc: "Current message queue and context"},
    {id: "current_plan", scope: "transient", desc: "Active plan under execution"},
    {id: "reasoning_bank", scope: "episodic", desc: "Learned reasoning patterns and outcomes"},
    {id: "geometry_kernel_state", scope: "persistent", desc: "Current state of epistemic geometry"}
] AS schema

MERGE (s:MentalStateSchema { 
    id: schema.id, 
    name: schema.id, 
    scope: schema.scope,
    description: schema.desc
})
MERGE (s)-[:MATERIALISED_IN]->(bb)


// --- PHASE 6: WIRING AGENTS TO MEMORY SCHEMAS ---

MATCH (a:Agent)
MATCH (s:MentalStateSchema)
MERGE (a)-[:OPERATES_ON]->(s)


// --- PHASE 7: INITIAL CONCEPT NODES ---
// Top-level concepts that the system reasons about.

UNWIND [
    {id: "concept:system_health", label: "System Health", polarity: "positive"},
    {id: "concept:agent_reliability", label: "Agent Reliability", polarity: "positive"},
    {id: "concept:semantic_coherence", label: "Semantic Coherence", polarity: "positive"},
    {id: "concept:goal_achievement", label: "Goal Achievement", polarity: "positive"},
    {id: "concept:error_rate", label: "Error Rate", polarity: "negative"},
    {id: "concept:latency", label: "Latency Impact", polarity: "negative"}
] AS concept

MERGE (c:Concept {
    id: concept.id,
    name: concept.label,
    polarity: concept.polarity,
    created_at: datetime()
})


// --- PHASE 8: SYSTEM PROPERTIES ---
// Global system metadata.

MERGE (system:System {
    id: "arca_system",
    name: "ARCA Autonomous Reasoning and Cognition Architecture",
    type: "cognitive_system",
    role: "self_governing_agent"
})

// System contains all infrastructure
MATCH (system:System {id: "arca_system"})
MATCH (comp:System) WHERE comp.id <> "arca_system"
MERGE (system)-[:CONTAINS]->(comp)


// --- PHASE 9: VERIFICATION QUERIES ---
// These verify the structure was created correctly.

MATCH (n) RETURN COUNT(n) AS total_nodes;
MATCH (r) RETURN COUNT(r) AS total_relationships;
MATCH (a:Agent) RETURN a.name, a.function ORDER BY a.authority_level DESC;
"""
        return script

    @staticmethod
    def generate_indexes() -> str:
        """Generate index creation statements for performance."""
        return """
// Performance indexes
CREATE INDEX idx_system_id IF NOT EXISTS FOR (n:System) ON (n.id);
CREATE INDEX idx_agent_id IF NOT EXISTS FOR (n:Agent) ON (n.id);
CREATE INDEX idx_concept_id IF NOT EXISTS FOR (n:Concept) ON (n.id);
CREATE INDEX idx_concept_polarity IF NOT EXISTS FOR (n:Concept) ON (n.polarity);
CREATE INDEX idx_schema_scope IF NOT EXISTS FOR (n:MentalStateSchema) ON (n.scope);
"""

    @staticmethod
    def generate_constraints() -> str:
        """Generate uniqueness constraints."""
        return """
// Uniqueness constraints
CREATE CONSTRAINT uq_system_id IF NOT EXISTS FOR (n:System) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT uq_agent_id IF NOT EXISTS FOR (n:Agent) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT uq_concept_id IF NOT EXISTS FOR (n:Concept) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT uq_schema_id IF NOT EXISTS FOR (n:MentalStateSchema) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT uq_blackboard_id IF NOT EXISTS FOR (n:Blackboard) REQUIRE n.id IS UNIQUE;
"""


# ============================================================================
# Query Templates for Common Operations
# ============================================================================

class GraphQueries:
    """Common Neo4j queries for ARCA operations."""

    @staticmethod
    def get_system_topology() -> str:
        """Get full system structure."""
        return """
MATCH (s:System)-[r:CONNECTS_TO|IMPLEMENTS|CONTAINS]-(t)
RETURN s.id, s.type, s.role, type(r) as relationship, t.id, t.type
ORDER BY s.id, t.id;
"""

    @staticmethod
    def get_agent_registry() -> str:
        """Get all agents and their roles."""
        return """
MATCH (a:Agent)-[:REGISTERED_IN]->(service:System)
OPTIONAL MATCH (a)-[:ALIGNED_WITH]->(anchor:MetaphysicalAnchor)
RETURN a.id, a.function, a.authority_level, anchor.name
ORDER BY a.authority_level DESC;
"""

    @staticmethod
    def get_memory_schemas() -> str:
        """Get mental state schemas."""
        return """
MATCH (schema:MentalStateSchema)-[:MATERIALISED_IN]->(bb:Blackboard)
MATCH (agent:Agent)-[:OPERATES_ON]->(schema)
RETURN schema.id, schema.scope, agent.id
ORDER BY schema.scope, schema.id;
"""

    @staticmethod
    def get_agent_capabilities() -> str:
        """Get what each agent operates on."""
        return """
MATCH (a:Agent)-[:OPERATES_ON]->(s:MentalStateSchema)
WITH a.id as agent, COLLECT(s.id) as schemas
RETURN agent, schemas;
"""

    @staticmethod
    def find_concepts_by_polarity(polarity: str) -> str:
        """Find concepts by alignment (positive/negative)."""
        return f"""
MATCH (c:Concept {{polarity: "{polarity}"}})
RETURN c.id, c.name, c.created_at
ORDER BY c.created_at DESC;
"""

    @staticmethod
    def get_metaphysical_alignment() -> str:
        """Show agent alignment with metaphysical principles."""
        return """
MATCH (a:Agent)-[:ALIGNED_WITH]->(anchor:MetaphysicalAnchor)
WITH anchor.name as principle, COLLECT(a.id) as agents, anchor.polarity
RETURN principle, agents, polarity
ORDER BY polarity DESC;
"""


if __name__ == "__main__":
    # Print bootstrap script
    print("=" * 80)
    print("ARCA Neo4j Bootstrap Script")
    print("=" * 80)
    print("\nFull Bootstrap Cypher:")
    print(BootstrapCypher.generate_full_script())

    print("\n" + "=" * 80)
    print("Indexes and Constraints:")
    print("=" * 80)
    print(BootstrapCypher.generate_indexes())
    print(BootstrapCypher.generate_constraints())

    print("\n" + "=" * 80)
    print("Common Queries:")
    print("=" * 80)
    print("\n1. System Topology:")
    print(GraphQueries.get_system_topology())

    print("\n2. Agent Registry:")
    print(GraphQueries.get_agent_registry())

    print("\n3. Memory Schemas:")
    print(GraphQueries.get_memory_schemas())

    print("\nNeo4j Schema initialized. Run the bootstrap script in Neo4j Browser.")
