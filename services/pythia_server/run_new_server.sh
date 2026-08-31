#!/bin/bash
# Pythia Server - Updated with new llama.cpp build

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

PROJECT_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

LLAMA_BUILD_DIR="$SCRIPT_DIR/llama_cpp/build_vulkan/bin"
export DYLD_LIBRARY_PATH="$LLAMA_BUILD_DIR:$DYLD_LIBRARY_PATH"

# Model paths
MODEL_PATH="$PROJECT_ROOT/models_optimized/qwen3.5-2b-Q8/qwen3.5-2b-q8_0.gguf"
MMPROJ_PATH="$PROJECT_ROOT/models_optimized/qwen3.5-2b-Q8/mmproj-F16.gguf"

echo "Starting Pythia Server (Updated Build)"
echo "  Model: $MODEL_PATH"
echo "  MMProj: $MMPROJ_PATH"
echo "  Port: 11435"
echo "  Device: Vulkan 0"
echo "  Context: 12288"
echo "  GPU Layers: 99"

export GGML_VK_VISIBLE_DEVICES=0

"$LLAMA_BUILD_DIR/llama-server" \
    --model "$MODEL_PATH" \
    --mmproj "$MMPROJ_PATH" \
    --host 0.0.0.0 \
    --port 11435 \
    --threads 8 \
    --ctx-size 12288 \
    --batch-size 4096 \
    --ubatch-size 4096 \
    --gpu-layers 99 \
    --verbose \
    2>&1 | tee server_new.log
