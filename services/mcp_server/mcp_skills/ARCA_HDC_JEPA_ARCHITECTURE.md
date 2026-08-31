---
skill_name: ARCA HDC-JEPA Architecture
version: 1.0.0
category: cognitive_architecture
status: design
dependencies:
  - geometry_kernel
  - hse_encoder
  - faiss
  - redis (dragonfly)
  - oracle_23ai (OCI)
compute_locations:
  macbook: [aflash_encoder, siglip, qwen_embedding, geometry_kernel, vae]
  oci_arm: [faiss_reasoning_bank, vjepa_physics, oracle_skill_bank]
  modal: [vjepa_training]
  kaggle: [exploration_notebooks]
---

# ARCA HDC-JEPA Architecture

## Overview

Implements "Think in Analog (HRR), Act in Digital (HDR)" for ARCA's cognitive layer.

## Architecture: MacBook Brain + OCI Reflex

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MacBook (Brain)                              │
│  ┌─────────────┐  ┌───────────────┐  ┌──────────────┐              │
│  │   SigLIP    │→│  A-FLASH      │→│  Geometry    │              │
│  │ Qwen Embed  │  │  Encoder      │  │  Kernel      │              │
│  └─────────────┘  │  (HRR→HDR)    │  └──────────────┘              │
│                   └───────────────┘          ↓                      │
│                          ↓            ┌──────────────┐              │
│                   ┌──────────────┐    │ DragonflyDB  │              │
│                   │ Curiosity +  │←──│ Blackboard   │              │
│                   │ Kuramoto     │    └──────────────┘              │
│                   └──────────────┘                                  │
│                          ↓  (HDR vectors)                           │
└──────────────────────────│──────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        OCI ARM (Reflex)                             │
│  ┌────────────────┐     ┌───────────────┐     ┌────────────────┐   │
│  │ FAISS Binary   │←───│ V-JEPA        │←───│ Oracle 26ai    │   │
│  │ Reasoning Bank │     │ Physics Model │     │ Skill/Graph    │   │
│  └────────────────┘     └───────────────┘     └────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### Phase 1: Core Data (MacBook)

| Component | File | Purpose |
|-----------|------|---------|
| ConceptMonad | `concept_monad.py` | Universal concept representation |
| A-FLASH Encoder | `aflash_encoder.py` | Learnable HDC projection with STE |
| Kuramoto Field | `kuramoto_field.py` | Phase-locking dynamics |
| Curiosity Engine | `curiosity_engine.py` | Fisher Information gradient |

### Phase 2: V-JEPA Interface (MacBook→OCI)

| Component | File | Purpose |
|-----------|------|---------|
| HDC-VJEPA Bridge | `hdc_vjepa_interface.py` | Project HDC→JEPA latent space |
| SerenaHDCBrain | `serena_hdc_brain.py` | Reflex + Deliberate control loop |

### Phase 3: Reasoning Bank (OCI)

| Component | Location | Purpose |
|-----------|----------|---------|
| FAISS Binary Index | OCI ARM RAM | Instant skill lookup (<1ms) |
| Oracle Skill Bank | Oracle 26ai | Persistent skill storage (VECTOR type) |
| Property Graph | Oracle 26ai | Concept relationships |

## Key Algorithms

### HRR→HDR Quantization
```python
def quantize(hrr_vector: torch.Tensor) -> np.ndarray:
    binary = (hrr_vector > 0).type(torch.uint8)
    return np.packbits(binary.numpy())  # 10000 bits → 1250 bytes
```

### Straight-Through Estimator (STE)
Enables backprop through binary sign():
```python
class BinarySign(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x): return torch.sign(x)
    @staticmethod  
    def backward(ctx, grad): return grad.clamp(-1, 1)
```

### Energy = Geometric Tension
```python
energy = hamming_distance(current_vec, attractor_vec) / dim
# Low energy = coherent state = healthy system
# High energy = orthogonal to attractors = crisis
```

## Oracle 26ai Schema

### Skill Bank
```sql
CREATE TABLE skill_bank (
    skill_id RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    concept_name VARCHAR2(128),
    state_vector VECTOR(1024, INT8),
    logic_payload CLOB
);
```

### Concept Graph
```sql
CREATE TABLE concept_edges (
    edge_id NUMBER GENERATED ALWAYS AS IDENTITY,
    source_skill_id RAW(16),
    target_skill_id RAW(16),
    relation_type VARCHAR2(50),
    weight NUMBER
);
```

## Related Skills

- `ARCA_GEOMETRY_KERNEL_PHASE2` - Document ingestion
- `ARCA_INVERSE_ATTENTION_SYSTEM` - Topic accumulation
- `ARCA_COGNITIVE_TICK_ARCHITECTURE` - Tick scheduling

## Resource Allocation

| Resource | Local (MacBook) | OCI Free Tier |
|----------|-----------------|---------------|
| RAM | 16GB | 24GB (4xA1) |
| Storage | SSD | 47GB boot + 40GB DB |
| GPU | MPS | N/A (ARM NEON) |
| Vector DB | DragonflyDB | FAISS + Oracle 26ai |
