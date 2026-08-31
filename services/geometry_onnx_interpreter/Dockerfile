# Dockerfile for Geometry ONNX Interpreter Service
# OCI ARM64 Deployment

FROM python:3.11-slim AS base

# Install system dependencies for ARM64/OCI
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
# Use specific versions for ARM64 compatibility
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn==0.24.0 \
    pydantic==2.5.0 \
    pydantic-settings==2.1.0 \
    onnxruntime==1.16.3 \
    onnx==1.15.0 \
    numpy==1.24.3 \
    httpx==0.25.1 \
    python-dateutil==2.8.2 \
    python-multipart==0.0.6

# Copy service code
COPY . .

# Create models directory (will be volume-mounted in production)
RUN mkdir -p /app/models

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8096/interpret/health || exit 1

# Run service
EXPOSE 8096
CMD ["python", "geometry_onnx_interpreter.py"]

# Multi-stage build for smaller final image (optional)
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy only necessary files from build stage
COPY --from=base /app /app
COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Create models directory
RUN mkdir -p /app/models

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8096/interpret/health || exit 1

EXPOSE 8096
CMD ["python", "geometry_onnx_interpreter.py"]
