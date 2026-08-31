# Layer 3: Service-specific logic (ui_term)
FROM ghcr.io/danxalot/arca-middleware:latest

WORKDIR /app

USER root

# Install gosu for privilege dropping
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

# Copy service logic
COPY services/ui_term/ .
COPY shared/ /app/shared/

# Copy and make initialization script executable
COPY services/ui_term/init_ui_term.sh /app/
RUN chmod +x /app/init_ui_term.sh && chown -R app:app /app

USER root

EXPOSE 8085

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8085/health', timeout=5)" || exit 1

# Run initialization script
CMD ["/app/init_ui_term.sh"]
