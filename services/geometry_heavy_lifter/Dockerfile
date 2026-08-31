# ─────────────────────────────────────────────────────────────────────────────
# ARCA Geometry Heavy Lifter
# Target GPU:  NVIDIA L40S (48 GB VRAM) on Vultr
#              NVIDIA A10G (24 GB VRAM) on Modal (same image, same paths)
#
# Build (from repo root):
#   docker build -f services/geometry_heavy_lifter/Dockerfile \
#     -t ghcr.io/danxalot/arca-geometry_heavy_lifter:latest .
#
# Run on Vultr:
#   docker run --gpus all --rm \
#     -v /root/shared_storage:/app/shared_storage \
#     ghcr.io/danxalot/arca-geometry_heavy_lifter:latest \
#     python services/geometry_heavy_lifter/run_pipeline.py
# ─────────────────────────────────────────────────────────────────────────────

FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# --------------------------------------------------------------------------
# System packages
# --------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 \
        python3.10-dev \
        python3-pip \
        git \
        curl \
        libgl1 \
        libglib2.0-0 \
        poppler-utils \
        tesseract-ocr \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Make python3.10 the default python/pip
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 \
 && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 \
 && python -m pip install --upgrade pip setuptools wheel

# --------------------------------------------------------------------------
# Python packages — GPU / vLLM stack
# --------------------------------------------------------------------------
RUN pip install --no-cache-dir \
    vllm>=0.7.2 \
    autoawq>=0.2.5 \
    "qwen-vl-utils>=0.0.8" \
    "transformers>=4.47.0" \
    "accelerate>=0.30.0" \
    "huggingface-hub>=0.22.0" \
    hf_transfer \
    "ray>=2.10.0" \
    "numpy>=1.24.0" \
    "pillow>=10.0.0" \
    "torch>=2.2.0"

# --------------------------------------------------------------------------
# Python packages — PDF / OCR stack (GPU-enabled PaddlePaddle)
# --------------------------------------------------------------------------
RUN pip install --no-cache-dir \
    "pdf2image>=1.17.0" \
    "paddlepaddle-gpu==2.6.2.post120" \
    --extra-index-url https://www.paddlepaddle.org.cn/packages/stable/cu120/ \
    "paddleocr==2.8.1"

# --------------------------------------------------------------------------
# Python packages — EPUB / eBook extraction
# --------------------------------------------------------------------------
RUN pip install --no-cache-dir \
    "ebooklib>=0.18" \
    "beautifulsoup4>=4.12.0" \
    "lxml>=4.9.0"

# --------------------------------------------------------------------------
# MOBI support — calibre's ebook-convert CLI (separate layer for cacheability)
# --------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        calibre \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------
# Application code (baked in — this image IS the future Modal container)
# --------------------------------------------------------------------------
WORKDIR /app

COPY services/geometry_kernel           /app/services/geometry_kernel
COPY services/pdf_to_embedding          /app/services/pdf_to_embedding
COPY services/geometry_heavy_lifter     /app/services/geometry_heavy_lifter
COPY modal_apps                         /app/modal_apps

# Ensure every services/ sub-package is importable
RUN touch /app/services/__init__.py \
    /app/services/pdf_to_embedding/__init__.py \
    /app/services/geometry_heavy_lifter/__init__.py

# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------
ENV PYTHONPATH=/app/modal_apps:/app
ENV HF_HUB_ENABLE_HF_TRANSFER=0
ENV PADDLE_FLAGS_INIT_LOG_FILE=/dev/null
ENV TOKENIZERS_PARALLELISM=false
ENV PADDLE_USE_GPU=1
ENV PADDLE_HOME=/models/paddle
ENV HF_HOME=/models/hf_cache
ENV VLLM_COMPILE_CACHE_DIR=/models/vllm_compile_cache

# CPU threading: intentionally NOT set so OpenMP/MKL/PyTorch auto-detect
# available cores at runtime.  Works on L40S (16-core), A10G (4-core), etc.
# Do NOT add OMP_NUM_THREADS or MKL_NUM_THREADS here.

# --------------------------------------------------------------------------
# Shared storage mount point (NFS on Modal, docker volume on Vultr)
# --------------------------------------------------------------------------
VOLUME ["/app/shared_storage"]

# Default entrypoint — override at run time for single-book runs
CMD ["python", "services/geometry_heavy_lifter/run_pipeline.py"]
