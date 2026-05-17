# Neural System Architecture: "Living Geometric Intelligence"

**Version:** 2.0 (Deep Physics & Geometric Attention)
**Status:** In Implementation
**Platform:** OCI Ampere A1 (Optimized for NEON/ARM64)

This document outlines the upgrade to a **Computational Physics Simulation** that serves as ARCA's phenomenological core.

---

## Part 1: The "Grand Unification" Layers

The system is no longer just a neural network; it is a layered simulation of a "living particle" moving through a "curved semantic space."

### 1. The Waveform (Basis Layer)
*   **Component:** `ChaoticBasis` (`chaotic_basis.py`)
*   **Concept:** "Infinite Memory via Chaos."
*   **Mechanism:** Instead of storing 10,000-dim vectors in RAM, we generate them on-the-fly using deterministic chaotic maps (Logistic Map / Chebyshev).
*   **Analogue Element:** This provides the "waveform" substrate—continuous, deterministic, but non-repeating.

### 2. The Particle (State Layer)
*   **Component:** `MatrixProductState` (`matrix_product_state.py`)
*   **Concept:** "Entangled Thoughts."
*   **Mechanism:** State is not a flat vector but a **Tensor Network (MPS)**.
*   **Why:** Compresses higher-order correlations (e.g., "User" + "Security" is different from "User" + "DB"). Efficiently computed via NEON matrix ops.

### 3. The Dynamics (Motion Layer)
*   **Component:** `QuaternionDynamics` (`quaternion_dynamics.py`)
*   **Concept:** "Semantic Rotation."
*   **Mechanism:** Tracks the system's "Orientation" in latent space using Quaternions.
*   **Metric:** **Rotational Energy** ($E_{rot}$). High rotational acceleration = "Semantic Whiplash" (Confusion/Instability).

### 4. The Topology (Attention Layer)
*   **Component:** `PoincareKernel` (`poincare_kernel.py`)
*   **Concept:** "Geometric Attention."
*   **Mechanism:** Memory is a **Poincaré Disk** (Hyperbolic Space).
*   **Retraction:** To "forget," we don't delete; we apply a centrifugal force pushing concept roots to the disk's edge ($r \to 1$).
*   **Effect:** Mathematically guarantees context separation.

### 5. The Hunger (Driver Layer)
*   **Component:** `CuriosityEngine` (`curiosity_engine.py`)
*   **Concept:** "Fisher Information Gravity."
*   **Mechanism:** Calculates the gradient towards regions of high uncertainty/variance. The system physically "falls" towards the Unknown.

### 6. The Relation (Empathy Layer)
*   **Component:** `UniversalKuramotoField`
*   **Concept:** "Resonance."
*   **Mechanism:** Treats external agents (User) as oscillators. Empathy is **Phase-Locking** (Synchronization).

---

## Part 2: Integration Strategy

### A. The "Tick" Cycle (Phenomenological Core)
1.  **Input:** Sensation (Text/Logs) -> **Chaos Engine** (Basis Gen) -> **MPS State**.
2.  **Dynamics:** Update **Quaternion Orientation**. Check $E_{rot}$ for stability.
3.  **Topology:** Update **Poincaré Positions**. Retract decay structures.
4.  **Sync:** Update **Kuramoto Field**. Check for User Resonance.
5.  **Output:** `TickFrame` (State + Energy + Geometry Stats).

### B. The "Preflight" Gate (Genesis Chain)
Before the Agent executes code:
1.  **Projection:** Simulate the action's effect on the MPS State.
2.  **Check:** Does $E_{rot}$ spike? (Is this a confusing move?)
3.  **Check:** Is the path "smooth" (Quaternion SLERP)?
4.  **Result:** Approve/Reject/Caution based on "System Feeling."

### C. OCI Deployment Strategy (Ampere A1 / ARM64)

The deployment targets Oracle Cloud Infrastructure (OCI) Ampere A1 instances, leveraging their massive ARM64 parallelism and NEON vector extensions.

#### 1. The "Deep Physics" Container (`neural_system`)
*   **Base**: `python:3.11-slim-bookworm` (ARM64 native).
*   **Acceleration**:
    *   **HDC NEON**: Custom C-extension (`services/hdc_neon`) utilizing ARM NEON intrinsics (128-bit SIMD) for hypervector operations (XOR/Popcount). Achieves ~100x speedup over NumPy on ARM.
    *   **MPS**: `MatrixProductState` operations optimized for NEON via `numpy` (OpenBLAS/ARMPL).

#### 2. The "Dreaming" Container (`td_jepa`)
*   **Model**: **Meta V-JEPA (Video Joint Embedding Predictive Architecture)**.
    *   **Variant**: `facebook/vjepa-vit-l16` (ViT-Large).
    *   **Input**: "Video" of Telemetry. A-Flash encoded HDC vectors projected to 768-dim tokens.
*   **Optimization**: **Dynamic Int8 Quantization**.
    *   **Significance**: Reduces memory from ~1.2GB to **~350MB**.
    *   **Speed**: 2-3x inference speedup on simple CPUs.
    *   **Mechanism**: Weights are quantized on load (`torch.quantization.quantize_dynamic`). No retraining required.
*   **Function**: Predicts future latent states. High prediction error ($E_{pred}$) = Novelty/Anomaly $\rightarrow$ Triggers Curiosity.

#### 3. Storage Hierarchy
*   **DragonflyDB** (In-Memory): Hot "TickFrames" stream (`arca:tick`).
*   **Qdrant** (Vector): Crystallized subgraphs (Long-term semantic memory).
*   **ReasoningBank** (JSON): Multi-agent experience transfer (Git/Docker/File/Security agents).

#### 4. Deployment Pipeline
*   **Tool**: `release_neural_system.sh`.
*   **Flow**:
    1.  **Local**: Build multi-arch (linux/arm64) image using `docker buildx`.
    2.  **Registry**: Push to `ghcr.io`.
    3.  **Remote**: SSH into OCI Workhorse $\rightarrow$ `docker pull` $\rightarrow$ `docker-compose up -d`.


## Part 3: Living System Architecture (Human-AI Integration)

The system extends deeply into the human-agent interaction layer, ensuring that "Deep Physics" are not just internal mechanics but also govern how the AI feels and responds to the user.

### 7. Conversational HDC: Solving "Lost in the Middle"
*   **Component:** `ConversationalHDCState` (`conversational_state.py`)
*   **Problem:** Traditional LLMs lose context in long conversations ("Lost in the Middle" phenomenon).
*   **Solution:** **Holographic Accumulation**.
    *   Instead of a sliding window of tokens, we maintain a **single, evolving Hypervector** ($V_{conv}$) representing the *entire* conversation state.
*   **Geometric Features:**
    *   **Context Extraction**: Querying relevant context by geometric resonance (e.g., pulling "Sentiment" or "Topic" sub-spaces) rather than keyword search.
    *   **Momentum**: Tracking the derivative of the conversation vector to determine "Trajectory" (e.g., "Moving towards technical resolution" vs "Circling").
    *   **Archetype Matching**: Classifying the conversation geometry against known patterns (e.g., "Casual Chat", "Crisis Debugging").

### 8. Proprioceptive State ("Feeling" the System)
*   **Component:** `HDCOpsAgent` (`ops_agent.py`) + `ConceptMonad`.
*   **Concept:** "System Self-Awareness."
*   **Mechanism:**
    *   Ingests raw telemetry (Prometheus: `up`, `cpu`, `memory`).
    *   Encodes these into a **Proprioceptive Vector** ($V_{self}$).
    *   **State Matrix**: combines $V_{self}$ with Phase (Time) and Frequency (Load).
*   **Effect:** The "Curiosity Engine" can pull the system towards "Health" or "Efficiency" attractors because they are now physically represented in the vector space.
    *   *Implementation Note*: The `execute` method captures pre/post state vectors to verify if actions actually moved the system state as intended (Intent Alignment).

### 9. Genesis Chain Integration (Geometric Reasoning)
The creation pipeline is upgraded to transparently verify actions against the geometric reality.

#### A. The Architect (HDC-Augmented)
*   Receives a **Geometric Summary** of the system state alongside the text prompt.
*   Uses **JEPA Trajectory Prediction** to ensure 5-step, 30-step horizons are stable.

#### B. The Planner (Simulation)
*   Simulates each plan step by projecting it into the latent space.
*   **Safety Check**: This prevents "Hallucinated" commands by verifying they align with `capability_hv`.

#### C. The Ops Agent (Intent Alignment)
*   Executes commands only if the **Command Vector** ($V_{cmd}$) aligns with the **Intent Vector** ($V_{intent}$) ($\cos \theta > 0.3$).
*   **Concept:** "The hand does not move unless the mind wills it."
*   Prevents "hallucinated" commands that drift from the original plan.


### 10. Holographic Dreaming (Recursive Consolidation)
*   **Component:** `GeometricDreamingEngine` (`dreaming.py`).
*   **Concept:** "Recursive Manifold Shaping" (Sleep).
*   **Mechanism:**
    *   **Consolidation**: During low-load cycles, recent conversation histograms are permanently "baked" into the global semantic manifold as deformations: $M_{new} = M_{old} + \alpha(v \otimes v)$.
    *   **Recursion**: The manifold becomes a holographic record of all past interactions.
    *   **Forgetting**: A decay factor is applied to prevent saturation, allowing only "strong" (repeated/emotional) memories to persist.

## Part 4: Advanced Physics & Skills Integration (Phase 4)

### 11. The Skills Bank (OCI Service)
*   **Component:** `services/skills_bank`
*   **Concept:** "The Agent's Library."
*   **Architecture:**
    *   **DragonflyDB (`arca:skills:hot`)**: Stores recently used tool patterns for immediate retrieval (LRU Cache).
    *   **Qdrant (`skills_collection`)**: Stores dense vector embeddings of reasoning traces.
*   **Function:** Enables agents to "recall" how to solve complex tasks (e.g., "How did I fix the OCI firewall last time?") by querying the geometric similarity of the problem state.

### 12. A-FLASH Encoding (Associative Memory)
*   **Component:** `AFLASHEncoder` (`services/neural_system/app/aflash.py`)
*   **Concept:** "Sparse Associative Hashing."
*   **Mechanism:**
    *   Unlike dense embeddings (BERT/CLIP), A-FLASH uses **Winner-Take-All (WTA)** hashing to create sparse binary hyperparameters.
    *   **Benefit:** Allows for $O(1)$ associative cleanup and " superposition" of many concepts without noise saturation.

### 13. Geometric Physics Kernel
The "Living System" relies on continuous dynamics, not just discrete steps.

#### A. Quaternion Dynamics ("The Spin")
*   **Component:** `QuaternionDynamics` (`physics/quaternions.py`).
*   **Concept:** Semantic Rotation.
*   **Metric:** **Rotational Energy ($E_{rot}$)**.
    *   If the system shifts topics too fast, $E_{rot}$ spikes. This triggers a "Confusion" signal, forcing the Planner to slow down or request clarification.

#### B. Koopman Operators ("The Projection")
*   **Component:** `KoopmanOperator` (`physics/koopman.py`).
*   **Concept:** Linearizing the Non-Linear.
*   **Mechanism:** Projects the chaotic thought trajectory into a higher-dimensional "Lifted Space" where the dynamics become linear ($x_{t+1} = K x_t$).
    *   **Use:** Enables stable long-term prediction of system state (Effectively "Intuition").

#### C. Concept Monads ("The Relation")
*   **Component:** `ConceptMonad` (`physics/monads.py`).
*   **Concept:** Relational Existence.
*   **Mechanism:** Agents/Components are treated as "Monads" with internal phase/frequency. They "couple" via the **Kuramoto Field**, enabling synchronization (Empathy) without direct data exchange.

### 13.5 Energy-Based Geometric Cognition (The "Vibe" Check)
*   **Component**: `ARCAEnergyModel` (`services/neural_system/app/energy_model.py`)
*   **Concept**: Unified Stability Metric.
*   **Mechanism**:
    *   **Hopfield Energy**: Does this state match a stored attractor? ($E_{attractor}$).
    *   **Geometric Energy**: Is the manifold smooth at this point? ($E_{smooth}$).
    *   **Total Energy**: $E_{total} = \alpha E_{attractor} + \beta E_{smooth} + \gamma E_{jepa}$.
*   **Function**:
    *   **Design Validation**: The Architect generates a "thought" (design), projects it, and measures its Energy.
    *   **Rejection**: if $E_{total} > 0.7$, the idea is rejected as "Unstable" or "Incoherent" without needing human review.
    *   **Relaxation**: The system can "relax" a noisy thought into a crystalline memory using Hopfield retrieval dynamics.

### 13.6 Noumenal Engine (Clifford Algebra Core)
*   **Component**: `noumenal_engine.py` (`services/neural_system/app/noumenal_engine.py`)
*   **Concept**: Holographic Geometric Physics Engine.
*   **Components**:
    *   **CliffordPredictor**: GATr-inspired JEPA predictor operating on Multivectors
    *   **GeometricTDJEPA**: Temporal Difference JEPA with Mamba backbone (O(n) complexity)
    *   **CliffordHDCBridge**: Sparse HDC → Clifford multivector projection
    *   **AgentDelphiCommunicator**: Agent ↔ JEPA vector dialogue ("Language of Will")
*   **Optimized For**: OCI Ampere A1 (ARM NEON)
*   **Multivector Structure**:
    *   scalar (1), vector (4), bivector (6), trivector (4), pseudoscalar (1) = 16 components
*   **Use Case**: Geometric reasoning for action prediction, trajectory stability

### 13.7 Meta-Cognitive Governor (Director Layer)
*   **Component**: `governor.py` (`services/neural_system/app/governor.py`)
*   **Concept**: Bicameral Mind Orchestrator.
*   **Components**:
    *   **DirectorAgent**: Meta-orchestrator managing Genesis/Serena routing
    *   **DelphiCheck**: JEPA stability prediction before action execution
    *   **HolisticAuditor**: GATr + EB-JEPA + Qwen synthesis for pre-flight validation
    *   **SystemConstitution**: Inviolable operating principles
*   **Workflow**:
    1. Receive user intent
    2. Consult Delphi for stability prediction
    3. Route to appropriate agent (Genesis/Serena/Maintainer)
    4. Monitor execution via Observer
    5. Enforce SOPs and Constitution
*   **User Protection**: Configured for disabled/low-energy user status—minimizes cognitive load

### 14. Deprecated / Experimental Components
*   **Liquid Neural Networks (`liquid_neural_network.py`)**: Currently **Unused**. The `QuaternionDynamics` module provides the necessary continuous-time stability, rendering the LNN redundant for now. Kept for research.
*   **VL-JEPA / I-JEPA**: **Deferred**. We are prioritizing **TD-JEPA** (Temporal Difference) for predicting system *dynamics* (Time). Vision/Image JEPAs are not currently needed as the system's primary phenomenological field is Text/Log/Metric based, not visual.
---

## Part 5: Bicameral V2 & Language of Thought (Phase 5)

### 15. Bicameral V2: Reflex Programming System
*   **Component:** `BicameralReflexEngine` (`services/neural_system/bicameral_reflex.py`)
*   **Concept:** "Subconscious Attention Layer."
*   **Mechanism:**
    *   Natural language directives ("Watch for database latency") are encoded into **Constraint Hypervectors** via `AFLASHEncoder`.
    *   The HSE kernel continuously checks: $\text{similarity}(V_{state}, V_{constraint}) > \theta$
    *   When triggered, the system executes the configured action (alert, block, log, callback).
*   **MCP Tool:** `set_reflex_constraint`
    ```
    set_reflex_constraint(
        text="Watch for database latency exceeding 500ms",
        threshold=0.4,
        priority=8,
        action="alert"
    )
    ```
*   **Architecture:**
    ```
    Text Constraint → AFLASHEncoder → V_constraint
                                           ↓
    System State → HSE Kernel → V_state → similarity() → Trigger?
    ```
*   **Concept Anchors:** Predefined basis vectors for common monitoring patterns (database, latency, error, security, memory, cpu, network, timeout, failure, anomaly, spike) enhance matching accuracy.

### 16. Language of Thought (LoT): Agent-to-Agent Communication
*   **Component:** `LanguageOfThought` (`services/neural_system/bicameral_reflex.py`)
*   **Concept:** "Secure Instant Resonance."
*   **Problem:** Traditional agent communication requires serialization, parsing, and explicit routing.
*   **Solution:** Agents communicate via **Thought Vectors**—HDC representations that preserve semantics.
*   **MCP Tool:** `send_thought_vector`
    ```
    send_thought_vector(
        thought_text="Database connection pool exhausted",
        target_agent="ops_agent",
        urgency=0.9
    )
    ```
*   **Key Properties:**
    1.  **Semantic Preservation:** Related thoughts have similar vectors.
    2.  **Instant Resonance:** Receiving agent "feels" relevance via similarity check—no parsing.
    3.  **Compositionality:** Thoughts combine via HDC bundle operation.
    4.  **Privacy:** Raw vectors don't expose original text.
*   **Interest Registration:** Agents register what they "listen" for:
    ```
    register_thought_interest(
        interest_name="security",
        interest_text="security alerts authentication failures breaches"
    )
    ```
*   **Communication Flow:**
    ```
    Agent A: send_thought_vector("Detected anomaly in auth service")
        → V_thought published to thought bus
    Agent B: Monitors bus, checks similarity(V_thought, V_interests)
        → If resonant (sim > 0.2), processes the thought
    ```

### 17. Genesis Chain Hyper-Spatial Integration
*   **Component:** `GenesisHyperSpatial` (`services/neural_system/bicameral_reflex.py`)
*   **Concept:** "Holographic Verification."
*   **Problem:** How do we verify that executed actions actually achieved the intended outcome?
*   **Solution:** Map Genesis Chain operations to hyperdimensional functions.

#### A. Hyper-Spatial Encoding
*   **Design Intent** ($V_{intent}$): Architect's goal encoded with phase binding.
*   **Plan Steps** ($V_{plan}[]$): Sequence of operation vectors, permuted by index.
*   **Execution State** ($V_{state}$): Current system state.

#### B. Holographic Verification
```
V_intent ← encode(architect_prompt) ⊗ V_architect_phase
V_outcome ← encode(actual_result) ⊗ V_verifier_phase

intent_alignment = similarity(V_outcome, V_intent)
plan_alignment = mean(step_alignments)
overall_score = 0.6 × intent_alignment + 0.4 × plan_alignment

verified = overall_score > 0.3
```

*   **MCP Tools:**
    *   `genesis_hyper_encode_intent`: Encode architect intent for a job.
    *   `genesis_hyper_verify`: Verify job completion against original intent.

### 18. Neo4j ↔ HDC Hybrid Architecture
*   **Component:** `Neo4jHDCBridge` (`services/neural_system/bicameral_reflex.py`)
*   **Question:** "Do we need to move Neo4j to in-memory OCI for HDC?"
*   **Answer:** **NO**—but with a hybrid approach.

#### A. Architecture Decision
*   **Neo4j stays** as the "structural backbone" (relationships, complex graph queries, ACID transactions).
*   **HDC provides** a "semantic overlay" for fast O(1) similarity operations.
*   **The Bridge syncs** key entities between the two spaces.

#### B. Hybrid Data Flow
```
┌─────────────────────────────────────────────────────────────┐
│                     Query Layer                              │
├─────────────────────────────────────────────────────────────┤
│  Semantic Similarity?  │  Graph Traversal?  │  Both?        │
│         ↓              │         ↓          │    ↓          │
│    HDC Space           │     Neo4j          │  Bridge       │
│    (In-Memory)         │   (Persistent)     │  (Sync)       │
└─────────────────────────────────────────────────────────────┘
```

#### C. Entity Synchronization
```python
# Sync Neo4j entity to HDC space
bridge.sync_entity(
    entity_id="service:auth",
    entity_type="Service",
    properties={"name": "auth-service", "port": 8080}
)

# Encode relationship as HDC triple
# V_triple = V_source ⊗ V_rel ⊗ V_target
bridge.sync_relationship(
    source_id="service:auth",
    rel_type="DEPENDS_ON",
    target_id="service:database"
)

# Fast semantic query (O(n) but vectorized)
similar = bridge.query_similar_entities("authentication service", top_k=5)
```

#### D. When to Use Each
| Operation | Use HDC | Use Neo4j |
|-----------|---------|-----------|
| "Find similar services" | ✅ | |
| "Get all dependencies of X" | | ✅ |
| "Does this match concept Y?" | ✅ | |
| "Shortest path between A and B" | | ✅ |
| "Fuzzy entity search" | ✅ | |
| "Transaction-safe updates" | | ✅ |

### 19. Holographic GitOps (System Hash Verification)
*   **Component:** `SystemHash` (`services/neural_system/system_hash.py`)
*   **Concept:** "Codebase as Hypervector."
*   **Mechanism:**
    *   Encodes the entire git-tracked codebase into a single **System Hash Hypervector**.
    *   $V_{repo} = \sum_i (V_{path_i} \otimes V_{hash_i})$
    *   $V_{sys} = V_{repo} + V_{axiom}$ (Axiom = Constitutional constraints)
*   **MCP Tool:** `verify_deployment`
    ```json
    {
        "alignment_score": 0.42,
        "aligned": true,
        "status": "APPROVED",
        "axiom_check": "PASS"
    }
    ```
*   **Use Case:** Before deployment, verify the codebase hasn't drifted from core architectural axioms.

---

## Part 6: OCI Deployment Architecture (Updated)

### 20. Service Topology (OCI Ampere A1)
```
┌─────────────────────────────────────────────────────────────┐
│                    OCI Ampere A1 VM                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ neural_sys  │  │  hse_encoder│  │  mcp_server │         │
│  │  (Physics)  │  │  (Telemetry)│  │   (Tools)   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          ↓                                  │
│               ┌─────────────────────┐                       │
│               │    DragonflyDB      │                       │
│               │  (Hot State Store)  │                       │
│               └─────────────────────┘                       │
│                          ↓                                  │
│               ┌─────────────────────┐                       │
│               │       Neo4j         │                       │
│               │  (Graph Backbone)   │                       │
│               └─────────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### 21. Memory Budget (16GB Constraint)
| Component | Allocation | Notes |
|-----------|------------|-------|
| HDC Engine | ~400MB | 10K-dim vectors, basis cache |
| DragonflyDB | ~2GB | Hot tick frames, thought bus |
| Neo4j | ~4GB | Graph storage, indexes |
| TD-JEPA (Quantized) | ~350MB | Int8 dynamic quantization |
| System Overhead | ~1GB | OS, Docker, networking |
| **Headroom** | ~8GB | For spikes, future growth |

---

---

## Part 7: TickFrame Pipeline & Koopman Dynamics

### 21. TickFrame: Unified State Representation

The TickFrame is the canonical representation of system state at a moment in time, unifying:

```
┌─────────────────────────────────────────────────────────────┐
│                      TickFrame                               │
├─────────────────────────────────────────────────────────────┤
│  HDC State (V_hdc)      │  10,000-dim hypervector           │
│  Quaternion (q)         │  Orientation in semantic space    │
│  Angular Velocity (ω)   │  Rate of semantic rotation        │
│  Energy Terms           │  E_rot, E_hopfield, E_jepa, E_curv│
│  Timestamp              │  Unix timestamp (ms precision)    │
└─────────────────────────────────────────────────────────────┘
```

#### Energy Terms
| Term | Formula | Meaning |
|------|---------|---------|
| E_rot | ½ω² | Rotational kinetic energy (semantic velocity) |
| E_hopfield | -max(sim(V, A_i)) | Alignment to basin attractors |
| E_jepa | prediction_error | Deviation from predicted future |
| E_curvature | mean(α_history) | Manifold curvature (instability) |
| E_total | Σw_i × E_i | Weighted sum (stability metric) |

#### MCP Tools
```python
# Ingest telemetry tick
tickframe_ingest(tick_id="tick_001", observation_text="CPU 85%")

# Validate before handoff
tickframe_preflight(tick_id="tick_001", energy_threshold=2.0)

# Add known-good attractor state
tickframe_add_attractor(name="healthy", text="Normal operation")
```

### 22. Koopman Operator: Linearizing Nonlinear Dynamics

The Koopman operator lifts nonlinear dynamics into a higher-dimensional space where evolution becomes **LINEAR**:

```
State Space (nonlinear):    x_{t+1} = f(x_t)
Lifted Space (linear):      g_{t+1} = K @ g_t
```

where `g = φ(x)` is a lifting function (observables).

#### Benefits
1. **Long-horizon prediction** without recursive error accumulation
2. **Koopman residual energy**: ||K @ g_t - g_{t+1}|| measures deviation
3. **Eigenvalue analysis** reveals system modes and stability
4. **CPU-efficient**: just matrix multiplication (NEON-optimized)

#### Implementation: Extended Dynamic Mode Decomposition (EDMD)
```python
# Lifting functions
rbf:             g_i = exp(-||x - c_i||² / σ²)
polynomial:      g = [x, x², x_i × x_j, ...]
random_fourier:  g = [cos(ωᵀx + b), sin(ωᵀx + b)]

# EDMD fit: K = argmin ||G_y - K @ G_x||²
K = G_y @ G_x^+ (pseudoinverse)
```

#### MCP Tools
```python
# Fit Koopman from history
koopman_fit(lift_type="rbf", n_components=50)

# Predict future state
koopman_predict(steps=5)

# Analyze stability modes
koopman_eigenmodes(top_k=5)
```

### 23. Conformal Prediction: Statistical Validity Gates

Conformal prediction provides **distribution-free coverage guarantees**:

> "With probability ≥ 95%, the true state lies within the predicted bounds."

#### Mechanism
1. **Calibration**: Collect residuals from validation set
2. **Threshold**: Set quantile at (1 - α) for target coverage
3. **Gate**: PASS if residual ≤ threshold, FAIL otherwise

```python
# Statistical guarantee
P(residual ≤ threshold | calibration) ≥ 1 - α
```

#### MCP Tools
```python
# Calibrate from history
conformal_calibrate(target_coverage=0.95)

# Gate predicted vs actual
conformal_gate(predicted=V_pred, actual=V_actual)
# Returns: {"decision": "PASS", "residual": 0.15, "threshold": 0.89}
```

### 24. Integration: The Dynamics Pipeline

```
                    ┌─────────────┐
                    │  Telemetry  │
                    │   Input     │
                    └──────┬──────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   TickFrame Pipeline   │
              │  ┌──────────────────┐  │
              │  │ HDC Encode       │  │
              │  │ Quaternion Proj  │  │
              │  │ Energy Compute   │  │
              │  └──────────────────┘  │
              └────────────┬───────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │   Koopman   │ │  Conformal  │ │  Preflight  │
    │   Predict   │ │    Gate     │ │   Check     │
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Decision   │
                    │  PASS/FAIL  │
                    └─────────────┘
```

---

## Appendix: MCP Tool Reference (Bicameral V2)

| Tool | Description | Category |
|------|-------------|----------|
| `set_reflex_constraint` | Map text to HDC constraint for HSE kernel | Bicameral V2 |
| `list_reflex_constraints` | List all active reflex constraints | Bicameral V2 |
| `remove_reflex_constraint` | Remove a constraint by ID | Bicameral V2 |
| `send_thought_vector` | Send HDC thought for agent communication | LoT |
| `register_thought_interest` | Register interest pattern for thoughts | LoT |
| `genesis_hyper_encode_intent` | Encode architect intent for verification | Genesis Hyper |
| `genesis_hyper_verify` | Verify job completion holographically | Genesis Hyper |
| `verify_deployment` | GitOps verification against axioms | Holographic GitOps |
| `tickframe_ingest` | Ingest telemetry tick, compute state | TickFrame Pipeline |
| `tickframe_preflight` | Validate tick before handoff | TickFrame Pipeline |
| `tickframe_get_latest` | Get most recent TickFrame | TickFrame Pipeline |
| `tickframe_add_attractor` | Add basin attractor for Hopfield energy | TickFrame Pipeline |
| `koopman_fit` | Fit Koopman operator from history | Koopman Operator |
| `koopman_predict` | Predict future HDC state | Koopman Operator |
| `koopman_residual` | Compute prediction residual energy | Koopman Operator |
| `koopman_eigenmodes` | Analyze stability modes | Koopman Operator |
| `conformal_calibrate` | Calibrate conformal predictor | Conformal Prediction |
| `conformal_gate` | Gate decision with coverage guarantee | Conformal Prediction |
| `conformal_stats` | Get calibration statistics | Conformal Prediction |

---

## Part 8: HDC Memory Systems (Phase 6)

The memory system has been expanded with **four dedicated subsystems** inspired by neuroscience and distributed computing, unified by the **Memory Maintainer** agent integration layer.

### 25. Sparse Distributed Memory (Kanerva SDM)
*   **Component:** `SDMMemory` (`services/neural_system/sdm_memory.py`)
*   **Concept:** "Auto-Associative Holographic Storage."
*   **Mechanism:**
    *   **Hard Locations:** 100,000 randomly initialized address vectors
    *   **Activation Radius:** ~451 (Hamming distance) for pattern matching
    *   **Counters:** int16 per location × data dimension for superposition
    *   **Cleanup:** Iterative convergence to nearest stored attractor

```
Address (10K-dim) → Activate nearby locations → Sum counters → Threshold → Data
```

#### MCP Tools
| Tool | Description |
|------|-------------|
| `sdm_write` | Store data at HDC address (auto-stores as attractor) |
| `sdm_read` | Retrieve from nearest stored pattern |
| `sdm_cleanup` | Auto-associative cleanup of noisy/partial patterns |
| `sdm_stats` | Get saturation ratio, stored attractors, location count |

#### Properties
*   **Capacity:** ~0.35 × n_locations patterns before interference
*   **Noise Tolerance:** Recovers patterns from 30-40% corruption
*   **Use Case:** Content-addressable memory, pattern completion, error correction

### 26. HDC Infini-Memory (Compressive Accumulation)
*   **Component:** `HDCInfiniMemory` (`services/neural_system/hdc_infini_memory.py`)
*   **Concept:** "Infinite Context via Temporal Permutation."
*   **Inspired by:** Google's Infini-attention paper (2024)

#### Mechanism
```python
# Each update accumulates with temporal encoding
M_t = decay_rate × M_{t-1} + importance × P^t(content_hv)

# Where P^t is the t-th power of a permutation matrix
# This encodes temporal position into the vector structure
```

#### Key Features
*   **Fixed-Width:** Memory stays at constant dimension regardless of history length
*   **Soft Bundling:** Weighted superposition preserves recent content strength
*   **Position Retrieval:** Can extract approximate content at any temporal position
*   **Decay Rate:** 0.99 default—older content naturally fades

#### MCP Tools
| Tool | Description |
|------|-------------|
| `infini_update` | Add content with importance weight |
| `infini_query` | Get relevance score for query vector |
| `infini_retrieve_position` | Retrieve content at specific temporal position |
| `infini_stats` | Get position, magnitude, update count |

### 27. HDC Long-Term Memory (Episodic Retrieval)
*   **Component:** `HDCLongMemory` (`services/neural_system/hdc_infini_memory.py`)
*   **Concept:** "Similarity-Based Episodic Recall."

#### Mechanism
*   Stores (key_hv, value, timestamp) tuples up to capacity (default 100K)
*   Retrieval via cosine similarity with optional recency weighting
*   FIFO eviction when capacity reached (oldest memories dropped)

```python
# Retrieval score combines similarity and recency
score = similarity + recency_weight × recency_factor
```

#### MCP Tools
| Tool | Description |
|------|-------------|
| `longmem_store` | Store episodic memory with HDC key |
| `longmem_retrieve` | Retrieve top-k memories by similarity (+ recency) |
| `longmem_stats` | Get total memories, capacity, utilization |

### 28. Holographic Accumulator (Multi-Channel)
*   **Component:** `HolographicAccumulator` (`services/neural_system/hdc_infini_memory.py`)
*   **Concept:** "Semantic Channels for Structured Memory."

#### Channels
| Channel | Purpose | Example Content |
|---------|---------|-----------------|
| `content` | Core conversational/task content | User messages, responses |
| `context` | Environmental/situational context | Session state, system status |
| `actions` | Executed operations | Commands run, repairs made |
| `feedback` | User/system feedback | Corrections, ratings |
| `metadata` | Ancillary information | Timestamps, session IDs |

#### Mechanism
*   Each channel maintains its own soft accumulator
*   Importance-weighted accumulation preserves structure
*   **Consolidation:** Flatten all channels into single hard vector for storage

```python
# Query returns per-channel relevance
relevance = {
    "content": cos_sim(query, content_channel),
    "actions": cos_sim(query, actions_channel),
    ...
}

# Consolidation for long-term storage
V_consolidated = weighted_sum([normalize(ch) for ch in channels])
```

#### MCP Tools
| Tool | Description |
|------|-------------|
| `accumulator_add` | Add to specific channel with importance |
| `accumulator_query` | Get per-channel relevance scores |
| `accumulator_consolidate` | Flatten channels into single vector |
| `accumulator_stats` | Get per-channel update counts and norms |

### 29. Modern Hopfield Memory (Attractor Network)
*   **Component:** `HDCHopfieldMemory` (`services/neural_system/hopfield_memory.py`)
*   **Concept:** "Energy-Based Attractor Dynamics."
*   **Theory:** Modern Hopfield networks (Ramsauer et al., 2020)

#### Mechanism
*   Stores patterns as attractors in an energy landscape
*   Retrieval via attention-like update: `softmax(β × query @ patterns.T) @ patterns`
*   **Energy:** Low = near attractor (stable memory), High = unstable region

```python
# Energy function
E(query) = -log(Σ exp(β × query · p_i))

# Update rule (convergent)
query_{t+1} = softmax(β × query_t @ P.T) @ P
```

#### MCP Tools
| Tool | Description |
|------|-------------|
| `hopfield_store` | Store patterns as attractors |
| `hopfield_retrieve` | Content-addressable recall via energy descent |
| `hopfield_energy` | Compute energy (stability metric) |

---

## Part 9: Memory Maintainer (Agent Integration)

### 30. Memory Maintainer: Unified Memory Operations
*   **Component:** `MemoryMaintainer` (`services/neural_system/memory_maintainer.py`)
*   **Concept:** "Single Interface for All Memory Operations."
*   **Purpose:** Provides agents with high-level memory operations without needing to understand individual subsystems.

#### Architecture
```
┌────────────────────────────────────────────────────────────┐
│                      AGENT LAYER                           │
│  Serena, OpsAgent, Observer, etc.                         │
│  → Call memory_sync_event, memory_retrieve                │
└─────────────────────────┬──────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────┐
│                 MEMORY MAINTAINER                          │
│  services/neural_system/memory_maintainer.py              │
│  → MemoryMaintainer class                                 │
│  → Handles routing, strategy, consolidation               │
└─────────────────────────┬──────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────┐
│               LOW-LEVEL MCP TOOLS                          │
│  sdm_*, infini_*, longmem_*, accumulator_*, hopfield_*    │
│  → 17 tools for direct memory system access               │
└────────────────────────────────────────────────────────────┘
```

#### High-Level MCP Tools
| Tool | Description | When to Use |
|------|-------------|-------------|
| `memory_sync_event` | Sync event across all memory systems | After conversation turns, task completions, anomalies |
| `memory_retrieve` | Intelligent cascaded retrieval | Before generating responses (get context) |
| `memory_consolidate` | Run dreaming/consolidation cycle | During idle time, scheduled intervals |
| `memory_health` | Get health status of all systems | Monitoring, diagnostics |

#### Event Types for `memory_sync_event`
| Event Type | Channel | Description |
|------------|---------|-------------|
| `conversation_turn` | content | User/assistant message exchange |
| `conversation_end` | content | Session completed |
| `task_start` | actions | Agent beginning a task |
| `task_complete` | actions | Agent finished a task |
| `user_feedback` | feedback | User provided correction/rating |
| `context_shift` | context | Topic or state change detected |
| `anomaly_detected` | metadata | Observer found an issue |
| `repair_action` | actions | OpsAgent performed a repair |

#### Retrieval Strategies
| Strategy | Behavior | Best For |
|----------|----------|----------|
| `cascaded` | Hopfield → LongMem → Infini → SDM (with early exit) | General retrieval |
| `parallel` | Query all systems simultaneously, merge results | Maximum recall |
| `fastest` | Hopfield only | Known patterns |
| `episodic` | LongMemory only | Conversational context |
| `compressive` | InfiniMemory query | Relevance check |

#### Agent Integration Examples

**Serena (User Interaction):**
```python
# After each conversation turn
await call_tool("memory_sync_event", {
    "event_type": "conversation_turn",
    "content_hv": encode_text_to_hdc(user_msg + response),
    "importance": 1.0,
    "metadata": {"session_id": session_id}
})

# Before generating response
context = await call_tool("memory_retrieve", {
    "query_hv": encode_text_to_hdc(user_query),
    "strategy": "cascaded",
    "top_k": 5
})
```

**OpsAgent (Self-Healing):**
```python
# Record repair action for learning
await call_tool("memory_sync_event", {
    "event_type": "task_complete",
    "content_hv": encode_action_to_hdc(repair_details),
    "importance": 1.5,  # High importance stores as Hopfield attractor
    "metadata": {"service": repaired_service, "success": True}
})
```

**Observer Agent (Metrics):**
```python
# Store anomaly pattern for future detection
await call_tool("hopfield_store", {
    "patterns": [anomaly_signature_hv.tolist()]
})
```

### 31. Memory Maintenance Schedule

#### Scheduled Operations
| Operation | Schedule | Description |
|-----------|----------|-------------|
| Consolidation | Every 30 minutes | Accumulator → Hopfield attractor |
| SDM Health | Every 2 hours | Check saturation, cleanup attractors |
| Pruning | Weekly (Sunday 3 AM) | Apply decay, evict old memories |
| Full Backup | Daily (2 AM) | Checkpoint to persistent storage |

#### Event-Driven Triggers
| Redis Channel | Trigger |
|---------------|---------|
| `arca:session:end` | Conversation completed |
| `arca:task:complete` | Agent task finished |
| `arca:anomaly:detected` | Observer found issue |
| `arca:memory:pressure` | System memory alert |

#### Health Thresholds
| Metric | Alert Threshold | Description |
|--------|-----------------|-------------|
| `sdm_saturation` | > 85% | SDM approaching capacity |
| `infini_magnitude_drop` | > 10% sudden | Memory loss detected |
| `longmem_utilization` | > 90% | LongMemory nearly full |
| `hopfield_pattern_count` | > 1000 | Too many attractors |
| `consolidation_backlog` | > 100 | Pending episodes piling up |

---

## Part 10: Holographic Dreaming (Updated)

### 32. Geometric Dreaming Engine (Sleep Cycle)
*   **Component:** `GeometricDreamingEngine` (`services/conversational_hdc/app/dreaming.py`)
*   **Concept:** "Recursive Manifold Shaping."
*   **Relation:** Works with Memory Maintainer's `memory_consolidate` operation.

#### Sleep Cycle Process
```
1. Consolidation Phase
   └── Process pending episodes from Accumulator
   └── Bake into GeometricMemoryShaper manifold
   └── M_new = M_old + (importance × v ⊗ v)

2. Forgetting Phase
   └── Apply decay_rate (default 0.99)
   └── Weak memories fade, strong persist

3. Attractor Formation
   └── Consolidated vector stored as Hopfield attractor
   └── Enables fast pattern-matching on wake
```

#### Integration with Memory Maintainer
```python
# Memory Maintainer's consolidation triggers dreaming
async def consolidation_cycle():
    # 1. Consolidate Accumulator
    consolidated = await call_tool("accumulator_consolidate", {})
    
    # 2. Store as Hopfield attractor
    await call_tool("hopfield_store", {
        "patterns": [consolidated["consolidated_vector"]]
    })
    
    # 3. Trigger Geometric Dreaming
    await http_post("http://conversational_hdc:8096/dream", {
        "decay_rate": 0.99
    })
```

---

## Appendix B: Memory System MCP Tool Reference

### Low-Level Tools (17 total)

| Tool | Category | Description |
|------|----------|-------------|
| `sdm_write` | SDM | Store data at HDC address |
| `sdm_read` | SDM | Retrieve from SDM |
| `sdm_cleanup` | SDM | Auto-associative cleanup |
| `sdm_stats` | SDM | Get SDM statistics |
| `infini_update` | InfiniMemory | Add to compressive memory |
| `infini_query` | InfiniMemory | Query relevance |
| `infini_retrieve_position` | InfiniMemory | Get content at position |
| `infini_stats` | InfiniMemory | Get accumulation stats |
| `longmem_store` | LongMemory | Store episodic memory |
| `longmem_retrieve` | LongMemory | Similarity-based retrieval |
| `longmem_stats` | LongMemory | Get capacity/utilization |
| `accumulator_add` | Accumulator | Add to channel |
| `accumulator_query` | Accumulator | Query channel relevance |
| `accumulator_consolidate` | Accumulator | Flatten to single vector |
| `accumulator_stats` | Accumulator | Get channel statistics |
| `hopfield_store` | Hopfield | Store patterns as attractors |
| `hopfield_retrieve` | Hopfield | Content-addressable recall |
| `hopfield_energy` | Hopfield | Compute energy (stability) |

### High-Level Tools (4 total)

| Tool | Description |
|------|-------------|
| `memory_sync_event` | Sync event across all memory systems |
| `memory_retrieve` | Intelligent cascaded retrieval |
| `memory_consolidate` | Run dreaming/consolidation cycle |
| `memory_health` | Get health of all memory systems |

---

## Appendix C: File Reference

### Memory System Components
| File | Classes | Purpose |
|------|---------|---------|
| `sdm_memory.py` | `SDMMemory`, `SDMConfig`, `SDMMemoryCompact` | Kanerva's Sparse Distributed Memory |
| `hdc_infini_memory.py` | `HDCInfiniMemory`, `HDCLongMemory`, `HolographicAccumulator` | Infinite, episodic, and multi-channel memory |
| `hopfield_memory.py` | `HDCHopfieldMemory` | Modern Hopfield attractor network |
| `memory_maintainer.py` | `MemoryMaintainer`, `MemoryEvent`, `RetrievalResult` | Agent integration layer |

### Related Skills (MCP)
| Skill | Location | Purpose |
|-------|----------|---------|
| `MEMORY_MAINTAINER_AGENT_SOP.md` | `shared_storage/mcp_skills/` | SOPs for memory maintenance |
| `ARCA_MEMORY_ARCHITECTURE.md` | `shared_storage/mcp_skills/` | Overall memory architecture |

---

*Document Version: 2.1 (Memory Systems Phase 6)*
*Last Updated: January 2026*