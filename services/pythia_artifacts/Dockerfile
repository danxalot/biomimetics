FROM ghcr.io/danxalot/arca-middleware:arm64

# ============================================================================
# ARCA Pythia Pulse Service (Layered)
# Layer 3 of 3-tier architecture
#
# Purpose: Service-specific code only (Default Mode Network heartbeat)
# Size: ~50-100MB (lightweight service for continuous operation)
# Update Frequency: WEEKLY (algorithm improvements)
#
# Built on: arca-middleware (which includes shared code + common deps)
# ============================================================================

# Switch to root to install service-specific deps
USER root

WORKDIR /app

# Install service-specific dependencies
RUN python3.11 -m pip install --break-system-packages --no-cache-dir redis numpy

# Copy application code
COPY services/pythia_artifacts/pythia_pulse.py /app/

# Fix permissions and switch back to app
RUN chown -R app:app /app

USER app

# Service metadata
ENV PORT=8080
ENV SERVICE_NAME=pythia_pulse

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3.11 -c "import sys; from pythia_pulse import *; print('Health check passed')" 2>/dev/null || exit 1

# Run the service
CMD ["python", "pythia_pulse.py"]

LABEL maintainer="ARCA Development Team" \
    version="1.0" \
    description="ARCA Pythia Pulse Service (Layered - minimal rebuild)" \
    build-layer="Layer 3/3"
