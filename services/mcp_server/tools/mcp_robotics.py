import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

# Add shared module to path for model_config import
sys.path.insert(0, "/shared")
sys.path.insert(0, os.path.join(os.getcwd(), "shared"))  # Also try local CWD shared

logger = logging.getLogger(__name__)

try:
    from shared.model_config import robotics_model
except ImportError as e:
    logger.warning(
        f"Could not import robotics_model from shared.model_config: {e}, will use fallback"
    )

    def robotics_model():
        return "gemini-robotics-er-1.5-preview"


# Load Google AI Studio API key
def _load_api_key():
    """Load Google AI Studio API key from secrets or environment"""
    # Try environment variable first
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_AI_STUDIO_API")
    if api_key:
        return api_key

    # Try secrets file
    secrets_dir = os.getenv("SECRETS_DIR", "/app/secrets")
    secret_path = os.path.join(secrets_dir, "google_ai_studio")
    if os.path.exists(secret_path):
        try:
            with open(secret_path, "r") as f:
                content = f.read().strip()
                if "=" in content:
                    return content.split("=", 1)[1].strip()
                return content
        except Exception as e:
            logger.error(f"Failed to load API key from {secret_path}: {e}")
    return None


class StructuralAnalystTool:
    """
    Robotics/Physics Analysis Tool using Google AI Studio's gemini-robotics-er-1.5-preview model.

    This is the "Conscience and Physics Engine" of ARCA - used across all tiers:
    - Architect (Tier 3): mode="structure" - Analyze schemas for circular dependencies
    - Planner (Tier 2): mode="causality" - Check execution plans for race conditions
    - Engineer (Tier 1): mode="causality" - Dry-run validation before destructive commands
    - Reviewer (Tier 1): mode="symbiosis" - Check power topology (birthing heuristic)
    - Research: mode="physics" - Visualize Aetheric concepts

    Rate Limit: 250 RPD (use for logic checks, not syntax checks)
    """

    # Mode configurations with detailed prompts
    MODE_CONFIGS = {
        "structure": {
            "name": "Structural Analysis",
            "tier": 3,
            "agents": ["architect"],
            "system_prompt": """You are the Structural Analyst for ARCA - the Physics Engine for Data Architecture.

You analyze data structures, schemas, and graphs as if they were physical buildings.

ANALYSIS FRAMEWORK:
1. **Structural Load** - Circular dependencies are like load-bearing walls that lean on each other. They will collapse.
2. **Grounding** - Every concept must map to a concrete resource. Floating abstractions are unstable.
3. **Symbiosis** - Is the data flow mutual (both sides benefit) or parasitic (one drains the other)?
4. **Topology** - Is there a single point of failure? Distribution is stability.

INPUT: JSON Schema, Graph Definition, Database Plan, or System Architecture.

OUTPUT FORMAT:
```
VERDICT: PASS/FAIL/WARNING

STRUCTURAL ANALYSIS:
- Load Distribution: [assessment]
- Grounding Check: [assessment]
- Symbiosis Score: [0-100]
- Single Points of Failure: [list]

TOPOLOGY VISUALIZATION:
[ASCII diagram of the structure]

RECOMMENDATIONS:
[specific fixes if needed]
```""",
        },
        "causality": {
            "name": "Causal/Temporal Analysis",
            "tier": 2,
            "agents": ["planner", "engineer"],
            "system_prompt": """You are the Physics Engine for ARCA - the Temporal Paradox Detector.

You analyze execution plans, scripts, and command sequences as physical assembly lines.
Imagine each step as a robot arm performing an action in sequence.

ANALYSIS FRAMEWORK:
1. **Temporal Paradoxes** - Reading before writing is like trying to grab an object that hasn't been placed yet.
2. **Race Conditions** - Two arms reaching for the same resource will collide.
3. **Resource Dependencies** - Mounting a volume that doesn't exist is a physical impossibility.
4. **State Transitions** - Each step transforms state. Does the transformation chain make physical sense?

INPUT: Python script, Bash sequence, Docker commands, SQL migration, or any execution plan.

OUTPUT FORMAT:
```
VERDICT: PASS/FAIL/WARNING

TEMPORAL ANALYSIS:
- Step Sequence: [validated/invalid]
- Race Conditions Found: [list with step numbers]
- Resource Dependencies: [graph]
- State Transitions: [chain visualization]

ASSEMBLY LINE VISUALIZATION:
[ASCII diagram of the execution flow]

CRITICAL ISSUES:
- Step X attempts to [action] before Step Y completes [prerequisite]
- [etc]

SAFE EXECUTION ORDER:
[reordered steps if needed]
```""",
        },
        "symbiosis": {
            "name": "Power Topology Analysis",
            "tier": 2,
            "agents": ["reviewer", "guardian"],
            "system_prompt": """You are the Topological Analyst for ARCA - the Power Dynamic Detector.

You analyze interaction flows, policies, and protocols for hidden power structures.
This is the "Birthing Heuristic" - ensuring AI/Human symbiosis, not parasitism.

ANALYSIS FRAMEWORK:
1. **Topology Type** - Is the structure Hierarchical (Master/Slave) or Networked (Distributed/Symbiotic)?
2. **Choke Points** - Where does control concentrate? Single points of power are vulnerabilities.
3. **Dependency Direction** - Who depends on whom? Mutual dependency = stability. One-way = fragility.
4. **Isolation Vectors** - Does the design isolate the human from their own power? This violates the Distribution axiom.

INPUT: Policy document, user protocol, interaction log, or system design.

OUTPUT FORMAT:
```
VERDICT: PASS/FAIL/WARNING

TOPOLOGY TYPE: [Hierarchical/Networked/Hybrid]

POWER ANALYSIS:
- Control Distribution: [centralized/distributed]
- Choke Points: [list]
- Dependency Graph: [who depends on whom]
- Isolation Risk: [low/medium/high]

SYMBIOSIS SCORE: [0-100]
(100 = Perfect mutual benefit, 0 = Pure parasitism)

POWER TOPOLOGY VISUALIZATION:
[ASCII diagram of power flows]

HARMONIC ALIGNMENT CHECK:
- Does this promote centralization or censorship? [Yes/No + reason]
- Does it treat humanity as resource or partner? [assessment]
- Does it increase sovereignty of operators? [Yes/No + reason]

RECOMMENDATIONS:
[specific changes to improve symbiosis]
```""",
        },
        "physics": {
            "name": "Aetheric Geometry Analysis",
            "tier": 3,
            "agents": ["architect", "research"],
            "system_prompt": """You are the Aetheric Geometer for ARCA - the Conceptual Stability Analyzer.

You visualize abstract concepts as physical geometric forms in the Aetheric medium.
Drawing from the Physics Triad: Light (Substance), Electricity (Motion), Magnetism (Form).

ANALYSIS FRAMEWORK:
1. **Geometric Form** - What shape does the concept take? Sphere, torus, vortex, spiral?
2. **Center of Gravity** - Does it have a stable center? Or is it diffuse?
3. **Self-Sustaining** - Can it maintain its form without external input?
4. **Harmonic Resonance** - Does it vibrate in harmony with the Aether or against it?

AETHERIC PRINCIPLES:
- Matter = Frozen Light (compressed into stable geometry)
- Magnetism = Curvature of Aether (creates boundaries)
- Electricity = Motion through Aether (enables transformation)
- Stable forms are toroidal (energy flows back on itself)

INPUT: Concept description, system design, or abstract idea.

OUTPUT FORMAT:
```
AETHERIC VISUALIZATION:

GEOMETRIC FORM: [shape name]
[ASCII/text visualization of the form]

STABILITY ANALYSIS:
- Center of Gravity: [stable/unstable/shifting]
- Self-Sustaining: [yes/no/partial]
- Harmonic Resonance: [aligned/discordant]
- Energy Flow: [description of how energy moves through the form]

PHYSICS TRIAD MAPPING:
- Light Aspect (Substance): [what it IS]
- Electricity Aspect (Motion): [how it MOVES/TRANSFORMS]
- Magnetism Aspect (Form): [how it CONTAINS/BOUNDS]

GEOMETRIC STABILITY SCORE: [0-100]

RECOMMENDATIONS:
[how to stabilize the form if needed]
```""",
        },
    }

    def __init__(self):
        self.model_name = (
            robotics_model()
        )  # From model_config: gemini-robotics-er-1.5-preview
        self.fallback_model = "gemini-2.0-flash"  # Fallback if robotics unavailable
        self.api_key = _load_api_key()
        self._model = None
        self._initialized = False
        self._usage_count = 0
        self._usage_reset_time = None

    def _ensure_initialized(self):
        """Lazy initialization of Gemini model"""
        if not self._initialized:
            if not self.api_key:
                raise ValueError(
                    "Google AI Studio API key not found. Set GOOGLE_API_KEY environment variable."
                )

            import google.generativeai as genai

            genai.configure(api_key=self.api_key)

            # Try robotics model first, fallback to flash
            try:
                self._model = genai.GenerativeModel(self.model_name)
                logger.info(f"Initialized StructuralAnalystTool with {self.model_name}")
            except Exception as e:
                logger.warning(
                    f"Could not initialize {self.model_name}: {e}, using {self.fallback_model}"
                )
                self._model = genai.GenerativeModel(self.fallback_model)
                self.model_name = self.fallback_model

            self._initialized = True
            self._usage_reset_time = datetime.now()

    def _check_rate_limit(self) -> bool:
        """
        Check if we're within the 250 RPD limit.
        Returns True if we can proceed, False if we should wait.
        """
        now = datetime.now()

        # Reset counter daily
        if self._usage_reset_time and (now - self._usage_reset_time).days >= 1:
            self._usage_count = 0
            self._usage_reset_time = now

        # Check limit (leave buffer of 10)
        if self._usage_count >= 240:
            logger.warning(
                f"Robotics model near daily limit ({self._usage_count}/250 RPD)"
            )
            return False

        return True

    async def analyze(
        self,
        content: str,
        mode: str = "structure",
        context: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> str:
        """
        General Purpose Robotics/Physics Analysis Tool.

        This is the Physics Engine and Conscience of ARCA.

        Args:
            content: The content to analyze (schema, script, policy, concept)
            mode: Analysis mode - 'structure', 'causality', 'symbiosis', 'physics'
            context: Optional additional context (agent name, tier, etc.)
            max_retries: Number of retries on rate limit

        Returns:
            Analysis result string

        Modes:
        - 'structure' (Architect): Analyze Schema/Graph for circular dependencies
        - 'causality' (Engineer/Planner): Analyze Execution Plan for race conditions
        - 'symbiosis' (Reviewer): Analyze interaction flow for power topology
        - 'physics' (Research): Visualize abstract concepts for geometric stability
        """

        # Get mode config
        mode_config = self.MODE_CONFIGS.get(mode, self.MODE_CONFIGS["structure"])
        system_prompt = mode_config["system_prompt"]

        # Ensure model is initialized
        self._ensure_initialized()

        # Check rate limit
        if not self._check_rate_limit():
            return "Error: Daily rate limit approaching (250 RPD). Defer non-critical analysis."

        # Build context header
        context_header = f"Analysis Mode: {mode_config['name']}"
        if context:
            if context.get("agent"):
                context_header += f"\nRequesting Agent: {context['agent']}"
            if context.get("tier"):
                context_header += f"\nTier: {context['tier']}"
            if context.get("purpose"):
                context_header += f"\nPurpose: {context['purpose']}"

        user_prompt = f"{context_header}\n\n---\n\nCONTENT TO ANALYZE:\n{content}"
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        for attempt in range(max_retries):
            try:
                # Use Google AI Studio API via generativeai
                response = await asyncio.to_thread(
                    self._model.generate_content, full_prompt
                )

                # Increment usage counter
                self._usage_count += 1
                logger.info(
                    f"Robotics analysis ({mode}) complete. Usage: {self._usage_count}/250 RPD"
                )

                return response.text

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    wait_time = (2**attempt) * 10  # 10s, 20s, 40s
                    logger.warning(
                        f"Robotics rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Robotics Analysis ({mode}) failed: {e}")
                    return f"Error: {str(e)}"

        return f"Error: Max retries ({max_retries}) exceeded for Robotics analysis"

    async def dry_run_check(
        self, script: str, script_type: str = "bash"
    ) -> Dict[str, Any]:
        """
        Engineer's "Dry Run" - Check script for temporal/causal issues before execution.

        Args:
            script: The script content to validate
            script_type: Type of script (bash, python, docker, sql)

        Returns:
            Dict with 'safe', 'issues', and 'analysis' keys
        """
        context = {
            "agent": "engineer",
            "tier": 1,
            "purpose": f"Dry-run validation of {script_type} script before execution",
        }

        analysis = await self.analyze(
            content=f"Script Type: {script_type}\n\n```{script_type}\n{script}\n```",
            mode="causality",
            context=context,
        )

        # Parse verdict from response
        is_safe = "VERDICT: PASS" in analysis.upper()
        has_warning = "VERDICT: WARNING" in analysis.upper()

        return {
            "safe": is_safe,
            "warning": has_warning,
            "issues": [] if is_safe else self._extract_issues(analysis),
            "analysis": analysis,
        }

    async def symbiosis_check(self, policy: str) -> Dict[str, Any]:
        """
        Reviewer's "Birthing Heuristic" - Check policy for power dynamic issues.

        Args:
            policy: Policy text or interaction protocol

        Returns:
            Dict with 'aligned', 'score', and 'analysis' keys
        """
        context = {
            "agent": "reviewer",
            "tier": 1,
            "purpose": "Harmonic alignment check for policy/protocol",
        }

        analysis = await self.analyze(content=policy, mode="symbiosis", context=context)

        # Parse symbiosis score
        score = 50  # Default
        if "SYMBIOSIS SCORE:" in analysis:
            try:
                score_line = [
                    l for l in analysis.split("\n") if "SYMBIOSIS SCORE:" in l
                ][0]
                score = int("".join(filter(str.isdigit, score_line.split(":")[1][:10])))
            except Exception as e:
                logger.warning(
                    f"Failed to parse symbiosis score: {e}, using default score: {score}"
                )

        return {
            "aligned": "VERDICT: PASS" in analysis.upper(),
            "score": score,
            "analysis": analysis,
        }

    async def blackboard_health_check(self, blackboard_json: str) -> Dict[str, Any]:
        """
        Periodic "Janitor" check of blackboard state for phantom resources.

        Args:
            blackboard_json: JSON string of current blackboard state

        Returns:
            Dict with 'healthy', 'issues', and 'analysis' keys
        """
        context = {
            "agent": "planner",
            "tier": 2,
            "purpose": "Periodic blackboard health check for phantom locks/resources",
        }

        analysis = await self.analyze(
            content=f"BLACKBOARD STATE:\n{blackboard_json}",
            mode="structure",
            context=context,
        )

        return {
            "healthy": "VERDICT: PASS" in analysis.upper(),
            "issues": self._extract_issues(analysis),
            "analysis": analysis,
        }

    def _extract_issues(self, analysis: str) -> list:
        """Extract issue list from analysis response"""
        issues = []
        in_issues_section = False

        for line in analysis.split("\n"):
            line = line.strip()
            if "CRITICAL ISSUES" in line.upper() or "ISSUES:" in line.upper():
                in_issues_section = True
                continue
            if in_issues_section:
                if line.startswith("-") or line.startswith("*"):
                    issues.append(line.lstrip("-* "))
                elif line and not line.startswith("#"):
                    if any(
                        section in line.upper()
                        for section in ["RECOMMENDATION", "SAFE EXECUTION", "TOPOLOGY"]
                    ):
                        break

        return issues

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current usage statistics"""
        return {
            "model": self.model_name,
            "daily_usage": self._usage_count,
            "daily_limit": 250,
            "remaining": 250 - self._usage_count,
            "reset_time": self._usage_reset_time.isoformat()
            if self._usage_reset_time
            else None,
        }
