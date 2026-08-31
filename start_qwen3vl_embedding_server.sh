#!/bin/bash
# Pythia Server — Qwen3-VL-Embedding-2B (Q8_0) on Vulkan0, port 11435
# LAUNCHD COPY (lives in ~/biomimetics because launchd runs under the Claude.app TCC
# context, which is denied path-traversal into the TCC-protected ~/Documents folder).
# Files in ~/Documents ARE readable once the process runs — only traversal to the
# SCRIPT is blocked — so this copy hardcodes ABSOLUTE repo paths to the model/binary.
# Keep in sync with services/pythia_server/start_qwen3vl_embedding_server.sh.
#
# Model:  Rizwan313/Qwen3-VL-Embedding-2B-GGUF → qwen3-vl-embedding-2b-Q8_0.gguf
# MMProj: mmproj-f16.gguf   Binary: llama_cpp_latest/build (v9445)
# Device: Vulkan0 = AMD Radeon Pro 5500M (4 GB VRAM). Embeddings-only server.

set -euo pipefail

REPO="/Users/danexall/Documents/VS Code Projects/ARCA/services/pythia_server"
BIN_DIR="${REPO}/llama_cpp_latest/build_stable/bin"
MODEL="${REPO}/models/qwen3-vl-embedding-2b-Q8_0.gguf"
MMPROJ="${REPO}/models/mmproj-f16.gguf"

PORT="${LLAMA_PORT:-11435}"
HOST="${LLAMA_HOST:-0.0.0.0}"
GPU_LAYERS="${LLAMA_GPU_LAYERS:-99}"     # full offload; drop to 22 if Vulkan OOMs
# ── VULKAN WATCHDOG STABILITY (2026-07-14) — keep in sync with repo copy ──
# 4GB VRAM 5500M: model(1.7G)+mmproj-on-GPU(0.78G) leaves too little for KV+compute;
# big dispatch trips macOS watchdog → GPU reset → vk::DeviceLostError crash-loop.
# Fix: smaller dispatch + mmproj on CPU (frees ~0.78G, numerically stable). Metal N/A.
CTX="${LLAMA_CTX:-2048}"
BATCH="${LLAMA_BATCH:-128}"
UBATCH="${LLAMA_UBATCH:-128}"
THREADS="${LLAMA_THREADS:-8}"
THREADS_BATCH="${LLAMA_THREADS_BATCH:-8}"
# Auto --parallel (4 slots) + cache-idle-slots was the DeviceLost / 4–12s
# first-query stall: KV for 4×2048 does not fit the 4GB 5500M, and every new
# task GPU-readback'd idle slots (prompt_save → vk::DeviceLostError). Pin 1 slot.
PARALLEL="${LLAMA_PARALLEL:-1}"
# Corpus-matching recipe (2026-07-08): the FGA corpus was embedded with LAST-TOKEN
# pooling + NO L2-normalisation (geometry_heavy_lifter core.py:426, Embedding-2B
# pooling_type=3). Set permanently so the local embedder produces vectors in the
# same space Pythia's corpus was built in. Callers prepend EMB_INSTR themselves.
POOLING="${LLAMA_POOLING:-last}"
NORMALIZE="${LLAMA_EMBD_NORMALIZE:--1}"   # -1 = no normalisation (raw last-hidden)

export DYLD_LIBRARY_PATH="${BIN_DIR}:${DYLD_LIBRARY_PATH:-}"
export GGML_VK_VISIBLE_DEVICES=0
export GGML_METAL=off

[[ -f "$MODEL"  ]] || { echo "❌ model missing: $MODEL" >&2; exit 1; }
[[ -f "$MMPROJ" ]] || { echo "❌ mmproj missing: $MMPROJ" >&2; exit 1; }
[[ -x "$BIN_DIR/llama-server" ]] || { echo "❌ llama-server missing: $BIN_DIR/llama-server" >&2; exit 1; }

echo "[$(date)] Starting Qwen3-VL-Embedding-2B (Q8_0) — Vulkan0, port ${PORT}, gpu-layers ${GPU_LAYERS}"

exec "$BIN_DIR/llama-server" \
    --model "$MODEL" \
    --mmproj "$MMPROJ" \
    --no-mmproj-offload \
    --host "$HOST" \
    --port "$PORT" \
    --threads "$THREADS" \
    --threads-batch "$THREADS_BATCH" \
    --ctx-size "$CTX" \
    --batch-size "$BATCH" \
    --ubatch-size "$UBATCH" \
    --gpu-layers "$GPU_LAYERS" \
    --main-gpu 0 \
    --device Vulkan0 \
    --embeddings \
    --pooling "$POOLING" \
    --embd-normalize "$NORMALIZE" \
    --parallel "$PARALLEL" \
    --no-cache-idle-slots \
    -lv 1
