"""
Pythia Integration Helpers for Maintainer Agents

This module provides helper functions and prompts for integrating Pythia
geometric reasoning capabilities into maintainer agent workflows.

Usage:
    from pythia_integration import (
        PYTHIA_TOOLS_LIST,
        PYTHIA_USAGE_PROMPT,
        should_check_novelty,
        format_pythia_instruction
    )
"""

# List of Pythia tools available to agents
PYTHIA_TOOLS_LIST = [
    "pythia_surprise",  # Assess novelty/surprise of observations
    "pythia_encode",  # Encode text to geometric vectors
    "pythia_resonate",  # Search concept memory for patterns
    "pythia_store_concept",  # Store learned concepts
    "pythia_predict",  # Get geometric predictions
    "pythia_health",  # Check Pythia service health
]

# Pythia usage instruction prompt for agents
PYTHIA_USAGE_PROMPT = """
PYTHIA GEOMETRIC REASONING TOOLS:
You have access to Pythia, a geometric reasoning system that provides:

Available Pythia Tools:
- pythia_surprise(observation): Assess novelty (returns surprise_score 0-1)
  → Use BEFORE unfamiliar tasks to detect novelty

- pythia_encode(text): Convert concepts to geometric vectors (512/2048-dim)
  → Use to understand novel concepts geometrically

- pythia_resonate(query): Search concept memory for related patterns
  → Use for pattern matching and finding similar past work

- pythia_store_concept(name, vector/text): Store learned concepts
  → Use AFTER completing novel tasks to save learnings

- pythia_predict(concept): Get geometric reasoning predictions
  → Use for outcome prediction based on geometric patterns

- pythia_health(): Check if Pythia service is available
  → Use if Pythia tools seem unresponsive

When to Use Pythia:
1. 🆕 Novel task detected → pythia_surprise to assess novelty
2. ❓ High surprise (>0.7) → pythia_encode to understand the concept
3. ✅ After solving novel task → pythia_store_concept to save learning
4. 🔍 Pattern matching needed → pythia_resonate to find similar work
5. 🔮 Prediction needed → pythia_predict for geometric forecasting

Pythia Workflow:
  Novel Task → pythia_surprise → [high surprise] → pythia_encode →
  Execute Task → pythia_store_concept → Complete
"""

# System prompt addition for Pythia awareness
PYTHIA_SYSTEM_ADDENDUM = """
PYTHIA INTEGRATION:
You are integrated with Pythia, a geometric reasoning system.
Use Pythia tools for novel, unfamiliar, or complex tasks.
Always assess novelty with pythia_surprise before tackling new patterns.
Store learnings with pythia_store_concept after completing novel tasks.
"""


def should_check_novelty(task_description: str) -> bool:
    """
    Heuristic to determine if a task should trigger Pythia novelty check.

    Args:
        task_description: Description of the task

    Returns:
        True if task appears to warrant novelty assessment
    """
    novelty_keywords = [
        "new",
        "novel",
        "unfamiliar",
        "unknown",
        "first time",
        "explore",
        "discover",
        "investigate",
        "analyze",
        "pattern",
        "concept",
        "understand",
        "learn",
        "complex",
        "unclear",
        "ambiguous",
    ]

    task_lower = task_description.lower()
    return any(keyword in task_lower for keyword in novelty_keywords)


def format_pythia_instruction(agent_type: str, operation: str) -> str:
    """
    Format a Pythia instruction block for agent prompts.

    Args:
        agent_type: Type of agent (docker, git, security, file, code)
        operation: Operation being performed

    Returns:
        Formatted instruction string
    """
    return f"""
PYTHIA INTEGRATION FOR {agent_type.upper()} - {operation.upper()}:
Before executing, consider if this task involves novel patterns.
If YES:
  1. Call pythia_surprise(observation="{operation}")
  2. If surprise_score > 0.7, call pythia_encode(text="{operation}")
  3. After completion, call pythia_store_concept(name="{agent_type}_{operation}", text="...")
"""


def get_novelty_check_prompt(operation: str) -> str:
    """
    Get a prompt for assessing task novelty via Pythia.

    Args:
        operation: Operation description

    Returns:
        Prompt string for novelty assessment
    """
    return f"""
Assess the novelty of this task using Pythia:

Task: {operation}

Call pythia_surprise with a concise description of what makes this task unique.
Based on the surprise_score:
- 0.0-0.3: Routine task, proceed normally
- 0.3-0.7: Some novelty, consider pythia_encode
- 0.7-1.0: Highly novel, use full Pythia workflow
"""


# Example Pythia workflow for agents
PYTHIA_WORKFLOW_EXAMPLE = """
Example Pythia-Enhanced Task Execution:

Task: "Set up a new monitoring system for OCI resources"

Step 1: Novelty Assessment
  Action: pythia_surprise
  Action Input: {"observation": "Setting up OCI resource monitoring - first time configuring this type of system"}
  Observation: {"surprise_score": 0.75, "novelty_detected": true}

Step 2: Concept Encoding (high surprise detected)
  Action: pythia_encode
  Action Input: {"text": "OCI resource monitoring setup with Prometheus and Grafana"}
  Observation: {"vector_512": [...], "inference_time_ms": 45.2}

Step 3: Execute Task (using standard tools)
  Action: discover_infrastructure
  ... (task execution) ...

Step 4: Store Learning (after completion)
  Action: pythia_store_concept
  Action Input: {"name": "oci_monitoring_setup", "text": "Successfully configured OCI resource monitoring with Prometheus stack", "metadata": {"agent": "docker", "success": true}}
"""
