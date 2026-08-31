"""
Bicameral V2: Reflex Programming System

Implements the "Reflex Constraint" pattern where natural language directives
are mapped to hypervector constraints that continuously modulate HSE kernel behavior.

Architecture:
    Text Constraint ("Watch for database latency") 
        → AFLASHEncoder → Constraint Hypervector 
        → HSE Kernel Constraint Field 
        → Continuous Attention/Alerting

The "Language of Thought" (LoT) enables secure agent-to-agent communication
via hyperdimensional vectors - bypassing serialization for instant resonance detection.
"""

import os
import sys
import logging
import numpy as np
import json
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

# Import HDC tools
_this_dir = os.path.dirname(os.path.abspath(__file__))
_mcp_tools_path = os.path.join(_this_dir, '..', 'mcp_server', 'tools')
if _mcp_tools_path not in sys.path:
    sys.path.insert(0, _mcp_tools_path)

try:
    from hdc_memory import HDCEngine, AFLASHEncoder
except ImportError:
    from services.mcp_server.tools.hdc_memory import HDCEngine, AFLASHEncoder

logger = logging.getLogger(__name__)

# =============================================================================
# Reflex Constraint System (Bicameral V2)
# =============================================================================

@dataclass
class ReflexConstraint:
    """
    A single reflex constraint that monitors system state.
    
    The constraint is active when the similarity between the current
    system state vector and the constraint vector exceeds the threshold.
    """
    id: str
    text: str  # Original natural language constraint
    vector: np.ndarray  # HDC representation
    threshold: float = 0.3  # Activation threshold
    priority: int = 1  # 1-10, higher = more important
    action: str = "alert"  # alert | block | log | callback
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    triggered_count: int = 0
    last_triggered: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "text": self.text,
            "threshold": self.threshold,
            "priority": self.priority,
            "action": self.action,
            "created_at": self.created_at,
            "triggered_count": self.triggered_count,
            "last_triggered": self.last_triggered,
            "metadata": self.metadata
        }


class BicameralReflexEngine:
    """
    The Bicameral Reflex Engine: Maps natural language to HDC constraint vectors.
    
    "Watch for database latency" → V_constraint
    
    The HSE kernel continuously checks:
        similarity(V_state, V_constraint) > threshold → Trigger reflex
    
    This creates a "subconscious" attention layer that operates below
    the explicit reasoning level - like reflexes in biological systems.
    """
    
    def __init__(self, dimensionality: int = 10000):
        self.hdc = HDCEngine(dimensionality=dimensionality)
        self.encoder = AFLASHEncoder(self.hdc)
        self.constraints: Dict[str, ReflexConstraint] = {}
        
        # Predefined concept anchors for common monitoring patterns
        self._concept_anchors = {
            "database": self.hdc.get_basis("DATABASE_CONCEPT"),
            "latency": self.hdc.get_basis("LATENCY_CONCEPT"),
            "error": self.hdc.get_basis("ERROR_CONCEPT"),
            "security": self.hdc.get_basis("SECURITY_CONCEPT"),
            "memory": self.hdc.get_basis("MEMORY_CONCEPT"),
            "cpu": self.hdc.get_basis("CPU_CONCEPT"),
            "network": self.hdc.get_basis("NETWORK_CONCEPT"),
            "disk": self.hdc.get_basis("DISK_CONCEPT"),
            "timeout": self.hdc.get_basis("TIMEOUT_CONCEPT"),
            "failure": self.hdc.get_basis("FAILURE_CONCEPT"),
            "anomaly": self.hdc.get_basis("ANOMALY_CONCEPT"),
            "spike": self.hdc.get_basis("SPIKE_CONCEPT"),
            "threshold": self.hdc.get_basis("THRESHOLD_CONCEPT"),
        }
        
        logger.info(f"BicameralReflexEngine initialized with {dimensionality}D vectors")

    def _generate_constraint_id(self, text: str) -> str:
        """Generate deterministic ID from constraint text."""
        return hashlib.sha256(text.encode()).hexdigest()[:12]

    def _enhance_with_anchors(self, base_vector: np.ndarray, text: str) -> np.ndarray:
        """
        Enhance the base text vector by binding with relevant concept anchors.
        This improves matching against system state vectors that use the same anchors.
        """
        text_lower = text.lower()
        enhanced = base_vector.copy()
        
        for concept, anchor in self._concept_anchors.items():
            if concept in text_lower:
                # Bind the concept anchor to strengthen the signal
                enhanced = self.hdc.bundle([enhanced, anchor])
                logger.debug(f"Enhanced constraint with anchor: {concept}")
        
        return enhanced

    def set_reflex_constraint(
        self,
        text: str,
        threshold: float = 0.3,
        priority: int = 5,
        action: str = "alert",
        metadata: Optional[Dict] = None
    ) -> ReflexConstraint:
        """
        Map a natural language constraint to an HDC vector.
        
        Args:
            text: Natural language constraint (e.g., "Watch for database latency")
            threshold: Activation threshold (0.0-1.0)
            priority: Importance level (1-10)
            action: Response type: alert | block | log | callback
            metadata: Additional constraint metadata
        
        Returns:
            The created ReflexConstraint object
        
        Example:
            engine.set_reflex_constraint(
                "Watch for database latency exceeding 500ms",
                threshold=0.4,
                priority=8,
                action="alert"
            )
        """
        constraint_id = self._generate_constraint_id(text)
        
        # Encode text to hypervector
        base_vector = self.encoder.encode_text(text)
        
        # Enhance with concept anchors
        enhanced_vector = self._enhance_with_anchors(base_vector, text)
        
        constraint = ReflexConstraint(
            id=constraint_id,
            text=text,
            vector=enhanced_vector,
            threshold=threshold,
            priority=priority,
            action=action,
            metadata=metadata or {}
        )
        
        self.constraints[constraint_id] = constraint
        logger.info(f"Set reflex constraint: {constraint_id} - '{text[:50]}...'")
        
        return constraint

    def check_constraints(self, state_vector: np.ndarray) -> List[Tuple[ReflexConstraint, float]]:
        """
        Check all constraints against the current state vector.
        
        Returns list of (constraint, similarity) tuples for triggered constraints.
        """
        triggered = []
        
        for cid, constraint in self.constraints.items():
            sim = self.hdc.similarity(state_vector, constraint.vector)
            
            if sim >= constraint.threshold:
                constraint.triggered_count += 1
                constraint.last_triggered = datetime.utcnow().isoformat()
                triggered.append((constraint, sim))
                logger.warning(
                    f"REFLEX TRIGGERED: {constraint.text[:40]}... "
                    f"(sim={sim:.3f}, threshold={constraint.threshold})"
                )
        
        # Sort by priority (descending) then similarity (descending)
        triggered.sort(key=lambda x: (-x[0].priority, -x[1]))
        return triggered

    def remove_constraint(self, constraint_id: str) -> bool:
        """Remove a constraint by ID."""
        if constraint_id in self.constraints:
            del self.constraints[constraint_id]
            logger.info(f"Removed constraint: {constraint_id}")
            return True
        return False

    def list_constraints(self) -> List[Dict]:
        """List all active constraints."""
        return [c.to_dict() for c in self.constraints.values()]

    def get_constraint_vector(self, constraint_id: str) -> Optional[np.ndarray]:
        """Get the raw vector for a constraint (for visualization/debugging)."""
        if constraint_id in self.constraints:
            return self.constraints[constraint_id].vector
        return None


# =============================================================================
# Language of Thought (LoT) - Agent-to-Agent Communication
# =============================================================================

@dataclass
class ThoughtVector:
    """
    A thought vector for inter-agent communication.
    
    Instead of serializing complex data structures, agents can
    communicate intentions and states via hypervectors that
    preserve semantic relationships.
    """
    source_agent: str
    target_agent: str  # "*" for broadcast
    intent: str  # Human-readable intent
    vector: np.ndarray
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    urgency: float = 0.5  # 0.0-1.0
    requires_ack: bool = False
    correlation_id: Optional[str] = None
    
    def to_serializable(self) -> Dict:
        """Convert to JSON-serializable dict (vector as base64)."""
        import base64
        return {
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "intent": self.intent,
            "vector_b64": base64.b64encode(self.vector.tobytes()).decode(),
            "vector_dtype": str(self.vector.dtype),
            "vector_shape": list(self.vector.shape),
            "timestamp": self.timestamp,
            "urgency": self.urgency,
            "requires_ack": self.requires_ack,
            "correlation_id": self.correlation_id
        }
    
    @classmethod
    def from_serializable(cls, data: Dict) -> "ThoughtVector":
        """Reconstruct from serialized dict."""
        import base64
        vector = np.frombuffer(
            base64.b64decode(data["vector_b64"]),
            dtype=np.dtype(data["vector_dtype"])
        ).reshape(data["vector_shape"])
        return cls(
            source_agent=data["source_agent"],
            target_agent=data["target_agent"],
            intent=data["intent"],
            vector=vector,
            timestamp=data["timestamp"],
            urgency=data["urgency"],
            requires_ack=data["requires_ack"],
            correlation_id=data.get("correlation_id")
        )


class LanguageOfThought:
    """
    Language of Thought (LoT) System for secure agent-to-agent communication.
    
    Key Properties:
    1. Semantic Preservation: Related thoughts have similar vectors
    2. Instant Resonance: Receiving agent can "feel" relevance without parsing
    3. Compositionality: Thoughts can be combined via HDC operations
    4. Privacy: Raw vectors don't expose the original text
    
    Communication Flow:
        Agent A: send_thought_vector("Detected anomaly in auth service")
            → V_thought published to thought bus
        Agent B: Monitors bus, checks similarity(V_thought, V_interests)
            → If resonant, processes the thought
    """
    
    def __init__(self, agent_id: str, dimensionality: int = 10000):
        self.agent_id = agent_id
        self.hdc = HDCEngine(dimensionality=dimensionality)
        self.encoder = AFLASHEncoder(self.hdc)
        
        # Interest vectors - what this agent "listens" for
        self.interests: Dict[str, np.ndarray] = {}
        
        # Incoming thought buffer
        self.thought_buffer: List[ThoughtVector] = []
        self.max_buffer_size = 100
        
        # Agent capability vector (what this agent can do)
        self.capability_vector: Optional[np.ndarray] = None
        
        logger.info(f"LanguageOfThought initialized for agent: {agent_id}")

    def register_interest(self, interest_name: str, interest_text: str) -> np.ndarray:
        """
        Register an interest for this agent.
        
        The agent will "resonate" with thoughts similar to this interest.
        
        Example:
            lot.register_interest("security", "security alerts authentication failures")
        """
        vector = self.encoder.encode_text(interest_text)
        self.interests[interest_name] = vector
        logger.info(f"Agent {self.agent_id} registered interest: {interest_name}")
        return vector

    def set_capability(self, capability_description: str):
        """
        Set this agent's capability vector.
        
        Other agents can query capabilities via vector similarity.
        """
        self.capability_vector = self.encoder.encode_text(capability_description)
        logger.info(f"Agent {self.agent_id} capability set")

    def send_thought_vector(
        self,
        thought_text: str,
        target_agent: str = "*",
        urgency: float = 0.5,
        requires_ack: bool = False,
        correlation_id: Optional[str] = None
    ) -> ThoughtVector:
        """
        Encode and prepare a thought for transmission.
        
        Args:
            thought_text: The thought content
            target_agent: Target agent ID ("*" for broadcast)
            urgency: 0.0-1.0 urgency level
            requires_ack: Whether to require acknowledgment
            correlation_id: Optional correlation ID for tracking
        
        Returns:
            ThoughtVector ready for transmission
        
        Example:
            thought = lot.send_thought_vector(
                "Database connection pool exhausted",
                target_agent="ops_agent",
                urgency=0.9
            )
        """
        vector = self.encoder.encode_text(thought_text)
        
        thought = ThoughtVector(
            source_agent=self.agent_id,
            target_agent=target_agent,
            intent=thought_text,
            vector=vector,
            urgency=urgency,
            requires_ack=requires_ack,
            correlation_id=correlation_id
        )
        
        logger.info(
            f"Thought prepared: {self.agent_id} → {target_agent}: "
            f"'{thought_text[:40]}...' (urgency={urgency})"
        )
        
        return thought

    def receive_thought(self, thought: ThoughtVector) -> Tuple[bool, float, Optional[str]]:
        """
        Receive and process an incoming thought.
        
        Returns:
            (is_relevant, max_resonance, matched_interest_name)
        """
        # Check if this thought is for us
        if thought.target_agent not in ("*", self.agent_id):
            return False, 0.0, None
        
        # Check resonance with all interests
        max_resonance = 0.0
        matched_interest = None
        
        for interest_name, interest_vector in self.interests.items():
            sim = self.hdc.similarity(thought.vector, interest_vector)
            if sim > max_resonance:
                max_resonance = sim
                matched_interest = interest_name
        
        # Buffer the thought if relevant (resonance > 0.2)
        is_relevant = max_resonance > 0.2
        if is_relevant:
            self.thought_buffer.append(thought)
            if len(self.thought_buffer) > self.max_buffer_size:
                self.thought_buffer.pop(0)
            
            logger.info(
                f"Thought received by {self.agent_id}: "
                f"resonance={max_resonance:.3f} (interest: {matched_interest})"
            )
        
        return is_relevant, max_resonance, matched_interest

    def compose_thoughts(self, thoughts: List[ThoughtVector]) -> np.ndarray:
        """
        Compose multiple thoughts into a unified representation.
        
        This enables "meta-cognition" - reasoning about multiple thoughts.
        """
        vectors = [t.vector for t in thoughts]
        return self.hdc.bundle(vectors)

    def query_capability(self, query_text: str, other_capability: np.ndarray) -> float:
        """
        Check if another agent's capability matches a query.
        
        Returns similarity score.
        """
        query_vector = self.encoder.encode_text(query_text)
        return self.hdc.similarity(query_vector, other_capability)

    def get_pending_thoughts(self, min_urgency: float = 0.0) -> List[ThoughtVector]:
        """Get pending thoughts above urgency threshold."""
        return [t for t in self.thought_buffer if t.urgency >= min_urgency]

    def clear_thought_buffer(self):
        """Clear the thought buffer."""
        self.thought_buffer.clear()


# =============================================================================
# Genesis Chain Hyper-Spatial Integration
# =============================================================================

class GenesisHyperSpatial:
    """
    Maps Genesis Chain operations to hyperdimensional functions.
    
    The Genesis Chain (Architect → Planner → Executor) operates in a
    hyper-spatial manifold where:
    
    1. Design Intent → V_intent (high-level goal vector)
    2. Plan Steps → V_plan[] (sequence of operation vectors)  
    3. Execution State → V_state (current system state)
    
    Verification: similarity(V_intent, V_outcome) > threshold
    
    This enables "Holographic Verification" - ensuring that executed
    actions actually achieved the intended outcome, not just completed.
    """
    
    def __init__(self, dimensionality: int = 10000):
        self.hdc = HDCEngine(dimensionality=dimensionality)
        self.encoder = AFLASHEncoder(self.hdc)
        
        # Genesis Chain phase vectors (fixed basis)
        self.phase_vectors = {
            "architect": self.hdc.get_basis("GENESIS_ARCHITECT"),
            "planner": self.hdc.get_basis("GENESIS_PLANNER"),
            "executor": self.hdc.get_basis("GENESIS_EXECUTOR"),
            "verifier": self.hdc.get_basis("GENESIS_VERIFIER"),
        }
        
        # Track active jobs
        self.active_jobs: Dict[str, Dict] = {}
        
        logger.info("GenesisHyperSpatial initialized")

    def encode_intent(self, intent_text: str, job_id: str) -> np.ndarray:
        """
        Encode the architect's design intent into V_intent.
        
        This vector serves as the "goal state" for verification.
        """
        base_vector = self.encoder.encode_text(intent_text)
        
        # Bind with architect phase
        v_intent = self.hdc.bind(base_vector, self.phase_vectors["architect"])
        
        self.active_jobs[job_id] = {
            "v_intent": v_intent,
            "intent_text": intent_text,
            "plan_vectors": [],
            "execution_vectors": [],
            "created_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Genesis intent encoded: job={job_id}")
        return v_intent

    def encode_plan_step(self, step_text: str, job_id: str, step_index: int) -> np.ndarray:
        """
        Encode a plan step into V_step.
        
        Steps are permuted by their index to preserve sequence.
        """
        if job_id not in self.active_jobs:
            raise ValueError(f"Unknown job: {job_id}")
        
        base_vector = self.encoder.encode_text(step_text)
        
        # Bind with planner phase and permute by step index
        v_step = self.hdc.bind(base_vector, self.phase_vectors["planner"])
        v_step = self.hdc.permute(v_step, step_index)
        
        self.active_jobs[job_id]["plan_vectors"].append({
            "index": step_index,
            "text": step_text,
            "vector": v_step
        })
        
        return v_step

    def encode_execution_result(
        self, 
        result_text: str, 
        job_id: str, 
        step_index: int
    ) -> Tuple[np.ndarray, float]:
        """
        Encode execution result and compute alignment with plan.
        
        Returns (v_result, alignment_score).
        """
        if job_id not in self.active_jobs:
            raise ValueError(f"Unknown job: {job_id}")
        
        job = self.active_jobs[job_id]
        base_vector = self.encoder.encode_text(result_text)
        
        # Bind with executor phase
        v_result = self.hdc.bind(base_vector, self.phase_vectors["executor"])
        
        # Find corresponding plan step
        plan_step = None
        for ps in job["plan_vectors"]:
            if ps["index"] == step_index:
                plan_step = ps
                break
        
        # Compute alignment
        alignment = 0.0
        if plan_step is not None:
            # Compare result (unpermuted) with plan step (unpermuted)
            v_plan_base = self.hdc.permute(plan_step["vector"], -step_index)
            v_result_base = v_result
            alignment = self.hdc.similarity(v_plan_base, v_result_base)
        
        job["execution_vectors"].append({
            "index": step_index,
            "text": result_text,
            "vector": v_result,
            "alignment": alignment
        })
        
        logger.info(f"Execution result: job={job_id}, step={step_index}, alignment={alignment:.3f}")
        return v_result, alignment

    def verify_job_completion(self, job_id: str, outcome_text: str) -> Dict[str, Any]:
        """
        Holographic verification of job completion.
        
        Checks if the final outcome aligns with the original intent.
        """
        if job_id not in self.active_jobs:
            raise ValueError(f"Unknown job: {job_id}")
        
        job = self.active_jobs[job_id]
        
        # Encode outcome
        v_outcome = self.encoder.encode_text(outcome_text)
        v_outcome = self.hdc.bind(v_outcome, self.phase_vectors["verifier"])
        
        # Compare with intent
        intent_alignment = self.hdc.similarity(v_outcome, job["v_intent"])
        
        # Compute aggregate plan alignment
        if job["execution_vectors"]:
            plan_alignments = [ev["alignment"] for ev in job["execution_vectors"]]
            avg_plan_alignment = np.mean(plan_alignments)
        else:
            avg_plan_alignment = 0.0
        
        # Overall score
        overall_score = 0.6 * intent_alignment + 0.4 * avg_plan_alignment
        
        result = {
            "job_id": job_id,
            "intent_alignment": float(intent_alignment),
            "plan_alignment": float(avg_plan_alignment),
            "overall_score": float(overall_score),
            "verified": overall_score > 0.3,
            "intent_text": job["intent_text"],
            "outcome_text": outcome_text,
            "steps_executed": len(job["execution_vectors"]),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(
            f"Job verification: {job_id} - "
            f"intent={intent_alignment:.3f}, plan={avg_plan_alignment:.3f}, "
            f"overall={overall_score:.3f}, verified={result['verified']}"
        )
        
        return result


# =============================================================================
# Neo4j HDC Integration Analysis
# =============================================================================

class Neo4jHDCBridge:
    """
    Bridge between Neo4j graph and HDC vector space.
    
    ANALYSIS: Does Neo4j need to move to in-memory OCI for HDC?
    
    Answer: NO - but with caveats:
    
    1. Neo4j stays as the "structural backbone" (relationships, queries)
    2. HDC provides a "semantic overlay" for fast similarity operations
    3. The bridge syncs key entities to HDC vectors
    
    Architecture:
        Neo4j (Graph) ←→ HDCBridge ←→ In-Memory HDC Space
        
        - Entities (services, functions, concepts) → HDC basis vectors
        - Relationships → Bound HDC vectors (V_a ⊗ V_rel ⊗ V_b)
        - Queries → Vector similarity search in HDC space
    
    This hybrid approach keeps Neo4j for complex graph traversals while
    enabling O(1) semantic similarity checks via HDC.
    """
    
    def __init__(self, dimensionality: int = 10000):
        self.hdc = HDCEngine(dimensionality=dimensionality)
        self.encoder = AFLASHEncoder(self.hdc)
        
        # Entity cache (synced from Neo4j)
        self.entity_vectors: Dict[str, np.ndarray] = {}
        
        # Relationship type vectors
        self.rel_type_vectors: Dict[str, np.ndarray] = {}
        
        # Composite relationship vectors (entity-rel-entity triples)
        self.triple_vectors: List[Dict] = []
        
        logger.info("Neo4jHDCBridge initialized")

    def sync_entity(self, entity_id: str, entity_type: str, properties: Dict) -> np.ndarray:
        """
        Sync a Neo4j entity to HDC space.
        
        The vector encodes: type + key properties.
        """
        # Build text representation
        prop_text = " ".join(f"{k}:{v}" for k, v in properties.items() if v)
        entity_text = f"{entity_type} {entity_id} {prop_text}"
        
        # Encode
        v_entity = self.encoder.encode_text(entity_text)
        
        # Bind with type basis for type-aware similarity
        v_type = self.hdc.get_basis(f"NEO4J_TYPE_{entity_type.upper()}")
        v_entity = self.hdc.bind(v_entity, v_type)
        
        self.entity_vectors[entity_id] = v_entity
        return v_entity

    def sync_relationship(
        self, 
        source_id: str, 
        rel_type: str, 
        target_id: str,
        properties: Optional[Dict] = None
    ) -> np.ndarray:
        """
        Encode a Neo4j relationship as an HDC triple.
        
        V_triple = V_source ⊗ V_rel ⊗ V_target
        """
        # Get or create entity vectors
        v_source = self.entity_vectors.get(source_id)
        v_target = self.entity_vectors.get(target_id)
        
        if v_source is None or v_target is None:
            raise ValueError(f"Entities must be synced before relationships")
        
        # Get relationship type vector
        if rel_type not in self.rel_type_vectors:
            self.rel_type_vectors[rel_type] = self.hdc.get_basis(f"REL_{rel_type.upper()}")
        v_rel = self.rel_type_vectors[rel_type]
        
        # Create triple: source ⊗ rel ⊗ target
        v_triple = self.hdc.bind(self.hdc.bind(v_source, v_rel), v_target)
        
        self.triple_vectors.append({
            "source": source_id,
            "rel_type": rel_type,
            "target": target_id,
            "vector": v_triple
        })
        
        return v_triple

    def query_similar_entities(
        self, 
        query_text: str, 
        entity_type: Optional[str] = None,
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Find entities similar to query text.
        
        This is O(n) but very fast due to vectorized operations.
        For large graphs, consider approximate methods.
        """
        v_query = self.encoder.encode_text(query_text)
        
        if entity_type:
            v_type = self.hdc.get_basis(f"NEO4J_TYPE_{entity_type.upper()}")
            v_query = self.hdc.bind(v_query, v_type)
        
        results = []
        for entity_id, v_entity in self.entity_vectors.items():
            sim = self.hdc.similarity(v_query, v_entity)
            results.append((entity_id, sim))
        
        results.sort(key=lambda x: -x[1])
        return results[:top_k]

    def query_relationships(
        self, 
        source_id: Optional[str] = None,
        rel_type: Optional[str] = None,
        target_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Query relationships by pattern matching.
        
        Any of source_id, rel_type, target_id can be None (wildcard).
        """
        results = []
        for triple in self.triple_vectors:
            if source_id and triple["source"] != source_id:
                continue
            if rel_type and triple["rel_type"] != rel_type:
                continue
            if target_id and triple["target"] != target_id:
                continue
            results.append(triple)
        return results


# =============================================================================
# Singleton Instances
# =============================================================================

_reflex_engine: Optional[BicameralReflexEngine] = None
_genesis_hyper: Optional[GenesisHyperSpatial] = None
_neo4j_bridge: Optional[Neo4jHDCBridge] = None
_lot_instance: Optional[LanguageOfThought] = None


def get_reflex_engine() -> BicameralReflexEngine:
    """Get or create the global reflex engine."""
    global _reflex_engine
    if _reflex_engine is None:
        _reflex_engine = BicameralReflexEngine()
    return _reflex_engine


# Alias for MCP compatibility
def get_bicameral_engine() -> BicameralReflexEngine:
    """Alias for get_reflex_engine (MCP-friendly)."""
    return get_reflex_engine()


def get_genesis_hyper() -> GenesisHyperSpatial:
    """Get or create the Genesis hyper-spatial engine."""
    global _genesis_hyper
    if _genesis_hyper is None:
        _genesis_hyper = GenesisHyperSpatial()
    return _genesis_hyper


def get_neo4j_bridge() -> Neo4jHDCBridge:
    """Get or create the Neo4j-HDC bridge."""
    global _neo4j_bridge
    if _neo4j_bridge is None:
        _neo4j_bridge = Neo4jHDCBridge()
    return _neo4j_bridge


def get_lot(agent_id: str = "default_agent") -> LanguageOfThought:
    """Get or create the Language of Thought instance."""
    global _lot_instance
    if _lot_instance is None:
        _lot_instance = LanguageOfThought(agent_id)
    return _lot_instance
