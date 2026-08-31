"""
Neo4j Schema
Defines the structural identity of ARCA within the Graph Database.
Separates 'What Exists' (Neo4j) from 'What Moves' (Geometry).
"""

class Neo4jSchema:
    """Schema definitions."""
    
    NODES = {
        "System": "Root node representing the ARCA instance.",
        "Agent": "Autonomous computational units (e.g. Architect, Engineer).",
        "Concept": "Epistemic units tracked by Geometry Kernel.",
        "MetaphysicalAnchor": "Immutable truths or core directives (Attractors).",
        "MemoryStore": "Reference to storage systems (Postgres, Redis).",
        "Role": "Functional designations for agents."
    }

    RELATIONSHIPS = {
        "OPERATES_ON": "Agent -> Concept (Agent modifies belief)",
        "MATERIALISED_IN": "Concept -> MemoryStore (Where data lives)",
        "GUIDED_BY": "System -> MetaphysicalAnchor",
        "PART_OF": "Agent -> System",
        "TRACKS": "GeometryKernel -> Concept"
    }

class BootstrapCypher:
    """Generates the initialization script for Neo4j."""

    @staticmethod
    def generate_full_script() -> str:
        return """
// 1. Clear constraints (if any - optional, usually manual)
// 2. Create Constraints
CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT system_id IF NOT EXISTS FOR (s:System) REQUIRE s.id IS UNIQUE;

// 3. Initialize System Root
MERGE (s:System {id: "ARCA_CORE", version: "1.0", status: "active"})

// 4. Initialize Agents
MERGE (arch:Agent {id: "architect", name: "Architect", role: "Planning"})
MERGE (eng:Agent {id: "engineer", name: "Engineer", role: "Implementation"})
MERGE (rev:Agent {id: "reviewer", name: "Reviewer", role: "QualityControl"})
MERGE (orch:Agent {id: "orchestrator", name: "Orchestrator", role: "Coordination"})
MERGE (maint:Agent {id: "maintainer", name: "Maintainer", role: "Operations"})

MERGE (arch)-[:PART_OF]->(s)
MERGE (eng)-[:PART_OF]->(s)
MERGE (rev)-[:PART_OF]->(s)
MERGE (orch)-[:PART_OF]->(s)
MERGE (maint)-[:PART_OF]->(s)

// 5. Initialize Memory Stores
MERGE (mem_epi:MemoryStore {id: "episodic_postgres", type: "SQL"})
MERGE (mem_sem:MemoryStore {id: "semantic_qwen", type: "VectorDB"})
MERGE (mem_str:MemoryStore {id: "structural_neo4j", type: "Graph"})

MERGE (s)-[:HAS_MEMORY]->(mem_epi)
MERGE (s)-[:HAS_MEMORY]->(mem_sem)
MERGE (s)-[:HAS_MEMORY]->(mem_str)

// 6. Initialize Core Concepts (Mirrors Geometry Kernel)
MERGE (c1:Concept {id: "sys_coherence", name: "System Coherence"})
MERGE (c2:Concept {id: "agent_reliability", name: "Agent Reliability"})
MERGE (c3:Concept {id: "memory_consistency", name: "Memory Consistency"})

MERGE (s)-[:TRACKS]->(c1)
MERGE (s)-[:TRACKS]->(c2)
MERGE (s)-[:TRACKS]->(c3)

RETURN s, arch, eng, rev, orch, c1, c2, c3;
"""

if __name__ == "__main__":
    print(BootstrapCypher.generate_full_script())
