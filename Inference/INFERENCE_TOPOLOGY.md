# Qwen3-VL Inference Topology (Intel Mac / AMD 5500M)

## Hardware Configuration
- **Host**: Intel i9 MacBook Pro
- **GPU**: AMD Radeon Pro 5500M
- **Acceleration**: Vulkan (via MoltenVK) + Metal (Native)

## Stable Execution Strategy (Hybrid)
To bypass GPU timeouts and "Error Code 1" (Metal Command Buffer Failure) during large vision token processing:

1. **Vision Encoder (CLIP)**: **CPU-ONLY**
   - Environment: `MTMD_BACKEND_DEVICE=CPU`
   - Reasoning: 1300+ vision tokens trigger `kIOAccelCommandBufferCallbackErrorTimeout` on the AMD 5500M when using Metal. CPU encoding takes ~16s but is 100% stable.

2. **Language Model (LLM)**: **CPU or Small-Batch GPU**
   - Mode: `n_gpu_layers=0` (CPU) for absolute stability.
   - Batching: `n_batch=64`, `n_ubatch=32` to keep command buffers small if using GPU.
   - Backend Conflict: Avoid splitting layers between Metal and Vulkan. Stick to one if possible.

## Architectural Improvements (Patched)
- **Projector**: `PROJECTOR_TYPE_QWEN3VL` (Merger/Resampler logic)
- **Weights**: Fused QKV weight and bias splitting implemented in `clip.cpp`.
- **Normalization**: `NORM_TYPE_RMS` enabled for vision branch.
- **Positional Encoding**: M-RoPE 3D indexing correctly integrated via `clip_is_qwen2vl` gatekeeper.
- **Patch Bias**: Full support for `model.patch_bias` in ViT graph.

## Verification
- **Test Script**: `run_qwen_vulkan.py`
- **Baseline Result**: Successfully identified `llama0-banner.png` (Solar panels) with coherent text generation.
