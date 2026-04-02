#!/bin/bash

# Unified Pythia Engine Startup Script
# Builds and runs the FastAPI server with Vulkan-accelerated llama-cpp-python

set -e

echo "=========================================="
echo "Unified Pythia Engine - Startup"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please create it first:"
    echo "   python3.11 -m venv venv"
    exit 1
fi

source venv/bin/activate

echo "✅ Virtual environment activated"

# Check if llama-cpp-python is installed with Vulkan
python3 -c "
from llama_cpp import Llama
import llama_cpp.llama_cpp as llama_lib
has_vulkan = hasattr(llama_lib, 'GGML_USE_VULKAN')
print(f'Has Vulkan: {has_vulkan}')
if not has_vulkan:
    print('⚠️  llama-cpp-python not built with Vulkan support!')
    exit(1)
" || {
    echo ""
    echo "⚠️  llama-cpp-python needs to be rebuilt with Vulkan support"
    echo "   This is a CRITICAL requirement for the latent bypass to work"
    echo ""
    echo "   Attempting rebuild..."
    echo ""
    
    # Uninstall current version
    pip uninstall llama-cpp-python -y
    
    # Set Vulkan environment
    export VULKAN_SDK=/usr/local
    export CMAKE_ARGS="-DGGML_VULKAN=ON -DGGML_USE_METAL=OFF"
    
    # Install with Vulkan support
    echo "   Installing llama-cpp-python with Vulkan (this may take 5-10 minutes)..."
    pip install --no-cache-dir llama-cpp-python
    
    # Verify
    python3 -c "
from llama_cpp import Llama
import llama_cpp.llama_cpp as llama_lib
has_vulkan = hasattr(llama_lib, 'GGML_USE_VULKAN')
print(f'Has Vulkan after rebuild: {has_vulkan}')
if not has_vulkan:
    print('❌ Vulkan still not available after rebuild')
    exit(1)
print('✅ Vulkan support confirmed!')
"
}

# Install/update requirements
echo ""
echo "📦 Installing/updating dependencies..."
pip install -r requirements.txt --quiet

echo ""
echo "🚀 Starting Unified Pythia Engine..."
echo "   Port: 11436"
echo "   Model: Qwen3-VL-2B-Instruct-Q8_0.gguf"
echo "   GPU: Vulkan0 (AMD Radeon Pro 5500M)"
echo ""
echo "   Endpoints:"
echo "     - GET  /health"
echo "     - POST /v1/chat/completions"
echo "     - POST /v1/latent_inject"
echo "     - POST /v1/geometry_embed"
echo ""
echo "   Press Ctrl+C to stop"
echo ""

# Run the server
python3 unified_pythia_engine.py
