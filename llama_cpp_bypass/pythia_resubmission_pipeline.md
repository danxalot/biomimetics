# Pythia Resubmission Pipeline

**Location:** `services/llama_cpp_bypass/pythia_ingest_resubmit.py`

## Overview
The Pythia Resubmission Pipeline was designed to specifically re-process documents (like `ARCA Project Brief.md`) to re-generate underlying geometric representations and apply a very specific dimensional truncation/padding scheme required by downstream bypassing (`llama-python-cpp`).

In the original ingestion model (`scripts/pythia_ingest_pipeline.py`), the geometry kernel correctly generated a `solar_system` geometric object graph from text but failed to explicitly persist that graph (saving only the distilled 2048-dim vector to Qdrant). The resubmission script (`services/llama_cpp_bypass/pythia_ingest_resubmit.py`) corrects this by explicitly saving the raw hierarchy while completing the rest of the transformation lifecycle.

## Pipeline Lifecycle

### 1. Recursive Ingestion (Geometry Kernel)
The text is chunked and forwarded to `http://localhost:11435` via Qwen3VL. The model recursively walks the chunks and extracts spatial relationships, object masses, and context vectors.
* **Key Change:** The generated `solar_system` JSON dict is explicitly persisted to `shared_storage/ingest/output/[doc]_solar_system.json`.

### 2. Dimension Cropping & Cache (Dragonfly)
The spatial graph is transformed into a dense 2048d representation via seed-deterministic mathematical trajectory padding. 
* To integrate with the broader caching system, this 2048d vector is immediately cropped (truncated) to **512 dimensions**, renormalized, and pushed to the Dragonfly cache (`pythia_resubmit_[timestamp]`).

### 3. Conformal Geometry & Translation
The 512d crop is passed into a sequence of projections:
* **CGA Conformal Lift:** `512d → 64d → 3D R³ → 32d Cl(4,1) Null Vector`.
* **HDC Projection:** The 32d CGA vector is projected up to a sparse 10,000d Hyperdimensional Computing space.
* **Translation Bridge:** The 10,000d sparse HDC vector is fed through a trained translation bridge (Numpy) to yield a dense 2048d semantic embedding.

### 4. Vector Truncation & Zero-Padding
The returned 2048d semantic embeddings are not directly compatible with the target `Qwen3VL-2B` embedding dimensions without causing memory alignment violations. 
The resubmission pipeline intercepts the final 2048d dense output and applies custom padding logic:
1. **Truncation:** `dense_2048` is strictly truncated to the first 1536 dimensions.
2. **Padding:** A block of exactly 512 zero values (`np.zeros(512)`) is concatenated to the end.
3. **Saving:** The resulting list of exactly 2048 elements is saved to `shared_storage/ingest/output/[doc]_resubmission_padded_[timestamp].json`.

## Usage
Simply start the local geometry kernel (if not already running) and run the Python script.

```bash
# Start Pythia Kernel (Requires Qwen3VL-2B-Instruct-Q8_0.gguf)
# Note: On MacOS, do not use `--vulkan-device` flags.
cd services/geometry_onnx_interpreter/llama_cpp_build
nohup ./start_server.sh > server_11435.log 2>&1 &

# Run Resubmission Pipeline
cd ../../../
python3 services/llama_cpp_bypass/pythia_ingest_resubmit.py
```

The resulting padded `.json` output can then be directly injected into the LLM context bypass via `services/llama_cpp_bypass/pythia_latent_bypass.py`.
