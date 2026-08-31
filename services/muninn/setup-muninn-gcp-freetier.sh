#!/bin/bash
# setup-muninn-gcp.sh - Deploy MuninnDB to GCP e2-micro (FREE TIER)
# 2GB storage, same region as ARCA project

set -e

PROJECT_ID="arca-471022"
REGION="us-central1"  # Existing ARCA region
ZONE="${REGION}-c"
INSTANCE_NAME="muninn-global"
DISK_SIZE="10"  # 10GB minimum for boot disk
MACHINE_TYPE="e2-micro"

echo "=================================="
echo "Setting up MuninnDB Global"
echo "FREE TIER CONFIGURATION"
echo "=================================="
echo ""

# Set project
gcloud config set project ${PROJECT_ID}

# Check if instance exists
echo "Checking for existing instance..."
if gcloud compute instances describe ${INSTANCE_NAME} --zone=${ZONE} &> /dev/null; then
    echo "⚠️  Instance ${INSTANCE_NAME} already exists!"
    echo "Delete it first with:"
    echo "  gcloud compute instances delete ${INSTANCE_NAME} --zone=${ZONE}"
    exit 1
fi

# Create startup script
cat > /tmp/muninn-startup.sh << 'STARTUP_SCRIPT'
#!/bin/bash
# MuninnDB startup script

set -e

# Install dependencies
apt-get update
apt-get install -y python3-pip python3-venv

# Create MuninnDB directory
mkdir -p /home/ubuntu/muninn-global/data
cd /home/ubuntu/muninn-global

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install MuninnDB and dependencies
pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    aiohttp \
    google-cloud-pubsub \
    google-cloud-monitoring

# Create config with free tier limits
cat > config.json <<EOF
{
  "instance_id": "muninn-global-gcp",
  "storage_path": "/home/ubuntu/muninn-global/data",
  "max_storage_gb": 2,
  "pubsub": {
    "project_id": "${PROJECT_ID}",
    "subscription_id": "muninn-global-events",
    "topics": ["os-events"]
  },
  "hebbian_learning": {
    "enabled": true,
    "decay_rate": 0.01,
    "reinforcement_threshold": 0.5,
    "max_engrams": 50000
  },
  "act_r": {
    "enabled": true,
    "base_level_activation": 0.5,
    "retrieval_threshold": 0.3
  },
  "mcp": {
    "port": 8097,
    "host": "0.0.0.0"
  },
  "quotas": {
    "monthly_requests": 100000,
    "storage_gb": 2,
    "alert_threshold": 0.75
  }
}
EOF

# Create MuninnDB server script
cat > muninn_server.py << \'PYTHON_SCRIPT\'
#!/usr/bin/env python3
"""MuninnDB Server - FREE TIER with quota monitoring"""

import os
import json
import asyncio
import time
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import aiohttp
from google.cloud import pubsub_v1
from google.cloud import monitoring_v3

# Configuration
@dataclass
class MuninnConfig:
    instance_id: str = "muninn-gcp"
    storage_path: str = "./data"
    max_storage_gb: float = 2.0
    
    # Pub/Sub configuration
    pubsub_project_id: str = "arca-471022"
    pubsub_subscription_id: str = "muninn-global-events"
    
    # Hebbian learning parameters
    hebbian_learning_rate: float = 0.1
    hebbian_decay_rate: float = 0.01
    hebbian_retrieval_threshold: float = 0.3
    hebbian_max_connections: int = 100
    hebbian_coactivation_window: float = 300
    hebbian_reinforcement_multiplier: float = 1.5
    max_engrams: int = 50000
    
    # ACT-R parameters
    act_r_decay_rate: float = 0.5
    act_r_retrieval_threshold: float = 0.3
    act_r_associative_strength: float = 2.0
    
    # MCP server
    mcp_port: int = 8097
    mcp_host: str = "0.0.0.0"
    
    # Quotas
    monthly_requests: int = 100000
    storage_gb: float = 2.0
    alert_threshold: float = 0.75


@dataclass
class Engram:
    id: str
    type: str
    timestamp: str
    content: Dict[str, Any]
    activation: float = 1.0
    last_accessed: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    access_count: int = 0
    connections: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


class MuninnDB:
    def __init__(self, config: MuninnConfig):
        self.config = config
        self.storage_path = Path(config.storage_path)
        self.engrams: Dict[str, Engram] = {}
        self.request_count = 0
        self.monthly_reset = datetime.utcnow().replace(day=1)
        self._load()
        self._check_quotas()
    
    def _load(self):
        engrams_file = self.storage_path / "engrams.json"
        if engrams_file.exists():
            with open(engrams_file, "r") as f:
                data = json.load(f)
                self.engrams = {k: Engram.from_dict(v) for k, v in data.items()}
            print(f"✅ Loaded {len(self.engrams)} engrams")
    
    def _save(self):
        self.storage_path.mkdir(parents=True, exist_ok=True)
        engrams_file = self.storage_path / "engrams.json"
        
        # Check storage limit before saving
        current_size = sum(e.size_bytes for e in self.engrams.values())
        max_size = self.config.max_storage_gb * 1024 * 1024 * 1024
        
        if current_size > max_size * 0.9:
            print("⚠️  Storage at 90% - applying aggressive cleanup")
            self._cleanup_old_engrams()
        
        with open(engrams_file, "w") as f:
            json.dump({k: v.to_dict() for k, v in self.engrams.items()}, f, indent=2)
        
        # Update size tracking
        self._update_storage_size()
    
    def _update_storage_size(self):
        engrams_file = self.storage_path / "engrams.json"
        if engrams_file.exists():
            size = engrams_file.stat().st_size
            size_gb = size / (1024 * 1024 * 1024)
            if size_gb > self.config.storage_gb * self.config.alert_threshold:
                print(f"⚠️  STORAGE ALERT: {size_gb:.2f}GB / {self.config.storage_gb}GB")
                self._send_quota_alert("storage", size_gb / self.config.storage_gb)
    
    def _cleanup_old_engrams(self):
        """Remove lowest activation engrams to stay under limit"""
        sorted_engrams = sorted(
            self.engrams.items(),
            key=lambda x: x[1].activation
        )
        
        # Remove bottom 10%
        to_remove = len(sorted_engrams) // 10
        for engram_id, _ in sorted_engrams[:to_remove]:
            del self.engrams[engram_id]
        
        print(f"🗑️  Removed {to_remove} low-activation engrams")
        self._save()
    
    def _check_quotas(self):
        """Check if we've exceeded monthly quotas"""
        now = datetime.utcnow()
        
        # Reset monthly counter if new month
        if now.month > self.monthly_reset.month:
            self.request_count = 0
            self.monthly_reset = now.replace(day=1)
        
        # Check request quota
        if self.request_count > self.config.monthly_requests * self.config.alert_threshold:
            self._send_quota_alert("requests", self.request_count / self.config.monthly_requests)
    
    def _send_quota_alert(self, metric: str, usage_ratio: float):
        """Send alert when quota usage exceeds threshold"""
        print(f"🚨 QUOTA ALERT: {metric} at {usage_ratio*100:.1f}%")
        
        # Log to Cloud Monitoring
        try:
            client = monitoring_v3.MetricServiceClient()
            project_name = f"projects/{self.config.pubsub_project_id}"
            
            series = monitoring_v3.TimeSeries()
            series.metric.type = "custom.googleapis.com/muninn/quota_usage"
            series.metric.labels["metric_type"] = metric
            series.resource.type = "gce_instance"
            series.resource.labels["instance_id"] = self.config.instance_id
            
            now = time.time()
            point = series.points.add()
            point.value.double_value = usage_ratio
            point.interval.end_time.seconds = int(now)
            point.interval.end_time.nanos = int((now % 1) * 1e9)
            
            client.create_time_series(name=project_name, time_series=[series])
        except Exception as e:
            print(f"Failed to send monitoring alert: {e}")
    
    def add_engram(self, engram: Engram):
        # Check max engrams limit
        if len(self.engrams) >= self.config.max_engrams:
            print("⚠️  Max engrams reached - applying cleanup")
            self._cleanup_old_engrams()
        
        # Calculate approximate size
        engram.size_bytes = len(json.dumps(engram.to_dict()))
        
        self.engrams[engram.id] = engram
        self.request_count += 1
        
        self._check_quotas()
        self._apply_hebbian_learning(engram)
        self._save()
    
    def _apply_hebbian_learning(self, new_engram: Engram):
        now = datetime.utcnow()
        window = timedelta(seconds=self.config.hebbian_coactivation_window)
        
        recent_engrams = []
        for engram_id, engram in self.engrams.items():
            if engram_id == new_engram.id:
                continue
            
            last_accessed = datetime.fromisoformat(engram.last_accessed)
            if now - last_accessed <= window:
                recent_engrams.append(engram)
        
        for recent in recent_engrams[:self.config.hebbian_max_connections]:
            connection_strength = self.config.hebbian_learning_rate
            
            new_engram.connections[recent.id] = (
                new_engram.connections.get(recent.id, 0) + connection_strength
            )
            recent.connections[new_engram.id] = (
                recent.connections.get(new_engram.id, 0) + connection_strength
            )
    
    def retrieve_engram(self, engram_id: str) -> Optional[Engram]:
        engram = self.engrams.get(engram_id)
        if engram:
            engram.access_count += 1
            engram.last_accessed = datetime.utcnow().isoformat()
            engram.activation = min(
                1.0,
                engram.activation * self.config.hebbian_reinforcement_multiplier
            )
            self.request_count += 1
            self._check_quotas()
            self._save()
        return engram
    
    def search_by_relevance(self, query: str = None, limit: int = 10) -> List[Engram]:
        self.request_count += 1
        self._check_quotas()
        
        now = datetime.utcnow()
        scored_engrams = []
        
        for engram in self.engrams.values():
            last_accessed = datetime.fromisoformat(engram.last_accessed)
            time_diff_hours = (now - last_accessed).total_seconds() / 3600
            
            base_activation = math.log(
                (time_diff_hours + 1) ** (-self.config.act_r_decay_rate)
            )
            
            associative_activation = 0
            for connected_id, strength in engram.connections.items():
                connected_engram = self.engrams.get(connected_id)
                if connected_engram:
                    associative_activation += strength * connected_engram.activation
            
            associative_activation = min(
                self.config.act_r_associative_strength,
                associative_activation
            )
            
            total_activation = base_activation + self.config.act_r_associative_strength + associative_activation
            engram.activation = max(0, engram.activation - (time_diff_hours * self.config.hebbian_decay_rate))
            
            scored_engrams.append((total_activation, engram))
        
        scored_engrams.sort(key=lambda x: x[0], reverse=True)
        
        return [engram for _, engram in scored_engrams[:limit] if engram.activation >= self.config.hebbian_retrieval_threshold]
    
    def get_stats(self) -> Dict[str, Any]:
        current_size = sum(e.size_bytes for e in self.engrams.values())
        size_gb = current_size / (1024 * 1024 * 1024)
        
        return {
            "total_engrams": len(self.engrams),
            "active_engrams": sum(1 for e in self.engrams.values() if e.activation >= self.config.hebbian_retrieval_threshold),
            "storage_used_gb": round(size_gb, 3),
            "storage_limit_gb": self.config.storage_gb,
            "storage_usage_percent": round((size_gb / self.config.storage_gb) * 100, 2),
            "monthly_requests": self.request_count,
            "monthly_limit": self.config.monthly_requests,
            "request_usage_percent": round((self.request_count / self.config.monthly_requests) * 100, 2),
            "quota_alert_threshold": self.config.alert_threshold * 100,
        }


# FastAPI App
app = FastAPI(title="MuninnDB Global", version="1.0.0")
config = MuninnConfig()
db = MuninnDB(config)


class EngramCreate(BaseModel):
    type: str
    content: Dict[str, Any]
    metadata: Dict[str, Any] = {}


@app.post("/engrams")
async def create_engram(engram_data: EngramCreate):
    import uuid
    engram = Engram(
        id=str(uuid.uuid4()),
        type=engram_data.type,
        timestamp=datetime.utcnow().isoformat(),
        content=engram_data.content,
        metadata=engram_data.metadata,
    )
    db.add_engram(engram)
    return {"id": engram.id, "status": "created"}


@app.get("/engrams/{engram_id}")
async def get_engram(engram_id: str):
    engram = db.retrieve_engram(engram_id)
    if not engram:
        raise HTTPException(status_code=404, detail="Engram not found")
    return engram.to_dict()


@app.get("/engrams")
async def search_engrams(q: str = None, limit: int = 10):
    results = db.search_by_relevance(query=q, limit=limit)
    return [r.to_dict() for r in results]


@app.get("/stats")
async def get_stats():
    return db.get_stats()


@app.post("/apply-decay")
async def apply_decay():
    db.apply_decay()
    return {"status": "decay applied"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.mcp_host, port=config.mcp_port)
PYTHON_SCRIPT

# Create systemd service
cat > /etc/systemd/system/muninn-global.service << EOF
[Unit]
Description=MuninnDB Global Memory Service (Free Tier)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/muninn-global
ExecStart=/home/ubuntu/muninn-global/venv/bin/python /home/ubuntu/muninn-global/muninn_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
systemctl daemon-reload
systemctl enable muninn-global
systemctl start muninn-global

echo "✅ MuninnDB Global installed and running"
STARTUP_SCRIPT

# Create instance with startup script
echo "Creating e2-micro instance in ${REGION}..."
gcloud compute instances create ${INSTANCE_NAME} \
  --zone=${ZONE} \
  --machine-type=${MACHINE_TYPE} \
  --boot-disk-size=${DISK_SIZE}GB \
  --boot-disk-type=pd-standard \
  --image-family=debian-11 \
  --image-project=debian-cloud \
  --metadata-from-file=startup-script=/tmp/muninn-startup.sh \
  --tags=http-server,https-server \
  --scopes=cloud-platform

# Wait for startup to complete
echo "Waiting for instance to start..."
sleep 30

# Get external IP
EXTERNAL_IP=$(gcloud compute instances describe ${INSTANCE_NAME} --zone=${ZONE} --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo ""
echo "=================================="
echo "✅ MuninnDB Global Deployed!"
echo "=================================="
echo ""
echo "Instance: ${INSTANCE_NAME}"
echo "Region: ${REGION}"
echo "Zone: ${ZONE}"
echo "External IP: ${EXTERNAL_IP}"
echo "MCP Port: 8097"
echo ""
echo "FREE TIER LIMITS:"
echo "  - e2-micro: 1GB RAM, 0.25 vCPU"
echo "  - Storage: 20GB (alert at 1.5GB)"
echo "  - Monthly requests: 100,000 (alert at 75%)"
echo "  - Engram limit: 50,000"
echo ""
echo "QUOTA MONITORING:"
echo "  - 75% threshold alerts enabled"
echo "  - Storage alerts at 90%"
echo "  - Check: gcloud monitoring channels list"
echo ""
echo "Test endpoint:"
echo "  curl http://${EXTERNAL_IP}:8097/stats"
echo ""
