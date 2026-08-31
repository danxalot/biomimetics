# syntax=docker/dockerfile:1.4

# Multi-stage build for ARCA MCP Server
# Build stage - compile and install dependencies
FROM --platform=linux/arm64 python:3.11-slim AS builder

WORKDIR /build

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage - minimal final image
FROM --platform=linux/arm64 python:3.11-slim AS runtime

WORKDIR /app

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/app/.local

# Set PATH
ENV PATH=/home/app/.local/bin:$PATH

# Copy application code
COPY --chown=app:app . .

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8090/health')" || exit 1

CMD ["python3", "macbook_mcp_integration_server.py"]
