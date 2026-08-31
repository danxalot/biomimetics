FROM python:3.11-slim-bookworm

WORKDIR /app

# Dependencies
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Copy Service
COPY services/reflexive_amygdala /app/services/reflexive_amygdala

# Env
ENV PYTHONPATH=/app
ENV PORT=8092

# Run
CMD ["python3", "services/reflexive_amygdala/api.py"]
