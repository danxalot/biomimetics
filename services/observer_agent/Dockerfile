FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (curl for healthcheck, docker client for restarts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -fsSL https://get.docker.com | sh \
    && rm -rf /var/lib/apt/lists/*

# Install Docker Compose V2 binary (x86_64 for this container)
RUN mkdir -p /usr/local/lib/docker/cli-plugins/ && \
    curl -SL https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose && \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose || true

COPY services/observer_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/observer_agent .

# Default command
CMD ["python", "main.py"]
