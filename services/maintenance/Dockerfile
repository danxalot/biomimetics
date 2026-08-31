# Layer 3: Service-specific logic (following ARCA Container Build Strategy)
FROM ghcr.io/danxalot/arca-middleware:latest

USER root

WORKDIR /app

# Copy shared dependencies
COPY services/execution_firewall /app/execution_firewall

# Copy service-specific application code
COPY services/maintenance/requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY services/maintenance/ /app/
RUN chown -R app:app /app

# Make port available to the world outside this container
EXPOSE 8090

# Set environment variables
ENV PORT=8090
ENV SERVICE_NAME=maintainer_agents

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8090/health || exit 1

USER root

# Run the application
CMD ["python", "main.py"]
