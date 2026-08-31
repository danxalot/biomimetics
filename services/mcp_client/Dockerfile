FROM python:3.11-slim

WORKDIR /app
COPY services/mcp_server/mcp_client.py ./
COPY services/mcp_server/requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

# Expose entrypoint as a script; keep image non-root for security
USER 1000

CMD ["python", "/app/mcp_client.py"]
