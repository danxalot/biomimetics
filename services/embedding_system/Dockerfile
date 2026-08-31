FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libaio1t64 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first to avoid massive CUDA downloads
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Copy requirements
COPY services/embedding_system/requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy download script and model (if exists context, else script runs)
COPY services/embedding_system/download_model.py /app/
RUN python3 /app/download_model.py

# Copy application code
COPY services/embedding_system/*.py /app/
COPY shared /app/shared

# Expose port
EXPOSE 8005

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
