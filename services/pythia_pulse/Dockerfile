FROM python:3.11-slim

# ============================================================================
# ARCA Pythia Pulse Service
# Default Mode Network Heartbeat
# ============================================================================

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir redis numpy

# Copy application code
COPY services/pythia_pulse/pythia_pulse.py /app/pythia_pulse.py

# Environment variables
ENV DRAGONFLY_HOST="localhost"
ENV DRAGONFLY_PORT="6379"
ENV PYTHIA_REDIS_HOST="localhost"
ENV PYTHIA_REDIS_PORT="6380"
ENV PULSE_LOG_LEVEL="INFO"
ENV PULSE_TICK_S="1.0"

# Run the service
CMD ["python", "-u", "pythia_pulse.py"]

LABEL maintainer="ARCA Development Team" \
    version="1.0" \
    description="ARCA Pythia Pulse Service - Default Mode Network Heartbeat"
