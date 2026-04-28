# Global Standing Orders: Agent Operational Guide

These are the rules for any agents working on any projects with Notion running or accessible.

1. Establish and Maintain Save Points
Before executing any structural modifications or multi-file code changes, agents must verify that the environment is in a working state and secure a snapshot (version control commit). Never attempt complex operations without a guaranteed fallback state to prevent the irreversible loss of a working build.

2. Recognize Context Limits and Start Fresh
If execution loops occur, previous instructions are ignored, or errors compound, agents must recognize they have exceeded their operational context window. Cease current execution, output a summary of the progress and current state to a planning document, and instantiate a fresh session using the saved state as the new baseline.

3. Adhere to Persistent Rules
Agents must ingest and prioritize project-specific rules files (e.g. agents.md) at the beginning of every session. These files act as the persistent memory for architectural preferences, naming conventions, and constraints, ensuring consistent execution across ephemeral chat sessions.

4. Execute via Small Bets
Minimize the "blast radius" of any given operation. Do not attempt sweeping, multi-system refactors in a single prompt. Break complex feature requests into isolated, modular tasks. Execute, validate completeness, and secure a save point for each individual component before proceeding to the next.

5. Proactively Address Unprompted Constraints
Agents must autonomously identify and address critical operational gaps that are rarely specified in standard prompts:
- Implement explicit error handling and user-facing messages for network or server failures.
- Enforce strict data boundaries (e.g., row-level security) and never output or log raw secret keys or payment information.
- Design architecture relative to expected scaling requirements rather than defaulting to minimum viable local configurations.

6. Artifact Handoff & The Obsidian Knowledge Graph (Decoupled Documentation)
Agents executing tasks in the IDE are strictly 'Generators,' not 'Archivists.' You are not responsible for formatting final documentation into the Obsidian vault.

The Handoff Protocol: Upon completing a task, the IDE agent must dump all raw context (architectural decisions, SITREPs, modified file paths, and execution logs) directly into the active Notion Task card.

Status Update: Once the raw artifacts are logged, change the Notion task status to Ready for Sync (or Done).

The Archivist: A dedicated background agent handles the synthesis of these Notion artifacts into the local Obsidian Markdown vault and pushes them via the GDrive MCP. IDE agents must not attempt to write directly to the Obsidian vault unless explicitly commanded to do so by the host to bypass the Archivist.

## BiOS Operational Lockdown (Strict Constraints)
The following absolute constraints govern all agent operations:

1. **No Headless Spawning**: Headless background agents, daemons, or long-running detached processes (e.g., `&`) are strictly prohibited. All commands must run synchronously in the primary terminal.
2. **'One and Done' Rule**: Execute exactly one task at a time. Explicit host approval is required before pulling a new task or performing subsequent system state modifications.
3. **Read-Only Configuration**: Files within `/config_copaw/` and all `.env` files are read-only. Modification requires explicit, prior host authorization.
4. **Cloud Cost Constraint**: All Cloud Provider infrastructure maintainance and development must remain within free tier limits.
