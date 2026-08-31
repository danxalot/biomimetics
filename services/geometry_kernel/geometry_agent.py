"""
Geometry Agent Interface - Bridge between DeepSeek and the Geometry Kernel

This module enables agents (ARCA, Serena, Maintainer Agents) to communicate
through geometry rather than raw text.

Key principles:
- Agents receive KernelState (topology), not text
- Agents output Force Proposals (structured intent)
- The Kernel is the sole authority on how truth moves
- DeepSeek handles "Why" and "What", Kernel handles "How"

Protocol:
1. Agent receives state topology (JSON or simplified view)
2. Agent reasons about anomalies/objectives
3. Agent outputs Force Proposals
4. Kernel validates and applies forces
5. New state is returned to agent
"""

import json
import logging
import requests
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .core import (
    GeometryKernel, KernelState, ConceptNode, Attractor, Force,
    Vector3D, ForceSource, Mode, EvaluationOutcome
)

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Specialized agent roles with different geometric perspectives."""
    ARCHITECT = "architect"     # System-level topology
    SECURITY = "security"       # Anomaly detection in geometry
    GIT = "git"                 # Version topology (before/after)
    FILE = "file"               # Ontological mapping
    DOCKER = "docker"           # State space convergence
    SERENA = "serena"           # Code refactoring geometry


@dataclass
class GeometricView:
    """
    Simplified view of KernelState for agent consumption.
    
    Focuses on:
    - Node positions and relationships
    - Anomalies (high energy, drift from attractors)
    - Topology delta (what changed)
    """
    state_id: str
    timestamp: str
    
    # Node summary
    nodes: List[Dict[str, Any]]  # [{id, position, velocity_magnitude, energy, stability}]
    
    # Attractor summary
    attractors: List[Dict[str, Any]]  # [{id, center, radius, depth}]
    
    # Anomalies detected
    anomalies: List[Dict[str, Any]]  # [{type, node_id, severity, description}]
    
    # Health metrics
    stability_index: float
    entropy_level: float
    
    def to_prompt_context(self) -> str:
        """Convert to text context for DeepSeek prompt."""
        lines = [
            f"## Geometric State: {self.state_id}",
            f"Timestamp: {self.timestamp}",
            f"Stability: {self.stability_index:.2f}",
            f"Entropy: {self.entropy_level:.2f}",
            "",
            "### Concept Nodes:",
        ]
        
        for node in self.nodes:
            pos = node['position']
            lines.append(
                f"- {node['id']}: pos=[{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], "
                f"energy={node['energy']:.2f}, stability={node['stability']:.2f}"
            )
        
        if self.attractors:
            lines.append("\n### Attractors (Safe States):")
            for attr in self.attractors:
                center = attr['center']
                lines.append(
                    f"- {attr['id']}: center=[{center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f}], "
                    f"radius={attr['radius']:.2f}, pull={attr['depth']:.2f}"
                )
        
        if self.anomalies:
            lines.append("\n### ⚠️ Anomalies Detected:")
            for anomaly in self.anomalies:
                lines.append(f"- [{anomaly['severity']}] {anomaly['type']}: {anomaly['description']}")
        
        return "\n".join(lines)


@dataclass
class ForceProposal:
    """
    Agent's proposed force on the geometry.
    
    Similar to Force but includes agent reasoning.
    """
    target_id: str
    vector: List[float]  # [x, y, z]
    magnitude: float
    source: str  # evidence, contradiction, correction
    reasoning: str
    agent_role: str
    
    def to_force(self) -> Force:
        """Convert to core.Force for kernel application."""
        source_map = {
            "evidence": ForceSource.EVIDENCE,
            "contradiction": ForceSource.CONTRADICTION,
            "correction": ForceSource.EVIDENCE,  # corrections are evidence-based
            "decay": ForceSource.DECAY,
        }
        return Force(
            target_id=self.target_id,
            vector=Vector3D.from_list(self.vector),
            magnitude=self.magnitude,
            source=source_map.get(self.source, ForceSource.EVIDENCE),
            rationale=self.reasoning
        )


class GeometryAgentInterface:
    """
    Bridge between LLM agents and the Geometry Kernel.
    
    Provides:
    1. State projection (KernelState -> GeometricView for agent)
    2. Force parsing (Agent output -> ForceProposal)
    3. Recursive interrogation (drill down levels)
    4. Agent-to-agent geometry exchange
    """
    
    # DeepSeek R1 endpoint
    DEEPSEEK_URL = "http://127.0.0.1:11434/v1/chat/completions"
    DEEPSEEK_MODEL = "DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M"
    
    # Prompt templates for different agent roles
    ROLE_PROMPTS = {
        AgentRole.SECURITY: """You are a Security Geometry Agent.
Your task is to analyze the geometric state for anomalies and propose corrective forces.

ANOMALY PATTERNS:
- Unclosed Loops: Data flows that don't return to secure state
- Unauthorized Bridges: Edges connecting isolated security domains
- High Energy Nodes: Concepts under contradiction/stress

OUTPUT FORMAT (JSON only):
{
  "analysis": "description of what you found",
  "forces": [
    {"target_id": "node_id", "vector": [x, y, z], "magnitude": 0.1, "source": "correction", "reasoning": "why"}
  ]
}""",
        
        AgentRole.GIT: """You are a Git Topology Agent.
Your task is to compare geometric states (before/after) and classify the change.

CLASSIFICATION:
- REFACTOR: Same topology, different text (nodes unchanged)
- FEATURE: New nodes appeared
- BUGFIX: Energy decreased (contradictions resolved)
- REGRESSION: Energy increased (new contradictions)

OUTPUT FORMAT (JSON only):
{
  "change_type": "REFACTOR|FEATURE|BUGFIX|REGRESSION",
  "topology_delta": "description of structural change",
  "forces": []
}""",
        
        AgentRole.ARCHITECT: """You are an Architect Topology Agent.
Your task is to analyze the overall system geometry and propose structural changes.

FOCUS ON:
- System coherence (are nodes well-connected?)
- Attractor coverage (are all nodes near safe states?)
- Energy distribution (is tension localized or distributed?)

OUTPUT FORMAT (JSON only):
{
  "assessment": "system health description",
  "recommendations": ["list of changes"],
  "forces": [
    {"target_id": "node_id", "vector": [x, y, z], "magnitude": 0.1, "source": "evidence", "reasoning": "why"}
  ]
}""",
        
        AgentRole.DOCKER: """You are a Docker State Agent.
Your task is to analyze container topology and propose convergence forces.

FOCUS ON:
- Container health nodes (running, stopped, unhealthy)
- Dependency edges (service → database, api → cache)
- Resource saturation (high energy = resource exhaustion)
- Restart loops (high velocity = unstable container)

OUTPUT FORMAT (JSON only):
{
  "container_health": "overview of container states",
  "dependency_issues": ["broken edges or missing connections"],
  "forces": [
    {"target_id": "container:name", "vector": [x, y, z], "magnitude": 0.1, "source": "correction", "reasoning": "why restart/scale/reconfigure"}
  ]
}""",
        
        AgentRole.FILE: """You are a File Ontology Agent.
Your task is to analyze file system topology and propose structural changes.

FOCUS ON:
- File hierarchy (are related files clustered?)
- Configuration drift (high energy = inconsistent config)
- Orphan files (isolated nodes with no connections)
- Import chains (edges between code files)

OUTPUT FORMAT (JSON only):
{
  "ontology_assessment": "file structure health",
  "drift_detected": ["files that need synchronization"],
  "forces": [
    {"target_id": "file:path", "vector": [x, y, z], "magnitude": 0.1, "source": "evidence", "reasoning": "move/rename/delete suggestion"}
  ]
}""",
        
        AgentRole.SERENA: """You are Serena, the System Proprioception Agent.
Your task is to sense overall system health and propose healing forces.

FOCUS ON:
- Overall stability (are most nodes calm?)
- Anomaly clustering (are problems localized or spreading?)
- Velocity trends (is the system converging or diverging?)
- Attractor drift (have safe states shifted?)

OUTPUT FORMAT (JSON only):
{
  "system_feel": "proprioceptive assessment of system health",
  "anomaly_spread": "localized|spreading|contained",
  "healing_priority": ["ranked list of what to fix first"],
  "forces": [
    {"target_id": "node_id", "vector": [x, y, z], "magnitude": 0.1, "source": "correction", "reasoning": "healing action"}
  ]
}"""
    }
    
    def __init__(
        self,
        kernel: GeometryKernel,
        llm_url: str = None,
        llm_model: str = None
    ):
        """Initialize the agent interface."""
        self.kernel = kernel
        self.llm_url = llm_url or self.DEEPSEEK_URL
        self.llm_model = llm_model or self.DEEPSEEK_MODEL
        
        logger.info(f"GeometryAgentInterface initialized (model={self.llm_model})")
    
    def project_state(
        self, 
        state: KernelState,
        detect_anomalies: bool = True
    ) -> GeometricView:
        """
        Project KernelState into GeometricView for agent consumption.
        
        This is the "lens" through which agents see geometry.
        """
        # Convert nodes to simplified format
        nodes = []
        for nid, node in state.nodes.items():
            nodes.append({
                "id": nid,
                "position": node.position.to_list(),
                "velocity_magnitude": node.velocity.magnitude(),
                "energy": node.energy,
                "stability": node.stability,
                "confidence": node.confidence
            })
        
        # Convert attractors
        attractors = []
        for aid, attr in state.attractors.items():
            attractors.append({
                "id": aid,
                "center": attr.center.to_list(),
                "radius": attr.radius,
                "depth": attr.depth,
                "confidence": attr.confidence
            })
        
        # Detect anomalies
        anomalies = []
        if detect_anomalies:
            anomalies = self._detect_anomalies(state)
        
        return GeometricView(
            state_id=state.id,
            timestamp=state.timestamp.isoformat(),
            nodes=nodes,
            attractors=attractors,
            anomalies=anomalies,
            stability_index=state.health_metrics.get("stability_index", 1.0),
            entropy_level=state.health_metrics.get("entropy_level", 0.0)
        )
    
    def _detect_anomalies(self, state: KernelState) -> List[Dict[str, Any]]:
        """Detect anomalies in the geometric state."""
        anomalies = []
        
        for nid, node in state.nodes.items():
            # High energy = contradiction/tension
            if node.energy > 0.5:
                anomalies.append({
                    "type": "HIGH_ENERGY",
                    "node_id": nid,
                    "severity": "WARNING" if node.energy < 0.8 else "CRITICAL",
                    "description": f"Node '{nid}' has energy {node.energy:.2f} (contradiction detected)"
                })
            
            # High velocity = rapid change
            vel_mag = node.velocity.magnitude()
            if vel_mag > 0.3:
                anomalies.append({
                    "type": "RAPID_DRIFT",
                    "node_id": nid,
                    "severity": "WARNING",
                    "description": f"Node '{nid}' moving at velocity {vel_mag:.2f}"
                })
            
            # Low stability
            if node.stability < 0.5:
                anomalies.append({
                    "type": "UNSTABLE",
                    "node_id": nid,
                    "severity": "WARNING",
                    "description": f"Node '{nid}' has low stability {node.stability:.2f}"
                })
            
            # Distance from nearest attractor
            min_dist = float('inf')
            for attr in state.attractors.values():
                dist = node.position.sub(attr.center).magnitude()
                if dist < min_dist:
                    min_dist = dist
            
            # Check if node is within any attractor's radius
            if min_dist > 1.0:  # Not near any attractor
                anomalies.append({
                    "type": "ISOLATED",
                    "node_id": nid,
                    "severity": "INFO",
                    "description": f"Node '{nid}' is {min_dist:.2f} from nearest attractor"
                })
        
        return anomalies
    
    def query_agent(
        self,
        role: AgentRole,
        objective: str,
        state: KernelState = None,
        custom_context: str = None
    ) -> Tuple[str, List[ForceProposal]]:
        """
        Query an agent about the geometric state.
        
        Args:
            role: Agent role (determines system prompt)
            objective: What the agent should focus on
            state: KernelState to analyze (or use current)
            custom_context: Additional context to include
            
        Returns:
            Tuple of (analysis_text, list of ForceProposals)
        """
        if state is None:
            state = self.kernel.current_state
            if state is None:
                return "No state available", []
        
        # Project state to agent view
        view = self.project_state(state)
        
        # Build prompt
        system_prompt = self.ROLE_PROMPTS.get(role, self.ROLE_PROMPTS[AgentRole.ARCHITECT])
        
        user_prompt = f"""## Objective
{objective}

## Current Geometric State
{view.to_prompt_context()}

{custom_context or ""}

Analyze the geometry and provide your response as JSON only."""
        
        # Call DeepSeek
        try:
            response = requests.post(
                self.llm_url,
                json={
                    "model": self.llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.3
                },
                timeout=30.0
            )
            response.raise_for_status()
            
            content = response.json()["choices"][0]["message"]["content"]
            
            # Parse response
            return self._parse_agent_response(content, role.value)
            
        except Exception as e:
            logger.error(f"Agent query failed: {e}")
            return f"Error: {e}", []
    
    def _parse_agent_response(
        self, 
        content: str, 
        agent_role: str
    ) -> Tuple[str, List[ForceProposal]]:
        """Parse agent's JSON response into analysis and forces."""
        try:
            # Try to extract JSON from response
            # Sometimes the model wraps it in markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content.strip())
            
            # Extract analysis text
            analysis = data.get("analysis") or data.get("assessment") or data.get("topology_delta", "")
            
            # Extract forces
            forces = []
            for f in data.get("forces", []):
                forces.append(ForceProposal(
                    target_id=f["target_id"],
                    vector=f["vector"],
                    magnitude=f.get("magnitude", 0.1),
                    source=f.get("source", "evidence"),
                    reasoning=f.get("reasoning", ""),
                    agent_role=agent_role
                ))
            
            return analysis, forces
            
        except Exception as e:
            logger.warning(f"Failed to parse agent response: {e}")
            return content, []
    
    def apply_forces(
        self,
        forces: List[ForceProposal],
        validate: bool = True
    ) -> Tuple[KernelState, Dict[str, Any]]:
        """
        Apply force proposals to the kernel.
        
        Args:
            forces: List of ForceProposals from agents
            validate: Whether to run validation first
            
        Returns:
            Tuple of (new_state, metrics)
        """
        if not self.kernel.current_state:
            raise ValueError("Kernel has no current state")
        
        # Convert proposals to Forces
        kernel_forces = [fp.to_force() for fp in forces]
        
        # Simulate
        result = self.kernel.simulate(
            base_state_id=self.kernel.current_state.id,
            forces=kernel_forces,
            attractor_proposals=[],
            mode=Mode.WAKE
        )
        
        # Validate if requested
        if validate:
            outcome, reason = self.kernel.validate(result.simulation_id)
            if outcome == EvaluationOutcome.REJECTED:
                logger.warning(f"Forces rejected: {reason}")
                return self.kernel.current_state, {"rejected": True, "reason": reason}
        
        # Update state (simplified - in production, use apply())
        self.kernel.current_state = result.predicted_state
        self.kernel.state_history[result.predicted_state.id] = result.predicted_state
        
        return result.predicted_state, result.metrics
    
    def recursive_interrogation(
        self,
        role: AgentRole,
        target_node_id: str,
        max_depth: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Recursively interrogate the geometry around a target node.
        
        This is the "drill down" protocol:
        Level 0: System overview
        Level 1: Target node and neighbors
        Level 2: Detailed force analysis
        """
        results = []
        
        for depth in range(max_depth):
            if depth == 0:
                objective = f"Provide system overview. Target node: {target_node_id}"
            elif depth == 1:
                objective = f"Focus on node {target_node_id}. Analyze its relationships and anomalies."
            else:
                objective = f"Deep dive: Recommend specific forces to stabilize {target_node_id}."
            
            analysis, forces = self.query_agent(
                role=role,
                objective=objective
            )
            
            results.append({
                "depth": depth,
                "objective": objective,
                "analysis": analysis,
                "forces": [vars(f) for f in forces]
            })
            
            # Apply forces at each level
            if forces:
                _, metrics = self.apply_forces(forces)
                results[-1]["applied_metrics"] = metrics
        
        return results


# Convenience function for quick agent queries
async def geometry_query(
    objective: str,
    role: str = "architect",
    kernel: GeometryKernel = None
) -> Dict[str, Any]:
    """
    Quick geometry query for use in MCP tools.
    
    Example:
        result = await geometry_query(
            "Is the authentication module stable?",
            role="security"
        )
    """
    if kernel is None:
        kernel = GeometryKernel()
    
    interface = GeometryAgentInterface(kernel)
    role_enum = AgentRole(role)
    
    analysis, forces = interface.query_agent(role_enum, objective)
    
    return {
        "analysis": analysis,
        "forces": [vars(f) for f in forces],
        "role": role
    }


if __name__ == "__main__":
    # Demo
    import sys
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("Geometry Agent Interface Demo")
    print("=" * 60)
    
    # Create kernel with test state
    kernel = GeometryKernel()
    
    nodes = [
        ConceptNode(
            id="auth_service",
            position=Vector3D(0.0, 0.0, 0.0),
            velocity=Vector3D(0.1, 0.0, 0.0),  # Moving
            mass=1.0,
            energy=0.6,  # High energy = contradiction
            stability=0.7,
            confidence=0.85,
            last_updated=datetime.utcnow(),
        ),
        ConceptNode(
            id="user_database",
            position=Vector3D(1.0, 0.5, 0.0),
            velocity=Vector3D(0.0, 0.0, 0.0),
            mass=2.0,
            energy=0.1,
            stability=0.95,
            confidence=0.9,
            last_updated=datetime.utcnow(),
        ),
    ]
    
    attractors = [
        Attractor(
            id="secure_state",
            center=Vector3D(0.5, 0.5, 0.0),
            radius=0.5,
            depth=0.8,
            confidence=0.95,
            created_by=Mode.WAKE,
            created_at=datetime.utcnow(),
        ),
    ]
    
    state = kernel.initialize_state(nodes, attractors)
    
    # Create interface
    interface = GeometryAgentInterface(kernel)
    
    # Project state
    view = interface.project_state(state)
    print("\n### Geometric View for Agent:")
    print(view.to_prompt_context())
    
    # Query agent (will use live DeepSeek if available)
    print("\n### Querying Security Agent...")
    try:
        analysis, forces = interface.query_agent(
            role=AgentRole.SECURITY,
            objective="Analyze the authentication service for security anomalies"
        )
        print(f"Analysis: {analysis}")
        print(f"Proposed Forces: {[vars(f) for f in forces]}")
    except Exception as e:
        print(f"Agent query failed (server may not be running): {e}")
    
    print("=" * 60)
