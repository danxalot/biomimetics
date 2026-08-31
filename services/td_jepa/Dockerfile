FROM python:3.11-slim-bookworm

WORKDIR /app

# Dependencies
# Dependencies
RUN apt-get update && apt-get install -y git unzip && rm -rf /var/lib/apt/lists/*

COPY services/td_jepa/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Pre-download JEPA model removed to avoid build failure
# RUN python3 -c "import torch; torch.hub.load('facebookresearch/jepa:main', 'vit_L_16', force_reload=True)"


# Copy Service
COPY services/td_jepa /app/services/td_jepa

# Env
ENV PYTHONPATH=/app
ENV PORT=8094

# Run
CMD ["python3", "services/td_jepa/api.py"]
