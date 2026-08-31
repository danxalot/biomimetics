
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (Git, Process Utils, Net Utils)
RUN apt-get update && apt-get install -y git procps psmisc curl && rm -rf /var/lib/apt/lists/*

# Install dependencies (basic setup)
RUN pip install --no-cache-dir uvicorn starlette

# Copy application code
COPY services/host_bridge/main.py .

# Expose port
EXPOSE 8092

# Define volume mount point for host filesystem (expected at runtime)
VOLUME /mnt/host

# Run the server
CMD ["python", "main.py"]
