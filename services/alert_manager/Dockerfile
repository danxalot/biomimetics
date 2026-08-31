FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY services/alert_manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/alert_manager/main.py .

EXPOSE 8089

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=10s \
    CMD curl -f http://localhost:8089/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8089"]
