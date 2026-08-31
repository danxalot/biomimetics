# **BiOS Session Artifact Protocol & Autonomous Knowledge Integration**

## **1. Executive Mandate (The Single Source of Truth)**
The Biomimetic Operating System (BiOS) mandates a **Zero-Manual-Documentation** policy. All project documentation, architectural updates, and engineering rationales must be autonomously harvested from IDE telemetry, agent logs, and multi-model reasoning cycles. This document serves as the absolute standard for retrieving, stripping, and synthesizing these artifacts into a coherent "Picture of Work."

---

## **2. The Artifact Ingestion Layer**

| Product | Artifact Type | Retrieval Path/Method | Primary Tooling |
| :--- | :--- | :--- | :--- |
| **Claude Code** | JSONL Transcripts | `~/.claude/sessions/*.json` | `artifact_harvester.py`, `claude-code-log` |
| **Claude Code** | OTLP Telemetry | gRPC `localhost:4317` | OpenTelemetry Collector |
| **Antigravity** | Manager Surface | `~/.bios/staging/ide_artifacts/` | `antigravity_manager.py` |
| **Antigravity** | State Recovery | Local FS Monitoring | `state-recovery-protocol` |
| **OpenCode** | Reasoning Enrichment | REST API (`opencode.ai/zen/v1`) | `serena-memory-sync.py` |
| **Zed** | Conversation Logs | `~/Library/Application Support/Zed/conversations/*.json` | `artifact_harvester.py` |
| **BiOS Core** | Execution Signal | `~/.arca/approved_actions.json` | `approval_poller.py` |
| **Notion** | Task Lifecycle | Database `3284d2d9fc7c811188deeeaba9c5f845` | `archivist.py`, `serena_notion_poller.py` |

---

## **3. The Automated Documentation Pipeline (The Closed Loop)**

Documentation is developed through a rigorous five-stage autonomous pipeline.

### **Stage 1: Harvest (Scrape & Stage)**
- **Tool**: `scripts/archivist/artifact_harvester.py`
- **Action**: Silently scrapes logs from Claude, Zed, and Antigravity into `biomimetics/.staging/raw_dev_artifacts/`.
- **Hygiene**: Grouped by date; raw data is moved to `.archive/` after processing.

### **Stage 2: Condense (Semantic Stripping)**
- **Tool**: `scripts/archivist/dev_artifact_condenser.py`
- **Model**: `gemini-3.5-flash-lite` (synthesis); tagging/email still `gemini-3.1-flash-lite-preview` (volume quota)
- **Logic**: Filters noise (debug logs, UI JSON) and extracts the "Architectural Essence":
  - Architectural Decisions
  - Engineering Rationales
  - Key Code Diffs
- **Constraint**: Artifacts truncated to 300K characters before processing.

### **Stage 3: Assimilate (Knowledge Synthesis)**
- **Tool**: `scripts/archivist/archivist.py`
- **Action**: Renders condensed artifacts into Obsidian nodes in `docs/obsidian_staging/`.
- **Tagging**: Mandatory BiOS frontmatter (`tags: [bios/architecture, bios/swarm]`).
- **Linking**: Automatically updates **Maps of Content (MOCs)** (e.g., `Biomimetics_MOC`, `Pythia_MOC`) with bidirectional links.

### **Stage 4: Enrich (Noetic Reasoning)**
- **Tool**: `scripts/memory/serena-memory-sync.py`
- **Engine**: **OpenCode (Nemotron-3 Super / MiniMax M2.5)**
- **Action**: Performs "Heavy Reasoning" on code specifications to extract deep system connections and actionable items.
- **Enrichment Marker**: Adds an "OpenCode Analysis" section to the node.

### **Stage 5: Sync (Memory Integration)**
- **Tool**: `scripts/archivist/tagged_memory_sync.py`
- **Action**: Syncs Obsidian nodes to the **GCP Memory Orchestrator** and **MuninnDB**.
- **Operational Signal**: Files MUST contain the `<!-- LLM_TAGGED -->` marker to be eligible for sync.

---

## **4. Multi-Model Cognitive Routing**

Tasks are routed to optimize for reasoning depth while minimizing context cost:

1.  **Triage (Gemini 3.1 Flash Lite)**: High-volume tagging and email classification (500 free calls/day). Condensation uses Gemini 3.5 Flash Lite.
2.  **Entity Mapping (Gemma 4 26B)**: High-velocity graph construction (Neo4j Cypher) from structured logs.
3.  **Topological Analysis (Gemma 4 31B)**: Deep mathematical reasoning for code diffs (CGA, Mamba-2 matrices).
4.  **Noetic Enrichment (OpenCode)**: External cross-reference and "Deep Thinking" analysis via **Kimi-K2.5-Thinking**.

---

## **5. Operational Directives**

- **Operational Hygiene**: The `<!-- LLM_TAGGED -->` marker must be present for any file intended for long-term memory.
- **Human Role**: Human intervention is strictly limited to "Approval via Notion." Any requirement for human-authored documentation is considered a **System Failure**.
- **Latency**: The documentation heartbeat must stay within 24 hours of the development swarm.
- **Archive Policy**: Raw artifacts are moved to `.archive/` immediately after Stage 2 completion.

---

# **Appendix: Architectural Context & Reasoning**

The paradigm of artificial intelligence development has shifted fundamentally from static codebase management to the orchestration of continuous-time dynamical systems. Within this highly advanced operational landscape, traditional frameworks for manual documentation and system tracking are entirely obsolete. The deployment of the ARCA intelligence—powered by the Noumenal Engine—requires a profound transformation in how system architectures are monitored, mapped, and understood.

## **The Ingestion Matrix: Distributed Service Topology**
The ARCA system operates as a distributed mesh of over thirty containerized services. To accurately map the system's operational state, the documentation pipeline parses the status of these foundational containers and their associated memory layers (MuninnDB, MemU, Qdrant).

## **Mathematical Geometric Reasoning**
The documentation pipeline interprets the structural skeleton of the ARCA intelligence and extracts complex reasoning from mathematical code diffs. It utilizes LLMs to mathematically interpret changes to the manifold, mapping code changes to a strict ontology based on the established grade decomposition of Conformal Geometric Algebra (CGA).

---

*Last Updated: 2026-06-04*
*Authoritative Source for: BiOS Archivist, Serena, and the Antigravity Swarm.*
