# Phase 2: Dual-Tier Memory Matrix - Deployment Guide

**Architecture**: Deep Storage (MemU) + Working Memory (MuninnDB)

---

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    NOTION WEBHOOK                           │
│              hooks.arca-vsa.tech                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  GCP Pub/Sub          │
         │  os-events            │
         └───────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  MemU (Cloud    │     │  MuninnDB       │
│  Run)           │     │  (GCP e2-micro) │
│  - Deep Archive │     │  - Working Mem  │
│  - Qdrant Cloud │     │  - Hebbian      │
│  - Firebase     │     │  - ACT-R        │
│  - Gemini Emb   │     │  - 24/7 MCP     │
│  - Gemma 4      │     │                 │
│  - MCP Server   │     │                 │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  Local MuninnDB        │
                    │  (Docker - Mac)        │
                    │  - Dev Scratchpad      │
                    │  - Transient errors    │
                    │  - MCP for coding      │
                    └────────────────────────┘
```

---

## 1. MemU - Deep Archive (GCP Cloud Run)

### Configuration

**Location**: GCP Cloud Run (serverless, pay-per-use)  
**Port**: 8096  
**Memory**: 512MB - 2GB  
**CPU**: 1-2 vCPU  
**Cost**: ~$0-5/mo (sleeps when idle)

### Environment Variables

```bash
# Gemini Embeddings
USE_GEMINI_EMBEDDINGS=true
GEMINI_EMBEDDING_MODEL=text-embedding-004
GEMINI_EMBEDDING_API_KEY_FILE=/run/secrets/google_ai_studio
EMBEDDING_DIMS=1024
EMBEDDING_RPM=100
EMBEDDING_TPM=30
EMBEDDING_TPD=1000

# Gemma 4 Agent
AGENT_PROVIDER=gemini
AGENT_MODEL=gemma-4-26b-a4b-it
AGENT_API_KEY_FILE=/run/secrets/google_ai_studio
AGENT_RPM=30
AGENT_TPM=15000
AGENT_CONTEXT_LIMIT=131072

# Qdrant Cloud
QDRANT_URL=https://bfc3f711-81d4-43c6-b7bb-f58c99684d70.eu-west-2-0.aws.cloud.qdrant.io
QDRANT_COLLECTION=arca_memory
QDRANT_API_KEY_FILE=/run/secrets/qdrant_api_key

# Firebase
FIREBASE_CREDENTIALS_PATH=/run/secrets/gcp_credentials.json
FIREBASE_PROJECT_ID=arca-471022

# GCP Pub/Sub
GCP_PROJECT_ID=arca-471022
PUBSUB_TOPIC_ID=os-events
PUBSUB_SUBSCRIPTION_ID=memu-memory-events

# MCP Server
MCP_SERVER_PORT=8096
MCP_INSTANCE_ID=memu-deep-archive
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    qdrant-client \
    firebase-admin \
    aiohttp \
    httpx \
    google-cloud-pubsub \
    mcp \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY services/openclaw_integration/memory_integration.py /app/memu/
COPY services/openclaw/memu_service.py /app/memu/
COPY services/memu/mcp_server.py /app/memu/

EXPOSE 8096

CMD ["python", "-m", "uvicorn", "memu_service:app", "--host", "0.0.0.0", "--port", "8096"]
```

### Deploy to Cloud Run

```bash
cd /Users/danexall/Documents/VS Code Projects/ARCA

# Build and push
docker build -t gcr.io/arca-471022/memu:latest -f services/memu/Dockerfile .
docker push gcr.io/arca-471022/memu:latest

# Deploy to Cloud Run
gcloud run deploy memu \
  --image gcr.io/arca-471022/memu:latest \
  --platform managed \
  --region europe-west1 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --concurrency 10 \
  --set-env-vars="GCP_PROJECT_ID=arca-471022" \
  --add-cloudsql-instances="" \
  --allow-unauthenticated
```

---

## 2. Global MuninnDB - Working Memory (GCP e2-micro)

### Configuration

**Location**: GCP e2-micro VM (always-on)  
**Storage**: 30GB persistent disk  
**RAM**: 1GB (shared)  
**Cost**: ~$5-10/mo (always running)

### Architecture

MuninnDB implements:
- **Engram Storage**: Every event from Pub/Sub
- **ACT-R Decay**: Memories fade over time unless reinforced
- **Hebbian Learning**: "Neurons that fire together, wire together"
- **Relevance Scoring**: Surfaces artifacts based on current context
- **MCP Server**: 24/7 accessible memory interface

### Installation Script

```bash
#!/bin/bash
# install-muninn-global.sh - Run on GCP e2-micro VM

set -e

# Install Python and dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv docker.io

# Create MuninnDB directory
mkdir -p ~/muninn-global
cd ~/muninn-global

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install MuninnDB
pip install muninn-db mcp google-cloud-pubsub aiohttp

# Create config
cat > config.json <<EOF
{
  "instance_id": "muninn-global-gcp",
  "storage_path": "/home/ubuntu/muninn-global/data",
  "pubsub": {
    "project_id": "arca-471022",
    "subscription_id": "muninn-global-events",
    "topics": ["os-events"]
  },
  "hebbian_learning": {
    "enabled": true,
    "decay_rate": 0.01,
    "reinforcement_threshold": 0.5
  },
  "act_r": {
    "enabled": true,
    "base_level_activation": 0.5,
    "retrieval_threshold": 0.3
  },
  "mcp": {
    "port": 8097,
    "host": "0.0.0.0"
  }
}
EOF

# Create systemd service
sudo tee /etc/systemd/system/muninn-global.service > /dev/null <<EOF
[Unit]
Description=MuninnDB Global Memory Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/muninn-global
ExecStart=/home/ubuntu/muninn-global/venv/bin/python -m muninn.server --config config.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable muninn-global
sudo systemctl start muninn-global

echo "✅ MuninnDB Global installed and running"
```

### Hebbian Learning Configuration

```python
# muninn_config.py
HEBBIAN_CONFIG = {
    # Learning rate for co-activated engrams
    "learning_rate": 0.1,
    
    # Decay rate per hour (memories fade)
    "decay_rate": 0.01,
    
    # Minimum activation to surface
    "retrieval_threshold": 0.3,
    
    # Maximum connections per engram
    "max_connections": 100,
    
    # Time window for co-activation (seconds)
    "coactivation_window": 300,
    
    # Reinforcement multiplier when retrieved
    "reinforcement_multiplier": 1.5,
}

ACT_R_CONFIG = {
    # Base level activation equation parameters
    "d": 0.5,  # Decay rate
    "tau": 0.3,  # Retrieval threshold
    
    # Associative activation
    "W": 2.0,  # Maximum associative strength
    "S": 0.5,  # Source activation
    
    # Partial matching
    "mp": 0.5,  # Mismatch penalty
}
```

---

## 3. Local MuninnDB - Dev Scratchpad (Docker)

### Configuration

**Location**: Docker on Mac  
**Storage**: Local volume  
**RAM**: 512MB  
**Cost**: $0 (local)

### docker-compose.local-muninn.yml

```yaml
version: '3.8'

services:
  muninn-local:
    image: muninn-db:latest
    build:
      context: ./services/muninn
      dockerfile: Dockerfile
    container_name: muninn-local
    ports:
      - "8098:8098"
    volumes:
      - ./data/muninn-local:/app/data
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - INSTANCE_ID=muninn-local-dev
      - STORAGE_PATH=/app/data
      - MCP_PORT=8098
      - MCP_HOST=0.0.0.0
      - TRACKING_MODE=transient
      - AUTO_FLUSH=false
      - FLUSH_INTERVAL=3600
      - SERENA_INTEGRATION=true
    networks:
      - arca-local
    restart: unless-stopped

networks:
  arca-local:
    name: arca-local
```

### Usage

```bash
# Start when coding
cd /Users/danexall/Documents/VS Code Projects/ARCA
docker-compose -f docker-compose.local-muninn.yml up -d

# Stop when done
docker-compose -f docker-compose.local-muninn.yml down
```

---

## 4. Copaw Integration - Conversation Turns

### Configuration

All Copaw conversation turns are sent to MuninnDB for:
- Context tracking
- Learning from interactions
- Surfacing relevant artifacts

### Implementation

```python
# copaw_muninn_integration.py
import aiohttp
import json
from datetime import datetime

class CopawMuninnBridge:
    """Bridge Copaw conversations to MuninnDB"""
    
    def __init__(self, muninn_url: str = "http://localhost:8098"):
        self.muninn_url = muninn_url
        self.session = None
    
    async def log_conversation_turn(
        self,
        role: str,  # "user" or "assistant"
        content: str,
        session_id: str,
        tools_used: list = None,
        files_accessed: list = None,
    ):
        """Log a single conversation turn to MuninnDB"""
        
        engram = {
            "type": "conversation_turn",
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": {
                "tools_used": tools_used or [],
                "files_accessed": files_accessed or [],
            }
        }
        
        await self._send_engram(engram)
    
    async def _send_engram(self, engram: dict):
        """Send engram to MuninnDB via MCP"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        async with self.session.post(
            f"{self.muninn_url}/engrams",
            json=engram,
            headers={"Content-Type": "application/json"}
        ) as resp:
            if resp.status != 200:
                print(f"Failed to send engram: {await resp.text()}")
    
    async def close(self):
        if self.session:
            await self.session.close()
```

### Pub/Sub Integration

```python
# pubsub_listener.py
from google.cloud import pubsub_v1
import json

class MuninnPubSubListener:
    """Listen to GCP Pub/Sub and store all events in MuninnDB"""
    
    def __init__(
        self,
        project_id: str,
        subscription_id: str,
        muninn_url: str = "http://localhost:8098",
    ):
        self.project_id = project_id
        self.subscription_id = subscription_id
        self.muninn_url = muninn_url
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(
            project_id, subscription_id
        )
    
    def start_listening(self):
        """Start listening to Pub/Sub events"""
        
        def callback(message: pubsub_v1.subscriber.message.Message):
            event = json.loads(message.data.decode("utf-8"))
            
            # Create engram from event
            engram = {
                "type": f"pubsub.{event.get('event_type', 'unknown')}",
                "timestamp": event.get("timestamp"),
                "source": event.get("source"),
                "data": event.get("data"),
                "attributes": event.get("attributes", {}),
            }
            
            # Send to MuninnDB
            self._send_to_muninn(engram)
            
            message.ack()
        
        streaming_pull_future = self.subscriber.subscribe(
            self.subscription_path, callback=callback
        )
        
        print(f"Listening on {self.subscription_path}...")
        
        with self.subscriber:
            try:
                streaming_pull_future.result()
            except TimeoutError:
                streaming_pull_future.cancel()
    
    def _send_to_muninn(self, engram: dict):
        """Send engram to MuninnDB"""
        import requests
        
        resp = requests.post(
            f"{self.muninn_url}/engrams",
            json=engram,
            headers={"Content-Type": "application/json"}
        )
        
        if resp.status_code != 200:
            print(f"Failed to send engram: {resp.text}")
```

---

## Deployment Checklist

### MemU (Cloud Run)
- [ ] Build Docker image
- [ ] Push to GCR
- [ ] Deploy to Cloud Run
- [ ] Set environment variables
- [ ] Configure secrets
- [ ] Test MCP endpoint
- [ ] Verify Qdrant connection
- [ ] Verify Firebase connection
- [ ] Test Gemini embeddings
- [ ] Test Gemma 4 agent

### Global MuninnDB (GCP e2-micro)
- [ ] Create e2-micro VM
- [ ] Attach 30GB persistent disk
- [ ] Run install script
- [ ] Configure Pub/Sub subscription
- [ ] Configure Hebbian learning
- [ ] Configure ACT-R parameters
- [ ] Test MCP endpoint
- [ ] Verify event streaming
- [ ] Test memory retrieval

### Local MuninnDB (Docker)
- [ ] Create Dockerfile
- [ ] Create docker-compose.yml
- [ ] Test local deployment
- [ ] Integrate with Serena MCP
- [ ] Configure transient tracking
- [ ] Test auto-flush

### Copaw Integration
- [ ] Add Muninn bridge to Copaw config
- [ ] Configure conversation logging
- [ ] Test Pub/Sub listener
- [ ] Verify all events logged
- [ ] Test memory surfacing

---

## Next Steps

1. **Deploy MemU to Cloud Run**
2. **Set up Global MuninnDB on e2-micro**
3. **Deploy Local MuninnDB**
4. **Integrate with Copaw**
5. **Test end-to-end flow**

---

## Cost Estimate

| Service | Monthly Cost |
|---------|-------------|
| MemU (Cloud Run) | $0-5 |
| Global MuninnDB (e2-micro + 30GB) | $10-15 |
| Local MuninnDB | $0 |
| Qdrant Cloud | $0-25 (free tier) |
| Firebase | $0 (free tier) |
| **Total** | **$10-45/mo** |

---

**Ready to deploy?** Let me know which component to start with!
