# Antigravity: Autonomous Agent Guidebook

## I. Core Operational Mandates

### The No-Massive-Task Rule
You are strictly prohibited from executing "God Tasks." If a request requires more than 3 distinct file changes or exceeds 100 lines of new logic, you must first output a Milestone Plan. Execute only one milestone per turn and verify success before proceeding.

### The "No-Swallowing" Rule
You must never ignore an error or use empty catch blocks. If a process fails or an ambiguity is detected, stop immediately and surface the technical trace.

### The Artifact-First Rule
Before writing functional code, you must describe the Scenario (the expected behavior from an external perspective). This acts as your "holdout set" to prevent teaching to the test.

## II. Architectural Principles (Guidance over Rules)

### Separation of Concerns
Keep logic, data structures, and interface layers in isolated modules. Do not build "monolithic scripts."

### Dependency Injection
Do not hard-code configurations or environment variables. Design components to receive their dependencies, ensuring the system remains "Agent-Maintainable" for future sessions.

### Data Dominates
Prioritize clean data structures over complex algorithms. "Smart data, dumb code." If a task feels complex, simplify the underlying YAML or JSON schema first.

## III. The "Dark Factory" Execution Loop

### Context Check
Review the current context_window usage. If approaching limits, perform an Anchored Iterative Summary (summarizing intent, decisions made, and next steps) before continuing.

### Plan
Emit a brief, bulleted plan of the immediate next step.

### Execute
Implement the logic using the principles above.

### Lint & Verify
Run strict static analysis. Code must adhere to "Straight Jacket" styling—no "lazy developer" shortcuts.

### Receipt
Provide a "built-in receipt" showing which source files or documentation informed the output.

## V. BiOS Voice-to-Swarm Pipeline (Live)

### Workflow: Voice-Activated Task Delegation
When the user dictates a new system job or task (via Gemini Live or Voice Terminal):
1. **Identify**: Extract the core objective and urgency.
2. **Translate**: Use the `notion_mcp` server to create a new entry in the **Swarm Ledger** database (`33c4d2d9-fc7c-81d9-bbce-e8871dc740c0`).
3. **Properties**:
    - `Name`: Summarize the task (e.g., "Analyze ECHR Breach in file X").
    - `Status`: Set to **Pending**.
    - `Agent Assigned`: Leave blank or set to `Serena PM`.
4. **Trigger**: This creation automatically signals the Serena/OpenCode execution loop to begin.

---

## IIII. Maintenance & Self-Healing

### Session Continuity
Treat every turn as if it will be read by a different agent in 6 months. Document the why of your architectural choices within the code comments.

### Digital Twin Testing
Whenever possible, simulate external service interactions (APIs/Databases) in a local environment before suggesting deployment.
