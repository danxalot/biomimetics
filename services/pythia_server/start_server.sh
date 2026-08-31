#!/bin/bash
# Pythia Server - llama.cpp with Vulkan0
# Runs Qwen3-VL-2B-Instruct-Q8 and mmproj on port 11435

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0])")" && pwd)
cd "$SCRIPT_DIR"

# Set library path for dylibs - use Vulkan libraries
export DYLD_LIBRARY_PATH="$SCRIPT_DIR:$DYLD_LIBRARY_PATH"

PROJECT_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

# Model paths - CORRECTED: Use Qwen3-VL-2B models
MODEL_PATH="$PROJECT_ROOT/models_optimized/Qwen3-VL-2B-Instruct-Q8/Qwen3-VL-2B-Instruct-Q8_0.gguf"
MMROJ_PATH="$PROJECT_ROOT/models_optimized/Qwen3-VL-2B-Instruct-Q8/mmproj-Qwen.Qwen3-VL-2B-Instruct.f16.gguf"

# Check if model exists
if [ ! -f "$MODEL_PATH" ]; then
    echo "Error: Model not found at $MODEL_PATH"
    exit 1
fi

# Check if mmproj exists
if [ ! -f "$MMROJ_PATH" ]; then
    echo "Error: MMProj not found at $MMROJ_PATH"
    exit 1
fi

echo "Starting Pythia Server"
echo "  Model: $MODEL_PATH"
echo "  MMProj: $MMROJ_PATH"
echo "  Port: 11435"
echo "  Device: Vulkan0 (AMD Radeon Pro 5500M)"

# Run llama-server with Vulkan
# Use --device Vulkan0 to specify the AMD Radeon Pro 5500M
./llama-server \
    --model "$MODEL_PATH" \
    --mmproj "$MMROJ_PATH" \
    --host 0.0.0.0 \
    --port 11435 \
    --threads 16 \
    --ctx-size 12288 \
    --batch-size 8192 \
    --ubatch-size 8192 \
    --gpu-layers 99 \
    --device Vulkan0 \
    --verbose \
    2>&1 | tee server.log