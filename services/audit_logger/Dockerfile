FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/audit_logger/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/audit_logger/main.py .

EXPOSE 9092

CMD ["python", "main.py"]
