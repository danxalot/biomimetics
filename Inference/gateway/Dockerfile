# Layer 3: Service-specific logic (gateway)
FROM ghcr.io/danxalot/arca-middleware:latest

WORKDIR /app

USER root

# Install gosu for privilege dropping
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

# Copy service code
COPY services/gateway/ .

# Copy and make initialization script executable
COPY services/gateway/init_gateway.sh /app/
RUN chmod +x /app/init_gateway.sh && chown -R app:app /app

USER root

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

# Run initialization script then start server
CMD ["/app/init_gateway.sh"]