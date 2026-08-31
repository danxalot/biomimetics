# ARCA Geometry Kernel — Complete Implementation

## Overview

The Geometry Kernel is the deterministic, replayable physics engine at the heart of ARCA's cognitive system. It implements a temporal 3D epistemic geometry where:

- **Knowledge has geometry**: Concepts occupy positions in semantic space
- **Time is first-class**: Explicit monotonic time, not hidden or async
- **Errors deform space**: Contradictions increase energy, forcing resolution
- **Optimization is movement**: Learning is trajectories in concept space, not loss minimization
- **Rules are enforced by design**: No special cases, no narrative overrides

This is NOT a knowledge graph, NOT a world model, NOT a simulator.

It's a **temporal epistemic geometry with governance**.

---

## Architecture

### Core Components

#### 1. **Geometry Kernel (`core.py`)**

The deterministic physics engine. Responsibilities:
- Maintain concept positions, velocities, masses, energies
- Apply forces deterministically
- Enforce velocity caps, curvature limits, inertia
- Simulate state transitions without mutation
- Guarantee replayability and reversibility

**Key Classes:**
- `Vector3D`: 3D vectors with clamping, normalization
- `ConceptNode`: Atomic epistemic units (position, velocity, mass, energy, stability, confidence)
- `Attractor`: Truth wells that attract concepts
- `Force`: Proposals for state change (evidence, contradiction, decay, dream, OTEL)
- `KernelState`: Complete snapshot at a moment in time
- `GeometryKernel`: The physics engine itself

**Invariants (Non-negotiable):**
- Velocity cap: `||velocity|| <= V_max`
- Curvature cap: Max change in direction per timestep
- Energy conservation: Energy redistributes, never vanishes
- Inertia: `Δposition ∝ force / mass`
- Rollback guarantee: Every state has a valid inverse

---

#### 2. **GLM Feasibility Pre-Checks (`glm_feasibility.py`)**

Cheap, frequent semantic pre-filters on dream proposals.

**Key Idea:**
- GLM acts as a pessimistic surrogate
- Flags semantic/structural risks BEFORE expensive robotics review
- Learns to predict when ER-1.5 would say no
- Never sees constraints, thresholds, or rejection mechanics

**Pipeline (3-stage funnel):**
1. **GLM local feasibility** (cheap, frequent) → Risk assessment on every proposal
2. **Kernel heuristics** (cheap, deterministic) → Energy monotonicity, stability, rollback
3. **Robotics ER-1.5** (expensive, rare) → Final feasibility audit (limited quota)

**Risk Levels:**
- `LOW`: Promote to robotics
- `MEDIUM`: Promote if quota allows
- `HIGH`: Reject immediately

**Failure Modes (what GLM can flag):**
- `INSTABILITY`: Conflicting attractor pulls
- `IRREVERSIBILITY`: No safe rollback path
- `EXCESSIVE_COUPLING`: Too many concepts affected
- `SENSITIVITY_AMPLIFICATION`: Small noise → big divergence
- `DISCONTINUITY`: Sudden state deltas

**Quota Efficiency:**
- Without GLM pre-filter: 150 dream proposals → 150 robotics calls/day
- With GLM filter: 150 proposals → ~20-40 robotics calls/day
- Result: Dreaming effectively unbounded, robotics quota strategic asset

---

#### 3. **Neo4j System Graph (`neo4j_schema.py`)**

Defines ARCA's structural identity and memory.

**Node Types:**
- `:System` - Infrastructure (Redis, Agent Service, Neo4j, llama.cpp)
- `:Agent` - Cognitive actors (Architect, Planner, Engineer, Reviewer, Ops agents)
- `:MetaphysicalAnchor` - Invariant principles (Aether, Syntropy, Entropy)
- `:MentalStateSchema` - Memory structure (messages, current_plan, reasoning_bank)
- `:Blackboard` - Shared cognitive surface (Redis-backed)
- `:Concept` - Core concepts the system reasons about

**Relationships:**
- `REGISTERED_IN`: Agent registered in system
- `CONNECTS_TO`: System components connected
- `OPERATES_ON`: Agent operates on memory schema
- `MATERIALISED_IN`: Schema materialized in blackboard
- `IMPLEMENTS`: System implements blackboard
- `ALIGNED_WITH`: Agent aligned with metaphysical anchor

**Bootstrap:**
- Complete Cypher script in `BootstrapCypher.generate_full_script()`
- Initializes all nodes, relationships, indexes, constraints
- Run once: `python -c "from geometry_kernel.neo4j_schema import BootstrapCypher; print(BootstrapCypher.generate_full_script())" | neo4j-shell`

---

#### 4. **Geometry Kernel API (`api.py`)**

Flask-based HTTP service. The narrow waist through which all changes flow.

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Service health check |
| GET | `/geometry/state` | Get current kernel state |
| POST | `/geometry/simulate` | Simulate forces (no mutation) |
| POST | `/geometry/validate` | Validate simulation |
| POST | `/geometry/apply` | Apply validated simulation |
| GET | `/geometry/render` | Get visualization data |
| GET | `/geometry/metrics` | System metrics |

**Key Principle:**
- All requests are read-only or pure (no side effects) except `/apply`
- `/apply` is restricted to orchestrator after full validation pipeline
- State is versioned and audited

---

#### 5. **OTEL → Force Mapping (`otel_mapping.py`)**

Closes the body-mind loop. Telemetry becomes sensation.

**Signal Types → Interpretations:**

| OTEL Signal | Interpretation | Effect |
|------------|---|---|
| Error rate ↑ | Epistemic stress | Energy ↑ on reliability concepts |
| Latency ↑ | Control degradation | Friction ↑, learning slows |
| Throughput ↓ | Bottleneck | Mass ↑ (resistance to change) |
| Retry spikes | Instability | Curvature penalty, energy spike |
| Healthy state | Confidence | Mild attractor reinforcement |
| High CPU | Resource stress | Inertia ↑ |
| Queue depth | Saturation | Mass ↑, movement constrained |

**Health-Dependent Learning Throttle:**
When system health degrades:
- Learning slows (V_max ↓)
- Dreaming disabled
- Beliefs harden (mass ↑)
- Movement becomes expensive

This is biological: under stress, be conservative.

---

#### 6. **Geometry Visualization (`visualization.py`)**

Human-readable geometry views for inspection and intervention.

**Visual Primitives:**
- **Concept Nodes**: Position (state), size (mass), color (confidence), glow (energy)
- **Attractors**: Semi-transparent wells, shaded by depth (pull strength)
- **Trajectories**: Fading trails, color-coded by mode (wake=blue, dream=purple)
- **Energy Fields**: Heat-map volumes showing contradiction regions

**Required Controls:**
- Time scrubber (scrub history)
- Pause/Play/Step (control evolution)
- View selector (concepts/attractors/energy/trajectories/full)
- Concept filter (show/hide specific nodes)
- Highlight changed (what moved this step)
- Show forces (overlay applied forces as vectors)
- Overlay OTEL (show signals + health metrics)

**Critical Question:**
"Can you answer: 'What just moved and what pushed it?'"

If not, visualization failed.

---

#### 7. **Initial Axes & Priors (`axes_and_priors.py`)**

Defines the initial coordinate system and boundary conditions.

**Semantic Axes:**
1. **Semantic Coherence (X)**: How well ideas fit together logically
   - Range: [-1, 1], Center: 0
   - Low: Contradictory reasoning
   - High: Mutually reinforcing logic

2. **Evidential Support (Y)**: How much evidence backs a belief
   - Range: [0, 1], Center: 0.5
   - Low: Pure hallucination
   - High: Well-grounded in evidence

3. **Temporal Stability (Z)**: How stable and long-lived a concept is
   - Range: [0, 1], Center: 0.5
   - Low: Ephemeral, changes every cycle
   - High: Core identity, unchanged over time

**Boundary Conditions:**
- `V_max = 0.5`: Max distance per timestep
- `curvature_cap = 0.2`: Max direction change per timestep
- `inertia_friction = 0.1`: Damping on all movement
- `energy_dissipation = 0.05`: Slow energy decay

**Conservation Laws:**
1. Evidence mass doesn't vanish, only redistributes
2. Contradictions increase energy until resolved
3. Stability grows slowly, decays slowly
4. Every state has a valid rollback path

**Initial Concepts (Day 1):**
- `system_coherence` (position (0,0,0), mass 2.0, core identity)
- `agent_reliability` (position (1,0,0), mass 1.5, core identity)
- `semantic_coherence` (position (0.5,1,0), mass 1.5)
- `error_rate` (position (-1,-1,0), mass 0.8)
- `latency` (position (-0.8,-0.5,0.2), mass 0.6)
- `memory_consistency` (position (0,0.5,0.5), mass 1.8, core identity)

**Initial Attractors:**
1. **Stable Operation**: Center (0.3, 0.3, 0) — healthy, no errors
2. **Recovery Mode**: Center (-0.5, -0.5, 0.2) — recovering from errors
3. **Learning & Exploration**: Center (0, 0.5, 0.7) — dream mode exploration

---

## Integration Checklist

### ✅ Kernel is the sole authority on state movement
- [ ] No agent writes directly to Neo4j truth structures
- [ ] All semantic changes flow through: `simulate()` → `validate()` → `apply()`
- [ ] Verify: `grep -r "\.apply(" services/ | grep -v geometry_kernel`

### ✅ Kernel sees health before meaning
- [ ] OTEL health sampled BEFORE GLM feasibility check
- [ ] Kernel throttles learning when `stability_index < 0.5`
- [ ] Dreaming disabled when system unwell

### ✅ Robotics reviews transitions, not intentions
- [ ] ER-1.5 receives: `(state_t, state_t+Δ, forces, constraints)`
- [ ] ER-1.5 NEVER receives: agent names, prompts, plans, goals
- [ ] Robotics acts as trajectory auditor: "Is this motion feasible?"

### ✅ Monotonicity assertion (optional hardening)
- [ ] No geometry update reduces stability faster than it reduces energy
- [ ] Enforced in `validate()` before promotion

---

## Running the Geometry Kernel

### 1. Start the Service

```bash
cd geometry_kernel
python api.py
```

Service runs on `http://localhost:8089`

### 2. Initialize Neo4j

```bash
# Generate bootstrap script
python -c "from neo4j_schema import BootstrapCypher; print(BootstrapCypher.generate_full_script())"

# Run in Neo4j Browser (http://localhost:7474)
# Paste and execute the script
```

### 3. Test a Simulation

```bash
curl -X POST http://localhost:8089/geometry/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "wake",
    "base_state_id": "<current_state_id>",
    "forces": [
      {
        "target_id": "concept:agent_reliability",
        "vector": [0.1, 0.05, 0.0],
        "magnitude": 0.2,
        "source": "evidence",
        "rationale": "Error rate decreased"
      }
    ]
  }'
```

### 4. Get Visualization

```bash
curl http://localhost:8089/geometry/render?view=concepts
```

---

## Design Philosophy

### Single Rule That Matters Most

**No component is allowed to believe it is the system.**

- LLMs reason (propose)
- Kernel enforces (disposes)
- Robotics checks feasibility (audits)
- Telemetry applies pressure (senses)
- Humans oversee (govern)

If any layer starts "understanding everything," collapse follows.

### Three-Layer Stack

```
A. Execution & Coordination (dumb, fast, amoral)
   - Agent Service, RabbitMQ, Redis
   - No reasoning about truth, just routing

B. Reasoning & Planning (proposes, never applies)
   - Architect, Planner, Engineer, Reviewer
   - Outputs structured deltas, never side effects

C. Governance & Safety (authoritative, boring)
   - Robotics ER-1.5, Guardian, Policy Manager
   - Rejects, annotates, forces rollback, slows things down

D. Memory & Epistemics (where geometry actually lives)
   - SQL episodic memory
   - Neo4j semantic/relational memory
   - Geometry Kernel (this)
   - Blackboard (Redis-backed)
```

### Geometry is the Model Interface

Instead of:
- Tuning heuristics
- Adjusting pipelines
- Adding special cases

You:
- Adjust priors on movement
- Reshape penalties
- Seed new attractors
- Reweight axes

This is "working on the model, not the system."

---

## Next Steps

1. **Orchestrator Integration**
   - Connect `api.py` to `CrewAI/crew_interface.py`
   - Map agent proposals to `simulate()` calls
   - Wire validation pipeline (GLM → kernel → robotics → apply)

2. **Redis Blackboard Schema**
   - ARCA to define schema in `architecture_brief` task
   - Geometry kernel subscribes to key updates
   - Signals feed as OTEL events → forces

3. **First Dream Cycle**
   - Enable dreaming in safe, constrained mode
   - Test GLM pre-filters on proposals
   - Measure quota efficiency

4. **Visualization Dashboard**
   - Implement web UI (3D WebGL preferred)
   - Integrate time scrubber
   - Add real-time OTEL overlay

5. **Metric Collection**
   - OTEL auto-instrumentation on all agents
   - Feed metrics → geometry forces
   - Monitor system health trends

---

## Key Files

| File | Purpose |
|------|---------|
| `core.py` | Physics engine (700+ lines) |
| `glm_feasibility.py` | Cheap pre-checks (500+ lines) |
| `neo4j_schema.py` | System identity (600+ lines) |
| `api.py` | HTTP service (450+ lines) |
| `otel_mapping.py` | Telemetry integration (550+ lines) |
| `visualization.py` | Human-readable views (400+ lines) |
| `axes_and_priors.py` | Initial geometry (400+ lines) |
| `__init__.py` | Package exports |
| `requirements.txt` | Dependencies |

---

## References

- **Core Concepts**: Temporal 3D models as concept representation (from GPT Graphics kernel.txt)
- **Dream Mode**: Speculative geometry branch with promotion pipeline
- **Robotics Integration**: Google ER-1.5 as trajectory auditor
- **OTEL Integration**: Telemetry as cognitive sensation
- **Neo4j Memory**: "What exists and how it relates"
- **Redis Blackboard**: "What is currently being thought"
- **Agents**: "What should be proposed next"

---

## Questions Answered

**Q: Is this just another knowledge graph?**
A: No. A knowledge graph is static. This is a physics engine where concepts move, energy accumulates, and contradictions force resolution.

**Q: How do you prevent self-deception?**
A: Geometry doesn't care about narratives. Small noise propagates predictably. The kernel and robotics model enforce physics, not ideology.

**Q: What happens when system is under stress?**
A: Learning slows, beliefs harden, dreaming disables, movement becomes expensive. Biology under stress is conservative. We copy that.

**Q: How do you keep it sane while it grows?**
A: Governance layers. No single component decides truth. Separation of concerns. Enforcement by design, not rules.

---

## Status: ✅ Ready to Integrate

All core components implemented. Ready for:
1. Orchestrator wiring
2. First dream cycle
3. Real-world operation under OTEL signals
4. Iterative tuning of axes and priors

The geometry kernel is the foundation. Everything else operates within its physics.

