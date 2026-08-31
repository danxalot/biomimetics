# syntax=docker/dockerfile:1.4

# Multi-stage build for ARCA MCP Server
# Build stage - compile and install dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY services/mcp_server/requirements.txt .
RUN pip install --default-timeout=100 --no-cache-dir --user -r requirements.txt

# Runtime stage - minimal final image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo \
    "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
    "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update && apt-get install -y docker-ce-cli gosu \
    && curl -fsSL https://tailscale.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
# USER app - Removed to allow entrypoint to run as root for permission setup

# Copy installed packages from builder
COPY --from=builder /root/.local /home/app/.local

# Set environment variables for Python packages
ENV PATH=/home/app/.local/bin:$PATH
ENV REDIS_HOST=redis
ENV PYTHONPATH=/home/app/.local/lib/python3.11/site-packages:/app:$PYTHONPATH

# Copy application code
COPY services/mcp_server/ .
COPY shared/ /app/shared/

# Copy and make initialization script executable
COPY services/mcp_server/init_mcp_server.sh /app/
RUN chmod +x /app/init_mcp_server.sh

EXPOSE 8086

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8086/health')" || exit 1

# Run initialization script then start server
CMD ["/app/init_mcp_server.sh"]
