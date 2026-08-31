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

---
**Dependencies:** Redis (Attractors), Dragonfly (Metrics), FastAPI (API), Numba (JIT), Three.js (UI).
