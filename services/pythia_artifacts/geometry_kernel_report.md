# Geometry Kernel Recursive Ingestion Issue Report

## Problem Statement
The `recursive_ingestion.py` function works correctly in `geometry_heavy_lifter.py` but fails when invoked via the Geometry Kernel's cognitive tick (using Gemini Flash). The failure is not due to model call routing (e.g., gateway/quota issues) but stems from **output parsing mismatches** and **state management differences** between the two implementations.

## Core Issues Identified

### 1. Prompt-Output Schema Mismatch
- **Geometry Kernel**: Uses verbose prompts requesting `vector`, `summary`, and `objects` with `desc` fields.
- **Gemini Flash**: Often returns extra explanatory text before/after JSON, or omits `summary` field, causing JSON extraction to fail.
- **Heavy Lifter**: Uses a simpler prompt (see `modal_apps/geometry_heavy_lifter.py`) that requests only `vector` and `objects` with `mass` and `position`, matching the parser's expectations.

### 2. State Update Assumptions
- **RecursiveIngestion._update_state()** assumes:
  - `vector` is a list of 3 floats.
  - `objects` is a list of dicts with `id`, `mass`, `position`.
  - Optional `summary` for `current_context`.
- Gemini Flash output frequently:
  - Includes `desc` but omits `mass`/`position` or uses different keys.
  - Returns nested structures or additional fields not handled by the normalizer.

### 3. Missing Artifact Extraction Integration
- The kernel calls `extract_clever_artifacts` only after processing all chunks (line 350-366), but:
  - It passes `model_for_artifacts` built from the final `state["objects"]` only.
  - The extractor expects a full geometric model with `trajectory_vector`; the kernel provides it, but the extractor may need per-chunk artifact accumulation for consistency with the heavy lifter.

### 4. Trajectory Vector Scaling
- The kernel applies magnitude scaling only if `mag > 100` (lines 328-332).
- The heavy lifter may use different scaling or clipping, leading to divergent trajectory vectors for identical input.

### 5. Error Handling & Fallbacks
- On JSON parse failure, the kernel logs a warning and returns the unchanged state (line 306-307), causing silent data loss.
- The heavy lifter has more aggressive fallback parsing (e.g., regex extraction of numbers) and emergency save mechanisms.

## Required Fixes (Non-Routing)

### A. Prompt Alignment
- Simplify the Geometry Kernel prompt to match the heavy lifter's expected output:
  ```json
  {
    "vector": [float, float, float],
    "objects": [
      {"id": "concept_name", "mass": 0.0-1.0, "position": [x, y, z]}
    ]
  }
  ```
- Optionally keep `summary` but make it optional and ensure it's parsed correctly.

### B. Robust JSON Normalization
- Extend `_update_state()` to:
  - Accept multiple JSON schemas (e.g., with `desc` field, with `name` instead of `id`).
  - Map common variants to the internal schema before updating `state["objects"]`.
  - Validate and coerce `mass` to float 0-1, `position` to list of 3 floats.

### C. Per-Chunk Artifact Extraction
- Move artifact extraction inside the chunk loop (after state update) to mirror heavy lifter behavior:
  ```python
  if extract_clever_artifacts:
      artifacts = extract_clever_artifacts({
          "objects": list(state["objects"].values()),
          "trajectory_vector": state["trajectory_vector"]
      })
      state["analysis_artifacts"] = artifacts
  ```

### D. Consistent Trajectory Scaling
- Adopt the same trajectory vector normalization used in the heavy lifter (if available) or define a clear clipping strategy (e.g., clamp each component to [-10,10]).

### E. Improved Error Handling
- On parse failure, attempt to extract numbers/vectors via regex as a last resort.
- Store failed chunks for manual inspection rather than silently skipping.

## Files Generated from a Single Ingestion
Based on the Geometry Kernel's output schema (`recursive_ingestion.py` lines 196-201) and artifact extraction:

1. **Primary Solar System JSON**:
   ```json
   {
     "system_id": "<file_path>",
     "gravity_well": {"concept": "<objective>", "mass": <chunk_count>},
     "objects": [
       {"id": "...", "mass": 0.5, "position": [x,y,z]}  // minimal verbosity
       // or with desc if verbosity >= standard
     ],
     "trajectory": [float, float, float]
   }
   ```

2. **Analysis Artifacts** (if verbosity allows and extractor succeeds):
   ```json
   {
     "theme_vectors": [...],
     "dependencies": [...],
     "contradictions": [...],
     "novelty_scores": [...],
     "implementation_density": 0.0-1.0,
     "context_injection": "<markdown summary>"
   }
   ```

3. **Checkpoint Files** (written by `UnifiedIngestionManager` or core loop):
   - `/app/shared_storage/data/ingestion/checkpoints/<safe_name>/latest.json`
   - Contains incremental state to resume on failure.

4. **Raw Chunk Files**:
   - `/app/shared_storage/data/ingestion/raw/<safe_name>/chunk_*.txt`

5. **Emergency Output** (on failure):
   - Same as output folder, prefixed with `EMERGENCY_`.

## Cognitive Tick Requirements for Correct Function
The Geometry Kernel's cognitive tick (via `CognitiveScheduler.run_reasoning_phase`) must:

1. **Receive a properly formatted prompt** (see Prompt Alignment above).
2. **Return ONLY valid JSON** matching the expected schema—no preambles, explanations, or markdown code fences.
3. **Include**:
   - `"vector"`: list of exactly 3 floats (trajectory update).
   - `"objects"`: list of objects, each with:
     - `"id"`: string (concept identifier).
     - `"mass"`: float between 0.0 and 1.0.
     - `"position"`: list of exactly 3 floats (x, y, z).
   - Optional `"summary"`: string for context propagation.
4. **Adhere to token limits** to avoid truncation that breaks JSON validity.
5. **Be deterministic enough** that similar chunks produce semantically similar vectors (to maintain trajectory coherence).

## Validation Checklist
- [ ] Ensure `EMBEDDING_SERVICE_URL` and LLM endpoint env vars are set correctly in the kernel's container.
- [ ] Verify the cognitive tick returns parseable JSON (test with a known input chunk).
- [ ] Confirm that `_update_state` correctly increments `trajectory_vector` and merges objects by `id`.
- [ ] Check that artifact extraction does not overwrite state but enriches it.
- [ ] Compare output schema against the GEOMETRY_ENCODING_STANDARD.md canonical output.

## References
- `shared_storage/wiki/01_core_architecture/GEOMETRY_ENCODING_STANDARD.md` – Canonical output schema.
- `shared_storage/wiki/07_advanced/GEOMETRY_KERNEL.md` – Hotfix details for Modal/local routing.
- `shared_storage/wiki/mesh_network_services.md` – Project mesh standards and state vector usage.
- `shared_storage/wiki/SESSION_BRIEF_OPUS_GEOMETRY.md` – Project state vector description.
- `services/geometry_kernel/recursive_ingestion.py` – Current implementation.
- `modal_apps/geometry_heavy_lifter.py` – Reference working implementation.

---
*Report generated for geometry kernel diagnostics. Fixes should focus on prompt/response normalization and state update robustness, not model routing.*