# Geometry Kernel — Technical Specification (Merged)

This document is the canonical specification for the `geometry_kernel` service. It consolidates the core technical spec, MCP tools/skills mapping, and a concise scripts/modules function reference so maintainers and operators can find all geometry-related functionality in one place.

## Purpose
- Deterministic, replayable physics engine for ARCA's temporal epistemic geometry.
- Kernel is the sole authority that moves belief-state in a 3D semantic space.

## High-level Components
- Core physics: `core.py` (`GeometryKernel`, `KernelState`, `ConceptNode`, `Attractor`, `Force`, `Vector3D`, `SimulationResult`).
- HTTP API: `api.py` (Flask) — narrow waist for proposals and state operations.
- Cognitive scheduler / model engine: `model_engine.py` (`CognitiveScheduler`, `CognitiveTickResult`) for VL/LLM orchestration and reasoning.
- Visual/audio spike detection & runtime: `main.py` (`V2GeometryKernel`, `KernelConfig`) — orchestrates the continuous tick loop and embedding worker.
- Recursive ingestion (document → geometry): `recursive_ingestion.py` (`RecursiveIngestion`).
- Audit service: `audit_service.py` (`LocalAuditor`) — uses configured LLM gateway for trajectory audits.
- OTEL mapping: `otel_mapping.py` (maps telemetry signals → `Force` objects).
- Visualization spec: `visualization.py` (builders and dashboard spec).
- Neo4j schema and bootstrap: `neo4j_schema.py` (schema, bootstrap Cypher generator).

## Primary Classes & Functions (Authoritative list)

- Geometry Kernel (`core.py`)
  - `GeometryKernel.__init__(v_max, curvature_cap, inertia_friction, time_step, initial_axes_weights)` — create engine with invariants.
  - `initialize_state(nodes, attractors)` — produce initial `KernelState` and set `current_state`.
  - `simulate(base_state_id, forces, attractor_proposals, axis_emphasis)` — produce a `SimulationResult` (no mutation).
  - `validate(simulation_result)` — deterministic checks that enforce invariants (stability, rollback safety, monotonicity).
  - `apply(simulation_result)` — atomically mutate `current_state` and append to `state_history` (auditable, versioned).
  - `ingest_hse_state(hse_dict)` — convert HSE/OTEL input into `HSEState` and apply health/throttle calculations.
  - Serialization helpers: `KernelState.to_dict()/from_dict`, `ConceptNode.to_dict()/from_dict`.

- API (`api.py`)
  - `init_kernel()` — instantiate `GeometryKernel`, `CognitiveScheduler`, `LocalAuditor`, connect Redis, start HSE polling and cognitive tick.
  - Background threads: `_poll_hse_loop()` (poll Redis key `arca:hse:state_vector`), `_cognitive_tick_loop()` (300ms heartbeat → calls `kernel.simulate([])` for physics-only ticks and publishes summary to Redis key `arca:geometry:tick_summary`).
  - REST endpoints (Flask):
    - `GET /health` — service health
    - `GET /geometry/state` — return `current_state`
    - `POST /geometry/simulate` — simulate with supplied `forces`, `mode`, `attractor_proposals`, `axis_emphasis` → returns `SimulationResult`
    - `POST /geometry/validate` — validate a previously produced simulation (accept/soften/reject)
    - `POST /geometry/apply` — apply validated simulation (restricted: expected to be called by orchestrator)
    - `GET /geometry/render` — render visualization JSON using `visualization.py`
    - `GET /geometry/metrics` — metrics endpoint

- Model Engine / Scheduler (`model_engine.py`)
  - `CognitiveScheduler._run_perception(image)` — spike detection via `VisualSpikeDetector`, calls VL when needed.
  - `_run_reasoning(context)` — calls DeepSeek R1 via the LLM gateway (configured by `LLM_GATEWAY_URL`).
  - `_run_safety(content)` — optional Guardian safety screening.
  - `tick(image)` — orchestrates perception → reasoning → safety; returns `CognitiveTickResult`.
  - `run_reasoning_phase(context_text, prompt_template)` — used by `RecursiveIngestion` to extract JSON concepts from document chunks.

- Audit Service (`audit_service.py`)
  - `LocalAuditor.audit_trajectory(proposed_state, trajectory_plot_path)` — quick auto-approve when stability high, otherwise calls visual LLM audit via gateway.

- Recursive Ingestion (`recursive_ingestion.py`)
  - `ingest_content(file_path, objective, content_type, verbosity, use_semantic_chunking)` — probe → chunk → recursive loop using `scheduler.run_reasoning_phase` → aggregate geometry objects.

- OTEL Mapping (`otel_mapping.py`)
  - `OTELSignal` data structure and `SignalForceMapper.map_signal(signal)` → returns `ForceMapping` with `Force` objects and interpretation.
  - Signal mappers: error_rate, latency, throughput, retry_spikes, healthy_state, cpu_usage, queue_depth.
  - `HealthDependentThrottling.compute_kernel_throttle()` — compute adjustments (V_max, inertia, etc.) from `health_metrics`.

- Visualization (`visualization.py`)
  - `VisualizationBuilder` to convert kernel objects to `VisualNode`, `VisualAttractor`, `VisualEnergy`, `VisualTrajectory`.

## Workflows & Dataflows (end-to-end)

1. Agent/Component proposes a change via the API: `POST /geometry/simulate` with `forces` + optional attractor proposals.
2. Kernel runs `simulate()` → returns `SimulationResult` (predicted `KernelState`, metrics like stability and energy_delta).
3. Pre-checks: GLM feasibility (`glm_feasibility.py`) may be invoked by orchestrator.
4. Auditor (`LocalAuditor`) may visually audit the trajectory (via `llm_interface`).
5. `POST /geometry/validate` runs invariant checks: monotonicity, rollback safety, curvature and velocity caps.
6. If validated, orchestrator calls `POST /geometry/apply` to persist the state; kernel appends to `state_history` and updates `current_state`.
7. Background tick loop simulates physics-only ticks (decay, attractor pulls) and publishes summaries to Redis.
8. OTEL signals mapped via `SignalForceMapper` are converted to `Force` objects and can be fed into `simulate` to reflect telemetry-driven forces.

## Configurations & Entrypoints

Environment variables observed in code:
- `REDIS_HOST` (default `redis`)
- `LLM_GATEWAY_URL` (default `http://llm_gateway:8080`)
- `QWEN_VL_URL`, `QWEN_VL_API_KEY`, `QWEN_MODEL_NAME`

Ports and entrypoints:
- Container CMD: `python api.py` (see `Dockerfile`) — runs Flask service and background threads.
- Dockerfile exposes `8087` (healthcheck) — README examples reference `8089`; confirm during deployment.

## Supplemental MCP Tools & Skills

- `geometry_simulate`, `geometry_apply`, `geometry_ingest`, `geometry_fetch_history`, `geometry_interpret`, `geometry_audit`, `geometry_state`, `geometry_analyze` — MCP tools registered in `services/mcp_server/mcp_server.py` and implemented/proxied under `services/mcp_server/tools/`.
- Embedding: `embed_geometry_description` in `services/mcp_server/tools/mcp_geometry_embed.py`.
- Agent hooks: agents call `geometry_ingest` and use `geometry_state` read tools; director skills decide when to promote patterns into skills.

## Script & Module Function Reference (detailed)

- `api.py`: Bootstrap and Flask endpoints; starts HSE poll and cognitive tick loops; manages Redis blackboard keys: `arca:geometry:tick_summary`, `arca:blackboard:working_model`, `arca:blackboard:geometry_history`.

- `core.py`: Simulation primitives and state management; `simulate()`, `validate()`, `apply()`, invariants, and serialization.

- `main.py`: Runtime defaults (`KernelConfig`), `V2GeometryKernel` orchestration, embedding worker lifecycle, and local demo entrypoints.

- `model_engine.py`: `CognitiveScheduler` orchestration for perception/reasoning/safety; wraps `llm_interface` calls and provides `run_reasoning_phase()` used by ingestion.

- `recursive_ingestion.py`: Document-to-geometry conversion pipeline; chunking, prompt-driven extraction, aggregation into `ConceptNode` objects.

- `embedding_worker.py`: Background embedding generator for ingested content and geometry descriptions.

- `glm_feasibility.py`: Quick GLM-based gating heuristics used prior to heavy audits.

- `audit_service.py` & `holistic_auditor.py`: Local and holistic audit orchestrators; escalate to visual LLM audits when needed.

- `otel_mapping.py`: Telemetry → `Force` deterministic mappings and health-based throttling.

- `visual_spike.py`: Visual spike detection primitives.

- `visualization.py`: Visual primitive builders and dashboard spec.

- `geometry_agent.py`: Experimental agent helpers for geometry proposals and tests.

- `blackboard.py`: Redis abstraction and helper functions for publish/subscribe and storing summaries/history.

- `axes_and_priors.py`, `genesis_chain_config.py`: Defaults for axis weights and genesis bootstrap.

- `semantic_chunker.py`, `state_comparison.py`: Chunking utilities and state diff helpers.

- `energy_integration.py`, `fusion.py`: Numerical and fusion helpers for energy/momentum updates.

- `components.py`, `context_memory.py`, `models/`, `research_augmentation.py`: Supporting modules and research helpers.

- `neo4j_schema.py`: Neo4j schema and Cypher bootstrap generator.

- `llm_interface.py`: Gateway adapter for VL/LLM calls (retry, templating, normalization).

- `requirements.txt` & `Dockerfile`: Runtime deps and container build; note port mismatch to align before production rollout.

## Auditability, Security & Safety Notes

- `POST /geometry/apply` is side-effecting and must be restricted to orchestrator/service accounts in production.
- Audit decisions rely on LLMs; tighten thresholds for Lyceum deployment and avoid auto-approving without stricter constraints.
- The kernel keeps a `state_history` for replay and debugging; ensure `state_history` persistence policy meets retention requirements.

## Examples & Artifacts

- Recorded agent interactions and ingest responses are stored under `shared_storage/responses/` and `shared_storage/jobs/` — these contain concrete `geometry_ingest` inputs/outputs useful for examples and tests.

### Example: `geometry_ingest` payload (representative)

Below is a representative `geometry_ingest` payload format used by agents when ingesting documents into the kernel. This example is adapted from recorded `shared_storage` job artifacts and is suitable for smoke tests.

```json
{
  "file_path": "/data/docs/design_spec.md",
  "objective": "Extract core concepts, evidential claims, and actionable attractors",
  "content_type": "markdown",
  "metadata": {
    "source": "user_upload",
    "uploaded_by": "alice@example.com",
    "received_at": "2026-01-15T07:51:23Z"
  },
  "options": {
    "verbosity": "medium",
    "use_semantic_chunking": true,
    "preserve_headings": true
  }
}
```

### Example: simulate → validate → apply (curl smoke sequence)

Use this sequence against a running `geometry_kernel` service to exercise the end-to-end flow. Replace `<HOST>` and `<SIM_ID>` as returned from the `simulate` step.

```bash
# 1) Simulate (dry-run)
curl -sS -X POST http://<HOST>:8087/geometry/simulate \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "wake",
    "base_state_id": null,
    "forces": [
      {
        "target_id": "concept:agent_reliability",
        "vector": [0.05, 0.02, 0.0],
        "magnitude": 0.12,
        "source": "ingest",
        "rationale": "New evidence: error rate decreased after patch"
      }
    ]
  }' | jq .

# 2) Validate (use returned simulation_id from previous response)
curl -sS -X POST http://<HOST>:8087/geometry/validate \
  -H 'Content-Type: application/json' \
  -d '{"simulation_id": "<SIM_ID>"}' | jq .

# 3) Apply (requires orchestrator privileges; example shown for completeness)
curl -sS -X POST http://<HOST>:8087/geometry/apply \
  -H 'Content-Type: application/json' \
  -d '{"simulation_id": "<SIM_ID>", "approver": "orchestrator-service"}' | jq .
```

Notes:
- The `validate` step returns deterministic invariant checks (energy_delta, stability score, rollback safety); only pass simulations to `apply` when checks succeed.
- Use recorded artifacts in `shared_storage/responses/` for realistic input payloads to populate `file_path` and metadata fields.

## Known Inconsistencies Observed
- README examples reference `http://localhost:8089`; `Dockerfile` uses `8087` (healthcheck). Confirm desired HTTP port during deployment.

---

If you'd like, I will:
- Extract representative `shared_storage/responses/*geometry_ingest*` artifacts into an `Examples` appendix in this file, and/or
- Open a commit/PR that replaces the old spec with this merged file (already replaced locally), and/or
- Run a quick smoke test script template that exercises `/geometry/simulate` → `/geometry/validate` → `/geometry/apply` using recorded example inputs.
