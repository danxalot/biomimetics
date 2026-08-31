FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    qdrant-client \
    firebase-admin \
    aiohttp \
    httpx \
    google-cloud-pubsub \
    mcp \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create memu directory
RUN mkdir -p /app/memu

# Copy updated memory integration with Gemini embeddings
COPY services/openclaw_integration/memory_integration.py /app/memu/
COPY services/openclaw/memu_service.py /app/memu/

EXPOSE 8080

# Run FastAPI service (Cloud Run requires PORT env var)
CMD ["python", "-m", "uvicorn", "memu.memu_service:app", "--host", "0.0.0.0", "--port", "8080"]
