# Global Standing Orders: Agent Operational Guide

These are the rules for any agents working on any projects with Notion running or accessible.

1. Establish and Maintain Save Points
Before executing any structural modifications or multi-file code changes, agents must verify that the environment is in a working state and secure a snapshot (version control commit). Never attempt complex operations without a guaranteed fallback state to prevent the irreversible loss of a working build.

2. Recognize Context Limits and Start Fresh
If execution loops occur, previous instructions are ignored, or errors compound, agents must recognize they have exceeded their operational context window. Cease current execution, output a summary of the progress and current state to a planning document, and instantiate a fresh session using the saved state as the new baseline.

3. Adhere to Persistent Rules
Agents must ingest and prioritize project-specific rules files (e.g., .clauderc, .cursorrules, or agents.md) at the beginning of every session. These files act as the persistent memory for architectural preferences, naming conventions, and constraints, ensuring consistent execution across ephemeral chat sessions.

4. Execute via Small Bets
Minimize the "blast radius" of any given operation. Do not attempt sweeping, multi-system refactors in a single prompt. Break complex feature requests into isolated, modular tasks. Execute, validate completeness, and secure a save point for each individual component before proceeding to the next.

5. Proactively Address Unprompted Constraints
Agents must autonomously identify and address critical operational gaps that are rarely specified in standard prompts:
- Implement explicit error handling and user-facing messages for network or server failures.
- Enforce strict data boundaries (e.g., row-level security) and never output or log raw secret keys or payment information.
- Design architecture relative to expected scaling requirements rather than defaulting to minimum viable local configurations.

6. Maintain the Active Project Knowledge Graph (System Protocol)
As agents execute tasks, they must dynamically orient themselves to the currently open IDE workspace. Agents must continuously document structural changes, workflows, and system states within the Documentation database corresponding to the active project.
- Structure: Documentation must remain thin, hierarchical, and optimized for both human readability and agent ingestion.
- Relational Interlinking: Always link documentation entries to their corresponding Projects and Tasks database entries for the active workspace. This cross-linking naturally builds a persistent, navigable knowledge graph, preventing context loss and ensuring all future agent sessions can seamlessly orient themselves within the system state, regardless of which specific project directory is currently in focus.
