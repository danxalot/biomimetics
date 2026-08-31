FROM ghcr.io/danxalot/arca/middleware:latest

# ============================================================================
# ARCA HSE Encoder (Layered)
# Layer 3 of 3-tier architecture
#
# Purpose: Service-specific code only (Hyperdimensional Semantic Encoding)
# Size: ~200-400MB (includes torch, numpy, semantic encoding libs)
# Update Frequency: WEEKLY (encoding algorithm improvements)
#
# Built on: arca-middleware (which includes shared code + common deps)
# ============================================================================

# Switch to root to install service-specific deps
WORKDIR /app
USER root

# Install system dependencies for numpy/arm optimization (if not in middleware)
RUN apt-get update && apt-get install -y \
    libopenblas-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Enable OpenBLAS threading for ARM NEON
ENV OPENBLAS_NUM_THREADS=4
ENV OMP_NUM_THREADS=4

# Copy service-specific requirements
COPY services/hse_encoder/requirements.txt* /tmp/service-requirements.txt
RUN if [ -f /tmp/service-requirements.txt ]; then \
    python3.11 -m pip install --break-system-packages --no-cache-dir -r /tmp/service-requirements.txt && \
    rm /tmp/service-requirements.txt; \
    fi

# Install CPU-only torch specifically for this service
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        python3.11 -m pip install --break-system-packages --no-cache-dir \
            --index-url https://download.pytorch.org/whl/cpu \
            torch; \
    else \
        python3.11 -m pip install --break-system-packages --no-cache-dir torch; \
    fi

# Copy application code
COPY services/hse_encoder/. /app/

# Fix permissions and switch back to app
RUN chown -R app:app /app

USER app

# Service metadata
ENV PORT=8095
ENV SERVICE_NAME=hse_encoder

# Expose HSE Encoder port
EXPOSE 8095

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8095/health || exit 1

# Run the service
CMD ["python", "main.py"]

LABEL maintainer="ARCA Development Team" \
    version="1.0" \
    description="ARCA HSE Encoder (Layered - minimal rebuild)" \
    build-layer="Layer 3/3"
