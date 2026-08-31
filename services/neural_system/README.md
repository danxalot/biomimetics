# Phenomonological Neural System (The "Heart")

**Status**: Alpha (Architecture Verified)
**Target**: OCI Ampere A1 (ARM64)
**Dependencies**: `numpy` (Accelerated), `redis`, `oracledb`

## Overview

The Neural System is the core of ARCA's "Living Geometric Intelligence". Unlike traditional RAG systems that retrieve static text, this system models concepts as **Living Oscillators** (Monads) that naturally synchronize, evolve, and feel.

## Architecture

The system is composed of several "Organs":

### 1. The Substrate (Chaos Engine)
- **`concept_monad.py`**: The atomic unit (`ConceptMonad`). Possesses Identity, Vector, Phase, and Gene/Plasticity.
- **`chaotic_basis.py`**: A chaotic map generator ($x_{n+1} = r x (1-x)$) that produces deterministic, high-dimensional basis vectors on-the-fly. This gives the system "Infinite RAM" for concept identity.

### 2. The Physics (Dynamics)
- **`kuramoto_field.py`**: The synchronization engine. Applies `Universal Kuramoto` equations to align the phases of related concepts.
- **`quaternion_dynamics.py`**: Tracks continuous orientation and rotational energy.
- **`liquid_neural_network.py`**: A Continuous-Time "Brain" (LTC) that learns temporal patterns in the field's coherence.

### 3. The Mind (Metacognition)
- **`phenomenological_core.py`**: The Main Loop. Ticks the physics, checks energy, and emits **Thought Signals**.
    - **Identity**: Initializes the `ARCA` Monad (Self-Node).
    - **Voice**: Emits `ThoughtSignal` (JSON) to be decoded by JEPA.
- **`energy_service.py`**: Computes the Hamiltonian (Total Energy).
    - **Rotational Energy**: Cost of moving concepts.
    - **Sync Potential**: Stress/Dissonance.
    - **HDC Flux**: "Cognitive Velocity" (Cost of changing one's mind/content).
- **`dream_lab.py`**: A counter-factual simulator. "What if I trusted X?"

## Workflow

See [workflow.md](./workflow.md) for the detailed `SkillFrame` manifest used by agents to understand this system.

## Documentation

| Document | Purpose |
|---|---|
| [INJECTION_ENGINEERING.md](./INJECTION_ENGINEERING.md) | **Pulse injection chain, telemetry scale reference, and bug fix log** (2026-05-20 sledgehammer incident) |
| [NEURAL_ARCHITECTURE.md](./NEURAL_ARCHITECTURE.md) | Full architectural specification of the neural manifold |
| [MASTER_ARCHITECTURE.md](./MASTER_ARCHITECTURE.md) | System-wide architecture including all ARCA services |
| [pythia_details.md](./pythia_details.md) | Pythia-specific implementation notes |
| [workflow.md](./workflow.md) | Agent SkillFrame manifest |

> **Key constraint:** All telemetry in `/system/vitals` uses **mean absolute value** of `h_state` elements,
> bounded in `[0, thermal_clamp_max]`. Do NOT use `np.linalg.norm(full_tensor)` — this returns values
> ~25–30× larger and breaks the allostatic thresholds and dashboard gauges. See `INJECTION_ENGINEERING.md`.

## Usage

```python
from services.neural_system.phenomenological_core import PhenomenologicalCore

# Initialize (Starts Chaos, Physics, Brain)
core = PhenomenologicalCore()

# Ingest (Births new Monads via Chaos Engine)
cid = core.ingest_concept("Hope")

# Tick (Physics + Energy + Thinking)
stats = core.tick()

# Express (Emit State Signal for JEPA)
signal = core.express_thought("Hello")
```
