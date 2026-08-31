FROM python:3.11-slim-bookworm

WORKDIR /app

# Dependencies
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Copy Service
COPY services/dreaming_consolidator /app/services/dreaming_consolidator

# Env
ENV PYTHONPATH=/app
ENV PORT=8093

# Run
CMD ["python3", "services/dreaming_consolidator/api.py"]
