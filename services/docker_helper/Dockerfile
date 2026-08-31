FROM python:3.11-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global --add safe.directory /home/ubuntu/ARCA

COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel && pip install --no-cache-dir -r requirements.txt

COPY helper.py .
CMD ["python", "helper.py"]
