FROM ghcr.io/danxalot/arca/middleware:latest

# ============================================================================
# ARCA Conversational HDC (Layered)
# Layer 3 of 3-tier architecture
#
# Purpose: Service-specific code only (High-Dimensional Context processing)
# Size: ~150-300MB (includes torch, numpy, qdrant-client, fastapi)
# Update Frequency: WEEKLY (algorithm improvements)
#
# Built on: arca-middleware (which includes shared code + common deps)
# ============================================================================

# Switch to root to install service-specific deps
WORKDIR /app
USER root

# Copy service-specific requirements
COPY services/conversational_hdc/requirements.txt /tmp/service-requirements.txt
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

# Copy application code (relative to docker-compose context ./)
COPY services/conversational_hdc/app /app/app

# Fix permissions and switch back to app
RUN chown -R app:app /app

USER app

# Service metadata
ENV PORT=8096
ENV SERVICE_NAME=conversational_hdc

# Expose port (Internal)
EXPOSE 8096

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8096/health || exit 1

# Run API
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8096"]

LABEL maintainer="ARCA Development Team" \
    version="1.0" \
    description="ARCA Conversational HDC (Layered - minimal rebuild)" \
    build-layer="Layer 3/3"
