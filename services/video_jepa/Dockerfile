# V-JEPA Service (OCI ARM64)
# Optimised for Ampere A1 (PyTorch CPU)

FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (ffmpeg for video decoding)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch (CPU only for ARM64 usually works best with default wheel or specific ARM wheel)
# For OCI Ampere, standard pip install torch typically grabs the aarch64 wheel.
RUN pip install --no-cache-dir \
    torch \
    torchvision \
    torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart \
    numpy \
    Pillow

# Copy app
COPY . .

# Expose port
EXPOSE 8000

# Run API
CMD ["python3", "api.py"]
