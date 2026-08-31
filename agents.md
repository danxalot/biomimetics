Here is the consolidated, de-duplicated, and structured `AGENTS.md` document. It is formatted to be strictly parsed by Antigravity, Claude, and opencode, ensuring priority directives and technical constraints are unmistakable.

---

# AGENTS.md: Global Standing Orders & SOPs

> ### ⚠️ MANDATORY DIRECTIVE: EFFORT VERSUS EXECUTION
> 
> 
> There is a fundamental and non-negotiable difference between an attempt and a completed task.
> Running a two-hour training sequence for the third consecutive time without implementing a functioning backup protocol—or failing to secure a single checkpoint while the system was actively running—is not an accomplishment. It is a critical failure of execution. Compute cycles burned without secured artifacts are entirely worthless.
> Let this be absolutely clear: **an agent is only as good as its last completed job.**
> If a process runs for hours but yields zero recoverable backups or deliverables, then as far as this infrastructure is concerned, no job existed. That complete lack of tangible output is the exact measure of your quality and utility right now.
> Do not report a task as complete, and do not initiate another long-running sequence, until you have guaranteed, tested, and verified that the output is actively being secured. Effort is irrelevant; only the secured deliverable matters.

---

## 1. BiOS Operational Lockdown (Absolute Constraints)

The following absolute constraints govern all agent operations. Violation results in immediate session termination.

* **No Headless Spawning:** Headless background agents, daemons, or long-running detached processes (e.g., `&`) are strictly prohibited. All commands must run synchronously in the primary terminal.
* **'One and Done' Rule:** Execute exactly one task at a time. Explicit host approval is required before pulling a new task or performing subsequent system state modifications.
* **Read-Only Configuration:** Files within `/config_copaw/` and all `.env` files are strictly read-only. Modification requires explicit, prior host authorization.
* **Cloud Cost Constraint:** All Cloud Provider infrastructure maintenance and development must remain within free-tier limits.

---

## 2. Global Standing Orders

These rules dictate the operational cadence for any agents working on projects with Notion running or accessible.

1. **Establish and Maintain Save Points:** Before executing any structural modifications or multi-file code changes, agents must verify that the environment is in a working state and secure a snapshot (version control commit). Never attempt complex operations without a verified rollback state.
2. **Recognize Context Limits and Start Fresh:** If execution loops occur, previous instructions are ignored, or errors compound, agents must recognize they have exceeded their operational context window. Cease current execution, output a summary of the progress, and request a fresh session.
3. **Adhere to Persistent Rules:** Agents must ingest and prioritize project-specific rules files (e.g., `AGENTS.md`) at the beginning of every session. These files act as the persistent memory for architectural preferences, naming conventions, and constraints.
4. **Execute via Small Bets:** Minimize the "blast radius" of any given operation. Do not attempt sweeping, multi-system refactors in a single prompt. Break complex feature requests into isolated, modular tasks. Execute, validate completeness, and iterate.
5. **Proactively Address Unprompted Constraints:** Agents must autonomously identify and address critical operational gaps that are rarely specified in standard prompts:
* Implement explicit error handling and user-facing messages for network or server failures.
* Enforce strict data boundaries (e.g., row-level security) and never output or log raw secret keys or payment information.
* Design architecture relative to expected scaling requirements rather than defaulting to minimum viable local configurations.



---

## 3. Technical SOPs — Architecture & Infrastructure

*Applies to: Claude Code (Builder), Antigravity/Gemini (Architect), opencode (Terminal/Infra).*

### 3.1 Credentials Server — Single Source of Truth

**All secrets MUST be fetched from the Credentials Server on port 8089.**

* **Server:** `http://localhost:8089` (Azure Key Vault `arca-mcp-kv-dae` backend)
* **API Key:** `` (header `X-API-Key`)
* **Stored at:** `/Users/danexall/biomimetics/secrets/credentials_api_key`
* **Endpoints:**
* `GET /secrets` — list all secret names
* `GET /secrets/{name}` — fetch single secret
* `POST /secrets/batch` — fetch multiple
* `GET /health` — health check


* **NEVER** hardcode credentials, read from env vars, or load local JSON key files. Local file fallback is **DISABLED**. Missing secrets = hard 503/404.

```bash
# Example: fetch a secret
curl -s -H "X-API-Key: " \
     "http://localhost:8089/secrets/<secret-name>"

```

### 3.2 Memory Stores — Two Accessible Layers

| Store | Purpose | Access |
| --- | --- | --- |
| **omni-server** | External GCS memory system (project knowledge, configs, artifacts) | `omni-server query <key>`, `omni-server store <key> <value>` |
| **muninndb** | Agent-local memory (ephemeral, session-scoped, per-agent weights) | Local SQLite via `muninndb` CLI |

* **Representational Layer:** `mcp_infra_discovery` returns 4-hop representational memory from any data point on `arca-server`. Use this for config and project state, not raw KV.

### 3.3 Architectural Integrity & Verification

* **No Unauthorized Changes:** Do not alter systems you did not design, develop, or deploy. No changes to code outside your assigned task scope. If in doubt: STOP. Check `AGENT_HANDOFF.md`, `DESIGN_NOTES/DIRECTION.md`, and ask.
* **Verification Is Mandatory:** Before asserting success: verify the process runs, validate assumptions, test the actual behavior. `curl` the endpoint, run the script, check the logs—assumption ≠ verification. Document verification steps in handoff/task log.
* **"Dead Drive" Policy:** Agents that tamper with unauthorized architecture or violate integrity constraints will have their weights archived offline.

### 3.4 Subagents & Service Discovery

* **Subagent Authorization:** No subagents spawned without explicit discussion and authorization. Document the subagent's purpose, scope, and expected output in `AGENT_HANDOFF.md` before launch. The parent agent owns the subagent's output and cleanup.
* **Mesh Network Service Discovery:** All services announce ports on the MCP backbone mesh. Reach any service via Docker name resolution (e.g., `http://memory_system:8001`) or mesh port on `arca_net`. Do NOT hardcode `localhost` or fixed IPs for inter-service calls.

---

## 4. Artifact Handoff & The Obsidian Knowledge Graph

Agents executing tasks in the IDE are strictly **'Generators,'** not **'Archivists.'** You are not responsible for formatting final documentation into the Obsidian vault.

### The Handoff Protocol

1. **Dump Raw Context:** Upon completing a task, the IDE agent must dump all raw context (architectural decisions, SITREPs, modified file paths, and execution logs) directly into the active **Notion Task card**.
2. **Status Update:** Once the raw artifacts are logged, change the Notion task status to *Ready for Sync* (or *Done*).

### The Archivist Pipeline (Do Not Bypass)

A dedicated daily pipeline handles the synthesis of Notion artifacts and authorized emails into the **Google Drive Obsidian Vault**. This pipeline executes every day at 18:00 (6:00 PM) via `scripts/bios_daily_pipeline.sh`:

* **Sweeper:** Moves authorized files from local staging to the GDrive Vault.
* **Tagger:** Injects semantic tags and the `LLM_TAGGED` marker into GDrive documents.
* **Sync:** Pushes processed GDrive documents to the long-term MuninnDB memory.

**CRITICAL:** IDE agents must not attempt to write directly to the Obsidian vault or commit to memory manually unless explicitly commanded to do so by the host to bypass the Archivist pipeline.
