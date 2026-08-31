FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn httpx

# Copy the server code and static assets
# Note: We also mount these as volumes in docker-compose for live updates,
# but they need to be here for the initial build/standalone run.
COPY services/pythia_lab/server.py /app/server.py
COPY services/pythia_lab/static /app/static

EXPOSE 8091

CMD ["python", "server.py"]
