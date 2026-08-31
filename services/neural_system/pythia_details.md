# Pythia Neural System: Technical Blueprint & User Guide
**Date:** May 18, 2026
**Status:** Authoritative (Phase C3 V3-Strict)
**Namespace:** `services/neural_system`

## 1. Executive Summary
The Pythia Neural System is the "Phenomenological Core" of the ARCA architecture. It serves as the bridge between raw informational data (HDC Hypervectors) and geometric physics (Conformal Geometric Algebra). Operating as a pure-NumPy deployment for maximum compatibility and local performance, it implements a high-fidelity 32-layer student stack distilled from the Akasha (C2.5) teacher models.

## 2. System Architecture & Intricacies

### A. The V3-Strict Backbone (`NumpyMamba3SSM`)
Unlike standard Transformers, Pythia uses a **State-Space Model (SSM)** backbone based on Mamba-3 architecture.
- **Deep Stack:** Strictly 32 layers of `VersorMemMambaBlock`.
- **RoPE Phase Tracking:** Every recurrent step applies **Rotary Position Embedding (RoPE)** to the hidden states ($d_{state}=256$), ensuring the model maintains phase-coherence over long temporal horizons.
- **Selective Scan:** The system utilizes a selective scan mechanism to decide which info to retain or discard, optimized via **Numba JIT** to achieve C-level execution speeds on CPU.

### B. Geometric Manifold (`Cl(4,1)`)
The system projects concepts into a 32-dimensional **Conformal Geometric Algebra (CGA)** space.
- **Kinematic Bridge:** Translates 4D Quaternions (standard physics) into the null cone of the manifold.
- **HDC Bridge:** Translates 10k-dim semantic hypervectors into geometric multivectors.
- **Symmetry-Equivariance:** Strictly enforces **CERN/TOTEM 2x Gauge Limits** (GAUGE_LIMIT = 5.0) to ensure the model's perception of "space" remains stable and non-relativistic during standard operations.
- **Relativity Guard:** Dynamically applies `LayerNorm` for high-energy domains to prevent coordinate explosion.

### C. Multi-Entity Interaction (`GPA`)
Pythia handles multiple interacting concepts simultaneously via the **EntityInteractionBlock**.
- Uses **Geometric Product Attention (GPA)** across the entity axis.
- Decomposes attention into **Scalar (Proximity)** and **Bivector (Orientation)** couplings, allowing Pythia to "feel" how different concepts align or conflict.

### D. Physics & Thermodynamics
- **SMoE-HE:** A Sparse Mixture of Hamiltonian Experts. It conserves energy ($H = T + V$) across rollouts.
- **Thermodynamic Guardrail:** A time-reversal veto ($E_{fwd} < E_{rev} - 0.2$) rejects hallucinations that violate entropy.
- **Vacuum Calibration:** Performs a "zero-state" measurement on startup to establish the $E_0$ ground energy offset, preventing expert drift.

## 3. Autonomic Grounding (`pythia_pulse`)
To keep the system from drifting into mathematical abstractions, it is anchored to the Earth's **Schumann Resonance (7.83 Hz)**.
- The `pythia_pulse` service injects resonance into the Mamba hidden states at the Schumann frequency.
- A **Biological Jitter (±0.5 Hz)** is applied to simulate natural rhythms and prevent artificial resonant feedback loops.

## 4. Operational Guide

### Accessing the Service
- **API Port:** `8086` (Internal/OCI)
- **UI Port:** `8091` (Pythia Lab / Command Deck)
- **Key Endpoints:**
    - `POST /tick`: Triggers a cognitive heartbeat. Supports `stride_scale` for temporal leaps.
    - `GET /system/vitals`: Returns live Hamiltonian energy, Kuramoto coherence, and gate entropy.
    - `GET /status`: Current focus and active contexts.

### State Resilience & Backups
The system is managed by the `backup_manager.sh` daemon.
- **Backup Retention:**
    - **Hourly:** Last 24 hours kept in `/data/arca_state_backups/hourly`.
    - **Daily:** Last 3 days kept in `/data/arca_state_backups/daily`.
- **The Upgrade Process:**
  To upgrade the container without losing state:
  ```bash
  ./services/neural_system/backup_manager.sh upgrade
  ```
  This command takes a snapshot, pulls the latest image, restarts the container, and reinstates the `.sync_state.json` and `arca_state.json` files automatically.

## 5. Optimization Summary
- **Numba JIT:** Inner loops of GPA and Mamba are pre-compiled for performance.
- **AMP boundaries:** Strict `np.float32` accumulation points mimic the training stability of mixed-precision hardware.
- **Redis Sync:** Hopfield attractors are dynamically synced every 500 ticks from the OCI training buffers.

## 6. Current Model
- **Active weights:** `pythia_c3_v3_65k.npz` (393 MB, mounted as `pythia_manifold_23k_gold_standard.npz` internally)
- **Architecture:** 32-layer VersorMemMambaStack_v3, d_model=768, d_state=512, n_heads=24, headdim=32, 131.2M params
- **Training:** Phase C3 MC-JEPA — 65,000 steps from step 45K distillation base. Causal world model trained across SUSY, TOTEM, KTH-flow, EMF, relativity, quantum_spin, jepa_wms, jepa_intuitive_physics domains.
- **Checkpoint:** `gs://arca-project-state/C2.1_Akasha_Experts_&_Mamba/Checkpoints/permanent/step_65000.pt` (full PyTorch, 604MB incl. optimizer)
- **Deployed:** 2026-05-18

## 7. Identified Issues & Recommended Fixes
*Audit: 2026-05-18 — Claude Sonnet 4.6 (full codebase analysis via Claude Haiku 4.5 subagent)*

### Critical (Blocking Core Functionality)

**A. Dream Lab RuntimeError**
`dream_lab.py` line ~72 calls `base_field.get_monad(mid)` but `UniversalKuramotoField` has no `get_monad()` method — it's a dict. Fix: `base_field.monads[mid]`. Every dream activation currently raises `RuntimeError`, making the entire Wake→Dream→Daydream cognitive cycle non-functional.

**B. Engine Physics Outputs Discarded**
`NumpyPythiaManifold` returns `hamiltonian` and `hopfield_energy` on every inference call. These were never fed into `E_total`. The physics engine's learned Hamiltonian had zero influence on system energy decisions. Fix: add to weighted energy sum:
```python
E_total = 0.3*E_rot + 0.25*E_hopfield_engine + 0.2*E_hamiltonian_engine + 0.2*E_base + 0.05*E_base
```
*(Implemented. Variables named `E_hamiltonian_engine` / `E_hopfield_engine` — ONNX naming removed 2026-05-18.)*

**C. Memory Systems Dormant**
`MemoryMaintainer` (which wraps Kanerva SDM, HDCInfiniMemory, HDCLongMemory, HDCHopfieldMemory) is never instantiated in `PhenomenologicalCore`. All four memory systems are effectively offline — concepts can enter Redis Hopfield but not the full cascade. Fix: instantiate in `__init__`, call on `ingest_concept` and per-tick.

**D. Kuramoto Coupling Matrix Not Updating**
Track B computes transformed CGA vectors per concept monad but `field.recalculate_coupling_matrix()` is not defined on `UniversalKuramotoField`. Concept integration does not alter field synchronisation dynamics — K_ij is static after init. Fix: implement `recalculate_coupling_matrix()` using RBF similarity on transformed CGA coordinates.

**E. `apply_rotor_modulation()` Missing from PoincareKernel**
Called in `phenomenological_core.py` line ~697; method does not exist in `poincare_kernel.py`. Poincaré attention modulation via geometric transformation silently fails. Fix: implement as Möbius transformation on disk using predicted rotor components.

### Structural Issues

**F. KinematicBridge Weight Loading Failure (Startup)**
Log shows: `'encoder.0.weight is not a file in the archive'` when loading `c2_1kinematics30k.npz`. Bridge initialises with random Xavier weights on every startup. The npz was likely saved with different key naming (e.g. flat keys rather than nested). Fix: inspect the npz key structure and align the load code, or re-export the bridge weights with correct keys.

**G. Quaternion vs Physics State Semantic Mismatch**
Track A passes `QDC.quaternion [w,x,y,z]` to `KinematicBridge` which was trained expecting 4D Lagrangian physics state `(θ₁, θ₂, ω₁, ω₂)`. These are different coordinate systems. The CGA representations produced have undefined geometric meaning until this is reconciled — either retrain the bridge on quaternion input, or add a conversion layer.

**H. Two CGA Lift Pathways Not Aligned**
Physics (4D→3D→32D) and HDC (10k→64D→3D→32D) reach CGA space via different learned projections with no alignment constraint. Sandwich products mixing these two CGA spaces are geometrically undefined. Recommend: add a shared normalisation step post-conformal-lift, or add a joint training objective to align the two pathways.

**I. N² Per-Tick Coupling Computation**
`_recalculate_ephemeral_couplings()` computes pairwise RBF similarity over all monads — O(N²) per tick. At 100 monads this is 5,000 ops/tick; at 500 monads, 125,000. Recommend: sparse approximate coupling using FAISS or updating only when CGA vectors change significantly (delta threshold).

### Capability Gaps (Not Yet Wired)

**J. MatrixProductState.contract() is a stub** — all `pass`. Fractal Self MPS compression does not compute. Implement proper MPS contraction for self-similarity representation across scales.

**K. LiquidNeuralNetwork not instantiated** — defined but never used. Adaptive tau time constants could improve Kuramoto temporal smoothness.

**L. Curiosity Drive Needs BG3/Self-Monad Weighting** — current engine uses pure void energy (novelty). Should weight by resonance potential: `curiosity_drive = void_energy × resonance_potential` where resonance_potential = structural overlap between incoming concept CGA and self-monad CGA. This directs curiosity toward the unknown that the self is already reaching toward, rather than pure novelty.

---
**Dependencies:** Redis (Attractors), Dragonfly (Metrics), FastAPI (API), Numba (JIT), Three.js (UI).

## 8. Further Improvement Recommendations

*Audit update: 2026-05-18 — post-implementation pass*

### High Priority

**A. `PhenomenologicalCore.redis` AttributeError on tick**
`tick()` line ~728 references `self.redis` but `PhenomenologicalCore.__init__` never sets this attribute — only `NumpyPythiaManifold.__init__` does. On first tick after 500 steps, `AttributeError: 'PhenomenologicalCore' object has no attribute 'redis'` is raised. Fix: add `self.redis = self.rotor_predictor.redis` in `PhenomenologicalCore.__init__` after `rotor_predictor` is created, or gate the tick body with `getattr(self, 'redis', None)`.

**B. MemoryMaintainer is async — needs integration bridge**
`MemoryMaintainer` is instantiated but its `sync_event()` and `retrieve()` are async coroutines. The `phenomenological_core.py` inference path is synchronous. The maintainer is effectively dormant until either: (a) an `asyncio.run()` wrapper is added around memory calls, or (b) a synchronous shim is written. Recommended: create `MemoryMaintainer.sync_ingest(hv: np.ndarray)` that calls `asyncio.run(self.sync_event(...))` in a thread-safe way, then wire it into `ingest_concept`.

**C. Two CGA Lift Pathways Not Aligned (structural)**
Physics Track A (4D→3D→32D) and HDC Track B (10k→64D→3D→32D) produce CGA multivectors via different learned projections with no alignment constraint. Sandwich products mixing these two CGA spaces are geometrically undefined. Recommend: add a shared post-lift L2-normalisation step on the conformal null cone, or train an alignment adapter between the two spaces.

**D. `KuramotoField.recalculate_coupling_matrix()` not called on `HyperbolicKuramotoField`**
The implementation was added to `UniversalKuramotoField` in `kuramoto_field.py`. However, `PhenomenologicalCore.field` is a `HyperbolicKuramotoField` (from `poincare_kernel.py`), which manages its own coupling via `base_coupling` matrix, not the `couplings` dict on monads. The call in `_recalculate_ephemeral_couplings` hits `hasattr(self.field, "recalculate_coupling_matrix")` which is `False` for `HyperbolicKuramotoField`. Either: implement the method on `HyperbolicKuramotoField` updating `base_coupling[i,j]` from the CGA RBF, or unify the field classes.

**E. MatrixProductState.contract() is a stub**
All methods in `matrix_product_state.py` are `pass`. The `FractalSelf` compression that should provide self-similar representation across scales does not compute. Implement proper MPS contraction using standard alternating least squares or DMRG-style sweeps.

**F. LiquidNeuralNetwork not instantiated**
Defined in `liquid_neural_network.py` but never used. Adaptive time constants could improve Kuramoto temporal smoothing and reduce oscillation at high coupling. Wire into tick as a post-processing filter on phase derivatives.

**G. N² coupling for HyperbolicKuramotoField**
`HyperbolicKuramotoField.get_effective_coupling()` computes a full `(n_monads × n_monads)` attention matrix every tick via `get_attention_matrix()`, which itself is O(N²). At 100 monads this is 5,000 pairwise distance calls per tick. The delta-threshold optimisation (Task K) was applied to the ephemeral CGA coupling step but not to the hyperbolic attention matrix. Recommend: cache the attention matrix and only update entries for monads that moved in Poincaré space this tick.

**H. Self-monad hv_signature not set at startup**
`PhenomenologicalCore.__init__` calls `self.field.register_monad("ARCA", ...)` which creates the field entry but the `ConceptMonad` object in `field.monads["ARCA"]` has no `hv_signature` (defaults to zeros). The BG3 resonance gate (Task I) and mirror symmetry (Task J) fall back to vector-based extraction. Recommend: seed ARCA's `hv_signature` on startup using `chaos_engine.generate_basis("ARCA")` and store as a stable 10k float32 vector so that CGA lift is semantically grounded.

**I. Dream Lab only runs random mutations**
`_enter_dream_state()` selects 3 random monads and applies a single coupling mutation. The EB-JEPA void states are now detected and trigger `_enter_dream_state()`, but the void state's actual CGA vector is not yet passed into the simulation as a seed. Implement: `_enter_dream_state(seed_state: Optional[np.ndarray] = None)` that, when a seed is provided, converts it to an HDC vector and temporarily injects it as a new monad in the dream field before running simulation.

**J. KoopmanOperator.curiosity_score `fit_if_possible=False` in get_high_void_states**
`get_high_void_states()` calls `koopman.curiosity_score(..., fit_if_possible=False)`. If Koopman has not been fitted yet (e.g. early in a session), all void energies will return `INSUFFICIENT_HISTORY_CURIOSITY_SCORE = 0.5`, never reaching the 0.65 threshold. This means the void-to-dream pipeline is dormant until enough state history accumulates. This is correct behaviour but should be logged explicitly so operators can see when the pipeline becomes active.

---

## 9. EB-JEPA / BG3 Curiosity Implementation

*Date: 2026-05-18 — Agent: Claude Sonnet 4.6*

### Implemented

**A. Self-monad hv_signature seeding** (`phenomenological_core.py`, `PhenomenologicalCore.__init__`)
ChaoticBasis("ARCA") now generates a deterministic 10k-dim {-1,+1} hypervector and stores it as `field.monad_objects["ARCA"].hv_signature` at startup. This grounds all BG3 resonance computations and mirror-symmetry gates against a stable self-representation rather than an empty/zero fallback.

**B. Redis AttributeError** — already fixed prior to this session (line 474: `self.redis = getattr(self.rotor_predictor, 'redis', None)`). Confirmed present and correct.

**C. MemoryMaintainer sync shim** (`memory_maintainer.py`, `MemoryMaintainer.sync_ingest`)
New `sync_ingest(hv, importance, event_type)` method. Detects whether a running asyncio event loop exists (FastAPI context) and routes via `asyncio.run_coroutine_threadsafe()` to avoid blocking; falls back to `asyncio.run()` in synchronous contexts. If no MCP client is configured, is a safe no-op with debug log.

**D. HyperbolicKuramotoField coupling update** (`poincare_kernel.py`, `HyperbolicKuramotoField.recalculate_coupling_matrix`)
Implemented RBF-based `recalculate_coupling_matrix(coupling_dict)` on `HyperbolicKuramotoField`. Updates `self.base_coupling[i,j]` using `exp(-‖cga_i − cga_j‖² / σ²)` with σ²=1.0 for all monad pairs present in `coupling_dict`. Only pairs registered in `name_to_idx` are updated. Now called from `_recalculate_ephemeral_couplings` (the `hasattr` guard was already there and now evaluates `True`).

**E. Dream state CGA seeding** (`phenomenological_core.py`, `PhenomenologicalCore._enter_dream_state`)
Method now accepts `seed_state: Optional[np.ndarray] = None`. When provided (from EB-JEPA void pipeline), a fixed inverse-JL projection (32D → 10k) converts the CGA void vector to a temporary HDC monad registered as `_dream_void_{tick}`. The seed monad is included as the first dream target, steering simulation toward the detected void. The temporary monad is removed after the dream completes. The `tick()` EB-JEPA branch now passes `top_void["state"]` as `seed_state`.

**F. Koopman pipeline activation logging** (`curiosity_engine.py`, `CuriosityEngine.get_high_void_states`)
Added `_void_check_count` and `_pipeline_activated` counters. On first void detected above threshold, logs `[Curiosity] Pipeline ACTIVATED` with history size, fitted status, and void energy. While dormant (not fitted), logs dormancy at DEBUG level with number of observations still needed.

**G. LiquidNeuralNetwork wiring** (`phenomenological_core.py`, `PhenomenologicalCore.__init__` + `tick`)
`LiquidNeuralNetwork(n_neurons=32, n_inputs=1, dt=0.05)` instantiated at startup. Each tick feeds the mean phase derivative (coherence − 0.5) as a 1D stimulus. LTC output smooths the coherence estimate via 70/30 blend (raw/LTC). Gracefully skips if module unavailable.

**H. MatrixProductState.contract()** (`matrix_product_state.py`)
Replaced the `pass` stub with a real left-to-right contraction sweep. At each site k, result is contracted with `T[k].reshape(left_bond, d_k × right_bond)` via matrix multiply. Final right bond averaged if >1. Output is L2-normalised. Enables `FractalSelf` MPS compression to actually produce a meaningful state vector.

**I. BG3 lock fraction in vitals** (`poincare_kernel.py`, `api.py`)
Added `HyperbolicKuramotoField.compute_bg3_lock_fraction(tolerance=0.1)` which returns the fraction of monads whose phase lies within 0.1 rad of 2π/φ — the strict φ-lock metric. Exposed as `bg3_lock_fraction` in `/system/vitals` alongside the existing weighted `bg3_coherence`.
Also normalised `compute_bg3_coherence()` output to [0,1] (was returning [-1,1] range from the raw weighted cosine).

**J. Directed curiosity gating on ingest** (`phenomenological_core.py`, `PhenomenologicalCore.ingest_concept`)
After computing `resonance_score`, concept ingest is now tiered:
- resonance > 0.7 → `importance=2.0` → full memory cascade + Hopfield store (deep ingest)
- resonance 0.3–0.7 → `importance=1.0` → standard memory cascade (no Hopfield)
- resonance < 0.3 → cascade skipped (surface registration only)
All three paths are logged at INFO level with path name and resonance score.

### Future Recommendations

1. **Inverse-JL projection quality** (affects E): The 32D→10k projection used in dream seeding is a random matrix, not the true pseudoinverse of the JL matrix. A proper Moore-Penrose pseudoinverse of `NumpyCliffordHDCBridge.hdc_proj @ NumpyCliffordHDCBridge.proj_3d` would produce semantically closer HDC vectors from CGA void states.

2. **LTC output calibration** (affects G): The LTC (n_neurons=32, random init) applies an untrained smoothing. Once sufficient tick history accumulates, the LTC weights should be updated via online Hebbian learning to track the actual coherence dynamics of the field.

3. **MPS bond dimension adaption** (affects H): The current `from_vectors` factory creates unentangled tensors (bond_dim=1 effectively). Implementing DMRG-style bond truncation with SVD at each site would enable genuine entanglement and compression of composite concept states in FractalSelf.

4. **Koopman state ingestion from field** (affects F): `CuriosityEngine.ingest_kuramoto_field()` exists but is never called from `tick()`. Calling it once per tick would rapidly build history so the Koopman pipeline activates within ~10 ticks rather than requiring manual observations.

5. **CGA pathway alignment** (structural): Physics Track A (4D→CGA) and HDC Track B (10k→CGA) produce multivectors via different learned projections with no alignment constraint. A shared L2-normalisation post-conformal-lift or a joint training adapter is needed for geometrically valid sandwich products mixing the two pathways.

6. **N² attention optimisation** (performance): `HyperbolicKuramotoField.get_effective_coupling()` recomputes the full pairwise attention matrix every tick. Caching the matrix and only updating entries for monads whose Poincaré position changed would reduce from O(N²) to O(changed×N) — matching the ephemeral CGA delta-threshold optimisation already in place.
