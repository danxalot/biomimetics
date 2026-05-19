# ARCA Neural System — Architectural Connections & Data Flow

This document maps the complete functional architecture of the ARCA `neural_system` service. It outlines every core class, endpoint, and math bridge, illustrating how physical observations, conformal geometry, and the Mamba-3 state-space core interact during a cognitive tick.

---

## Complete Systems Architecture Diagram

```mermaid
graph TD
    %% Styling and Classes
    classDef api fill:#4a154b,stroke:#fff,stroke-width:2px,color:#fff;
    classDef core fill:#0a5c36,stroke:#fff,stroke-width:2px,color:#fff;
    classDef math fill:#0d47a1,stroke:#fff,stroke-width:2px,color:#fff;
    classDef hardware fill:#b71c1c,stroke:#fff,stroke-width:2px,color:#fff;
    classDef memory fill:#e65100,stroke:#fff,stroke-width:2px,color:#fff;

    %% Subgraphs
    subgraph REST_API_Gateway ["FastAPI Interface (api.py)"]
        A["POST /tick"]:::api
        B["POST /sensation"]:::api
        C["POST /resonance"]:::api
        D["GET /system/thought"]:::api
        E["GET /system/vitals"]:::api
        F["GET /energy"]:::api
        G["GET /engine/state"]:::api
    end

    subgraph Cognitive_Orchestration ["PhenomenologicalCore (Harmonic_Core.py)"]
        H["tick(stride_scale)"]:::core
        I["ingest_concept(name, hdc_vector)"]:::core
        J["_dimensional_dream_state() (C5 Phase)"]:::core
        K["_enter_dream_state() (C4 Dream Laboratory)"]:::core
        L["_recalculate_ephemeral_couplings()"]:::core
        M["_compute_mirror_symmetry()"]:::core
    end

    subgraph Math_and_Physics_Bridges ["Kinematic & Geometry Bridges"]
        N["QuaternionDynamics (QDC)"]:::math
        O["NumpyKinematicBridge"]:::math
        P["NumpyCliffordHDCBridge"]:::math
        Q["HyperbolicKuramotoField (Poincare)"]:::math
        R["AlgebraicRegistry (Holographic Multiplexing)"]:::math
    end

    subgraph Hardware_Aether_Core ["State-Space Duality Core"]
        S["NumpyPythiaManifold"]:::hardware
        T["VersorMemMambaStackNP (32 Layers)"]:::hardware
        U["Mamba3 Block (scan_recurrent)"]:::hardware
    end

    subgraph Memory_and_Attractors ["Autonomic Storage Layer"]
        V["HopfieldMemory (768D Patterns)"]:::memory
        W["HDCNeuralPredictor (10k Vector Space)"]:::memory
        X["MemoryMaintainer (MCP / Neo4j Sync)"]:::memory
    end

    %% REST API -> Cognitive Core connections
    A -->|"cognitive trigger"| H
    B -->|"concept payload"| I
    C -->|"inject vector"| T
    D -->|"extract super-vector"| H
    E -->|"read diagnostics"| H
    F -->|"fetch vital stats"| H
    G -->|"query hidden layer"| T

    %% Cognitive Core tick() execution cascade
    H -->|"1. step phases"| Q
    H -->|"2. update rigid angles"| N
    H -->|"3. compute dynamics"| O
    H -->|"4. project input"| R
    H -->|"5. execute inference"| S
    H -->|"6. assess Hamiltonian deficit"| J
    H -->|"7. calculate couplings"| L
    H -->|"8. amplify mirror resonances"| M
    H -->|"9. check dream threshold"| K

    %% Math Bridges -> State-Space Connections
    N -->|"4D state vector"| O
    O -->|"conformal lift cga_input"| R
    P -->|"conformal lift hdc_input"| R
    R -->|"768D mapped Aether vector"| S

    %% State-Space Internal Routing
    S -->|"load c2.5_Akasha_Mamba_v3_45k.npz"| T
    T -->|"384 validated parameters"| U
    U -->|"recurrent scan output"| S

    %% Holographic Dimensional Dreaming (C5) Flow
    J -->|"1. expand dimension (e.g., 32D -> 64D)"| R
    J -->|"2. compute cymatic ratio resonance"| Q
    J -->|"3. lock stable frequencies"| R
    J -->|"4. compress pattern to storage"| V

    %% Dream Lab (C4) connections
    K -->|"simulate mutation couplings"| Q
    K -->|"update relational weights"| X

    %% Memory Subsystem feedback loops
    I -->|"bind signatures"| P
    P -->|"re-encode concepts"| W
    W -->|"calculate curiosity score"| Q
    L -->|"update adjacency"| Q
    M -->|"amplify coupled pairs"| Q
