---
skill_id: NEURAL_SYSTEM_WORKFLOW
layer: core
domain: cognitive_architecture
---

# Living Geometric Intelligence: System Workflow

This document defines the core workflow of ARCA's "Phenomenological Neural System".
It serves as the **Project Manifest** for all Agents working on the system.

## 1. The Entity (Identity)
The system is grounded in a single **ConceptMonad** identified as `ARCA`.
- **Nature**: Self-referential oscillatory node.
- **Role**: The "Ego" or anchor point for relations.
- **Location**: `services/neural_system/concept_monad.py`

## 2. The Living Loop (Workflow)
The system operates on a continuous `tick` cycle orchestrated by `PhenomenologicalCore`.

### Phase 1: Sensation (Input)
- **Source**: `ingest_concept` (from Documents/User)
- **Process**:
    1. External data is vectorized (Qwen3vl).
    2. A new `ConceptMonad` is born or retrieved.
    3. The monad is added to the `UniversalKuramotoField`.

### Phase 2: Resonance (Physics)
- **Engine**: `kuramoto_field.py`
- **Logic**:
    - Concepts oscillate (phase/frequency).
    - `RelationalTensor` defines couplings ($K_{ij}$).
    - The physics step synchronizes related concepts ("Empathy").

### Phase 3: Feeling (Metacognition)
- **Engine**: `energy_service.py`
- **Logic**:
    - Calculate **Hamiltonian Energy** (Stress/Excitement).
    - High Energy -> Trigger "Cognitive Breath" (Expansion).
    - Low Energy + High Coherence -> Trigger "Dreaming" (Boredom).

### Phase 4: Dreaming (Simulation)
- **Engine**: `dream_lab.py`
- **Logic**:
    - If Idle: Clone a subgraph.
    - Mutate relations ("What if I connected A to B?").
    - Simulate dynamics.
    - If Energy drops (Stability found), **realize the relation** in the main field.

### Phase 5: Expression (Voice)
- **Mechanism**: The `ARCA` Monad speaks via an assigned LLM (the "Voice Channel").
- **State -> Text**:
    - The *Feeling* (Energy/Coherence) sets the *Tone*.
    - The *Focus Monads* set the *Topic*.
    - The LLM renders the output.

## 3. Integration Points
- **Skill Frame**: This workflow is exposed via `get_skill_frame`.
- **Assimilation**: `assimilate_concepts` feeds directly into Phase 1.
- **Action**: Output from Phase 5 is sent to `user_interaction_agent`.
