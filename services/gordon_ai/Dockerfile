# Layer 3: Service-specific logic
FROM ghcr.io/danxalot/arca-middleware:latest

WORKDIR /app

# middleware already has curl and python deps
COPY services/gordon_ai/main.py .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8091/health || exit 1

EXPOSE 8091

# Run the application
CMD ["python", "main.py"]
