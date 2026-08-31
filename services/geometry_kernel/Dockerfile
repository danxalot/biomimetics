# Layer 3: Service-specific logic (Geometry Kernel)
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from service folder
COPY services/geometry_kernel/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service application code
COPY services/geometry_kernel /app/services/geometry_kernel
COPY shared /app/shared

# Set PYTHONPATH to include the app root
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8087

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8087/health || exit 1

# Run the API server from the package context
CMD ["python3", "services/geometry_kernel/api.py"]
