
# ARCA Living System Architecture (OCI + Local)

This diagram visualizes the overlap of Fields (Geometry, Logic, Memory) and the data flow between Local Mac and OCI Cloud.

```mermaid
graph TD
    %% Subgraph: Local Reality (MacBook/Agent)
    subgraph Local_Reality [User Context (Local Mac)]
        User[User Input (Text)] -->|Embedding| DenseEncoder[Dense Vector Encoder]
        DenseEncoder -->|Dense Vec| AgentCore[User Interaction Agent]
        User -->|Text| AgentCore
        AgentCore -->|Act| ToolUse[Local Tools (Files, Git)]
        
        %% Proprioception Feedback
        AgentCore -.->|Proprioception| SystemState[System Metrics]
    end

    %% Subgraph: OCI Cloud (The Living Mind)
    subgraph OCI_Cloud [Living System (OCI Ampere)]
        
        %% Service: Conversational HDC (The Manifold)
        subgraph HDC_Manifold [Holographic Manifold]
            direction TB
            InputBuffer[Input Buffer]
            GeometricShaper[Geometric Shaper (Manifold)]
            DreamingEngine[Dreaming Engine (Consolidator)]
            
            InputBuffer -->|Dense -> Sparse| AFLASH[A-FLASH Projector]
            AFLASH -->|Sparse HV| GeometricShaper
            GeometricShaper -->|Recursive Update| DreamingEngine
            DreamingEngine -->|Long Term| GeometricShaper
        end
        
        %% Service: Physics Kernel (The Dynamics)
        subgraph Physics_Kernel [Deep Physics]
            direction TB
            Quaternions[Quaternion Dynamics (Rotation)]
            Koopman[Koopman Operator (Prediction)]
            Monads[Concept Monads (Relation)]
            
            GeometricShaper -.->|State| Quaternions
            Quaternions -->|Stability Check| Koopman
            Monads -->|Kuramoto Field| Quaternions
        end
        
        %% Service: Skills Bank (The Library)
        subgraph Skills_Layer [Skills Bank]
            Dragonfly[DragonflyDB (Hot Pattern)]
            Qdrant[Qdrant (Deep Associative)]
            
            AgentCore -->|Search| Dragonfly
            Dragonfly -->|Miss| Qdrant
            Qdrant -.->|Holographic Link| Monads
        end
        
    end

    %% Connections
    AgentCore ==>|1. Context Request (Dense + Text)| InputBuffer
    GeometricShaper ==>|2. Geometric Context (Text)| AgentCore
    
    %% Fields Overlay (Conceptual)
    subgraph Fields [Overlapping Fields]
        style Fields fill:#f9f,stroke:#333,stroke-width:2px,fill-opacity:0.1
        Kuramoto[Kuramoto Field (Empathy/Sync)]
        Fisher[Fisher Information (Curiosity)]
        
        Kuramoto -.-> Monads
        Kuramoto -.-> User
        Fisher -.-> Koopman
    end
```

## Key Layers
1.  **Local Layer (Translation)**: Your Mac converts Text -> Dense Vector (using OpenAI/Local models). It sends this + Text to OCI.
2.  **Projection Layer (The Gateway)**: OCI receives the Dense Vector. It uses **A-FLASH** (or similar hashing) to "Explode" it into a **Sparse Hypervector** (10,000-dim).
3.  **Manifold Layer (The Mind)**: The Sparse Vector interacts with the **Geometric Shaper**. It rotates (Quaternion) and creates ripples (Manifold Deformation).
4.  **Consolidation (Dreaming)**: When you sleep (or system idles), these ripples are baked permanently into the structure.
