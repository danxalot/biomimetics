FROM python:3.11-slim-bookworm

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    curl \
    wget \
    pkg-config \
    libcurl4-openssl-dev \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Clone and build llama.cpp from source (Tag b6907 for Qwen3-VL support)
WORKDIR /app
RUN git clone https://github.com/ggml-org/llama.cpp.git \
    && cd llama.cpp \
    && git checkout master \
    && git config user.email "build@arca" \
    && git config user.name "ARCA Build" \
    && git remote add chrismuzyn https://github.com/chrismuzyn/llama.cpp.git \
    && git fetch chrismuzyn chris_mm_embed \
    && git cherry-pick d7ec22fe465c44c6f57cb356583a1dcc66262845 \
    && mkdir build \
    && cd build \
    && cmake .. -DGGML_NATIVE=1 -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS -DGGML_OPENMP=ON \
    && make llama-server -j$(nproc) \
    && ls -la /app/llama.cpp/build/bin/llama-server

# Expose server binary as entrypoint
ENTRYPOINT ["/app/llama.cpp/build/bin/llama-server"]
CMD ["--help"]
