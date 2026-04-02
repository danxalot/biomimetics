FROM python:3.11-slim

WORKDIR /app/memu

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi==0.135.1 \
    uvicorn==0.41.0 \
    aiohttp==3.13.3 \
    pydantic==2.12.5 \
    pydantic-settings==2.13.1 \
    qdrant-client==1.17.1 \
    firebase-admin==7.2.0 \
    google-cloud-firestore \
    google-cloud-storage \
    certifi

COPY memory_integration.py .
COPY memu_service.py .

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD ["uvicorn", "memu_service:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "300"]
