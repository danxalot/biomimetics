#!/bin/bash

# Pythia Server - LLaMA.cpp with Vulkan 0
# Always runs Qwen3-VL-2B-Instruct-Q8_0.gguf with mmproj on port 11436

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

# Set library path for dylibs
export DYLD_LIBRARY_PATH="$SCRIPT_DIR:$DYLD_LIBRARY_PATH"

PROJECT_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

# Model paths
MODEL_PATH="$PROJECT_ROOT/models_optimized/Qwen3-VL-2B-Instruct-Q8_0.gguf"
MMPROJ_PATH="$PROJECT_ROOT/models_optimized/Qwen3-VL-2B-Instruct-MMProj.gguf"

# Check if model exists
if [ ! -f "$MODEL_PATH" ]; then
    echo "Error: Model not found at $MODEL_PATH"
    exit 1
fi

echo "Starting Pythia Server"
echo "  Model: $MODEL_PATH"
echo "  Port: 11436"
echo "  Device: Vulkan0 (AMD Radeon Pro 5500M)"

# Run llama-server with Vulkan
# Use --device Vulkan0 to specify the AMD Radeon Pro 5500M
# Remove MMProj path as it's not specified by user for this model, and we don't know where it is yet
./llama-server \
    --model "$MODEL_PATH" \
    --host 0.0.0.0 \
    --port 11436 \
    --threads 8 \
    --ctx-size 4096 \
    --batch-size 4096 \
    --ubatch-size 4096 \
    --gpu-layers 99 \
    --device Vulkan0 \
    --embeddings \
    --pooling rank \
    -cb \
    --verbose \
    > server_11436.log 2>&1

