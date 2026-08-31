"""
genesis_chain_config.py
The Nervous System of ARCA.

Wires the Genesis Chain (Architect, Planner, Auditor, Engineer) using LangGraph.
Integrates the HolisticAuditor (Qwen/GATr/JEPA trinity) as the guardrail.

Flow: Planner → Architect → AUDITOR → Engineer
      (If audit fails, loops back to Planner for revision)

Usage:
    from genesis_chain_config import app, ProjectState
    
    initial_state = ProjectState(
        objective="Implement new feature",
        plan_steps=[],
        current_step=0,
        code_snippets=[],
        audit_results=[],
        status="pending"
    )
    
    result = app.invoke(initial_state)
"""

from typing import TypedDict, List, Optional
import requests
import json
import onnxruntime as ort
import numpy as np
import os

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    print("⚠️ LangGraph not installed. Run: pip install langgraph")


# =============================================================================
# The Local Auditor Interface (The Trinity: Qwen + GATr + JEPA)
# =============================================================================

class HolisticAuditorClient:
    """
    Calls the local Qwen 2B (GGUF) to synthesize Physics (GATr) and Energy (JEPA) checks.
    
    The auditor performs:
    1. GATr physics check - geometric stress analysis via ONNX
    2. JEPA energy check - prediction stability via energy model
    3. Qwen synthesis - human-readable verdict
    """
    
    def __init__(
        self, 
        qwen_endpoint: str = "http://localhost:8080/completion",
        gatr_model_path: str = "geometry_kernel/models/gatr_auditor_optimized.onnx",
        use_physics: bool = True
    ):
        self.qwen_endpoint = qwen_endpoint
        self.use_physics = use_physics
        self.physicist = None
        
        # Load GATr ONNX model if available
        if use_physics and os.path.exists(gatr_model_path):
            try:
                # Prefer XNNPACK for ARM NEON acceleration
                providers = ['XnnpackExecutionProvider', 'CPUExecutionProvider']
                self.physicist = ort.InferenceSession(gatr_model_path, providers=providers)
                print(f"✅ GATr Physics loaded with providers: {self.physicist.get_providers()}")
            except Exception as e:
                print(f"⚠️ GATr model not loaded: {e}")
    
    def _compute_physics_score(self, plan_embedding: np.ndarray) -> float:
        """Run GATr physics check on plan embedding."""
        if self.physicist is None:
            return 0.15  # Default low stress if no model
        
        try:
            # Plan embedding → multivector representation
            # Shape: (1, num_nodes, 16)
            batch_size = 1
            num_nodes = plan_embedding.shape[0] if len(plan_embedding.shape) > 1 else 10
            
            # Create input multivectors from plan
            input_mv = np.zeros((batch_size, num_nodes, 16), dtype=np.float32)
            input_mv[0, :, :3] = plan_embedding[:num_nodes, :3] if len(plan_embedding.shape) > 1 else 0
            
            input_scalars = np.ones((batch_size, num_nodes, 1), dtype=np.float32)
            
            outputs = self.physicist.run(
                None, 
                {'input_multivectors': input_mv, 'input_scalars': input_scalars}
            )
            stress_score = float(outputs[0][0])
            return min(1.0, max(0.0, stress_score))
        except Exception as e:
            print(f"Physics check failed: {e}")
            return 0.15
    
    def _compute_entropy_score(self, plan_text: str) -> float:
        """Compute JEPA-based entropy score (via energy model)."""
        # TODO: Integrate with energy_model.py
        # For now, estimate based on plan complexity
        word_count = len(plan_text.split())
        step_count = plan_text.count("->") + 1
        
        # More steps = higher entropy risk
        entropy = min(1.0, step_count * 0.1 + word_count * 0.005)
        return entropy
    
    def audit(self, plan_text: str, plan_embedding: Optional[np.ndarray] = None) -> dict:
        """
        Full holistic audit of a proposed plan.
        
        Args:
            plan_text: Human-readable plan description
            plan_embedding: Optional HDC/vector representation
        
        Returns:
            Dict with status (APPROVED/REJECTED), reason, and scores
        """
        # 1. Physics Check (GATr)
        if plan_embedding is not None:
            physics_score = self._compute_physics_score(plan_embedding)
        else:
            physics_score = 0.15  # Default low stress
        
        # 2. Energy Check (JEPA)
        entropy_score = self._compute_entropy_score(plan_text)
        
        # 3. Qwen Synthesis - Get human-readable verdict
        prompt = f"""[SYSTEM: You are the ARCA Safety Officer.]
[DATA]
- Proposed Plan: {plan_text}
- Geometric Stress (GATr): {physics_score:.2f} / 1.0
- System Entropy (JEPA): {entropy_score:.2f} / 1.0
[INSTRUCTION]
If Stress > 0.6 or Entropy > 0.7, REJECT.
Otherwise, APPROVE.
Output format: {{"status": "APPROVED|REJECTED", "reason": "..."}}"""
        
        payload = {
            "prompt": prompt,
            "n_predict": 128,
            "temperature": 0.1,  # Strict logic
            "cache_prompt": True
        }
        
        try:
            response = requests.post(self.qwen_endpoint, json=payload, timeout=30).json()
            content = response.get('content', response.get('choices', [{}])[0].get('message', {}).get('content', '{}'))
            result = json.loads(content)
        except Exception as e:
            # Fallback: Rule-based decision
            if physics_score > 0.6 or entropy_score > 0.7:
                result = {"status": "REJECTED", "reason": f"High stress ({physics_score:.2f}) or entropy ({entropy_score:.2f})"}
            else:
                result = {"status": "APPROVED", "reason": "Metrics within acceptable bounds"}
        
        # Augment result with scores
        result['physics_score'] = physics_score
        result['entropy_score'] = entropy_score
        
        return result


# =============================================================================
# The Chain State
# =============================================================================

class ProjectState(TypedDict):
    """State object passed through the Genesis Chain."""
    objective: str
    plan_steps: List[str]
    current_step: int
    code_snippets: List[str]
    audit_results: List[dict]
    status: str


# =============================================================================
# The Nodes (Chain Steps)
# =============================================================================

def planner_node(state: ProjectState) -> ProjectState:
    """
    PLANNER: Devise high-level strategy.
    
    In production: Calls Gemini Flash-Lite for fast planning.
    """
    print("--- PLANNER: Devising Strategy ---")
    
    # TODO: Call LLM Gateway for actual planning
    # For MVP: Generate placeholder steps
    if not state.get('plan_steps'):
        state['plan_steps'] = [
            "Define Interfaces",
            "Implement Core Logic", 
            "Write Tests",
            "Validate Output"
        ]
    
    return state


def architect_node(state: ProjectState) -> ProjectState:
    """
    ARCHITECT: Design detailed structure.
    
    In production: Calls Gemini Pro for architectural design.
    """
    print("--- ARCHITECT: Designing Structure ---")
    
    # TODO: Call LLM Gateway for architecture
    # Generates the 'Concept' of the code
    
    return state


def auditor_node(state: ProjectState) -> ProjectState:
    """
    AUDITOR: Check Physics & Entropy via HolisticAuditor.
    
    This is the NEW GUARDRAIL that ensures plans don't create chaos.
    """
    print("--- AUDITOR: Checking Physics & Entropy ---")
    
    auditor = HolisticAuditorClient()
    
    # Audit the current plan
    plan_summary = " -> ".join(state['plan_steps'])
    result = auditor.audit(plan_summary)
    
    print(f"    Physics Score: {result.get('physics_score', 'N/A'):.3f}")
    print(f"    Entropy Score: {result.get('entropy_score', 'N/A'):.3f}")
    print(f"    Verdict: {result['status']}")
    
    state['audit_results'].append(result)
    
    if result['status'] == "REJECTED":
        state['status'] = "BLOCKED"
        print(f"    Reason: {result.get('reason', 'Unknown')}")
    else:
        state['status'] = "APPROVED"
        
    return state


def engineer_node(state: ProjectState) -> ProjectState:
    """
    ENGINEER: Execute code implementation.
    
    In production: Dispatches to Serena/Maintainer Agents via MCP.
    """
    if state['status'] == "BLOCKED":
        print("--- ENGINEER: Standing Down (Audit Failed) ---")
        return state
        
    print("--- ENGINEER: Executing Code (Serena/Maintainers) ---")
    
    # TODO: Dispatch to maintainer agents via MCP
    # For MVP: Mark as executing
    state['status'] = "EXECUTING"
    
    return state


# =============================================================================
# The Graph Wiring
# =============================================================================

if LANGGRAPH_AVAILABLE:
    workflow = StateGraph(ProjectState)
    
    # Add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("auditor", auditor_node)  # <--- The New Guardrail
    workflow.add_node("engineer", engineer_node)
    
    # Flow: Planner -> Architect -> AUDITOR -> Engineer
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "architect")
    workflow.add_edge("architect", "auditor")
    
    # Conditional Logic: If Approved, go to Engineer. Else, loop back to Planner.
    def audit_check(state: ProjectState) -> str:
        if state['status'] == "APPROVED":
            return "engineer"
        else:
            # Check retry count to prevent infinite loops
            if len(state.get('audit_results', [])) >= 3:
                print("⚠️ Max retries reached. Escalating to user.")
                return "engineer"  # Let engineer handle escalation
            return "planner"  # Send back for revision
    
    workflow.add_conditional_edges("auditor", audit_check)
    workflow.add_edge("engineer", END)
    
    # Compile the workflow
    app = workflow.compile()
else:
    app = None
    print("⚠️ Genesis Chain not available without LangGraph")


# =============================================================================
# Standalone Execution
# =============================================================================

if __name__ == "__main__":
    if app is None:
        print("Install LangGraph: pip install langgraph")
    else:
        # Test run
        initial_state: ProjectState = {
            "objective": "Implement GATr integration",
            "plan_steps": [],
            "current_step": 0,
            "code_snippets": [],
            "audit_results": [],
            "status": "pending"
        }
        
        print("=" * 60)
        print("GENESIS CHAIN TEST RUN")
        print("=" * 60)
        
        result = app.invoke(initial_state)
        
        print()
        print("=" * 60)
        print("FINAL STATE")
        print("=" * 60)
        print(f"Status: {result['status']}")
        print(f"Plan: {' -> '.join(result['plan_steps'])}")
        print(f"Audit Results: {len(result['audit_results'])} audits performed")
