# Quick Build Instructions (MacBook)

## Prerequisites
- Docker Desktop installed and running
- `docker buildx` available (comes with Docker Desktop)

## Simple 3-Step Process

### Step 1: Build the Image
```bash
cd /path/to/ARCA/services/user_interaction_agent

# Build for linux/amd64 (GCP server architecture)
docker buildx build --platform linux/amd64 \
  -t arca-user-interaction-agent:latest \
  --load .
```

**Troubleshooting Build Issues:**
- If `buildx` not found: `docker buildx create --use`
- If `--load` fails: Remove `--platform` flag and build for native arch
- If build is slow: Use Option 2 below

### Step 2: Save and Transfer
```bash
# Save image to file
docker save arca-user-interaction-agent:latest | gzip > arca-agent.tar.gz

# Copy to GCP (replace with your GCP details)
scp arca-agent.tar.gz user@your-gcp-ip:~/

# Clean up local file
rm arca-agent.tar.gz
```

### Step 3: Load and Run on GCP
```bash
# SSH to GCP
ssh user@your-gcp-ip

# Load the image
docker load < ~/arca-agent.tar.gz
rm ~/arca-agent.tar.gz

# Deploy
cd ~/ARCA/services/user_interaction_agent
docker-compose down
docker-compose up -d

# Check logs
docker logs -f user_interaction_agent
```

---

## Alternative: Direct Build on GCP

If MacBook build is too slow or has issues:

```bash
# SSH to GCP
ssh user@your-gcp-ip

# Pull latest code
cd ~/ARCA
git pull

# Build directly on GCP
cd services/user_interaction_agent
docker build -t arca-user-interaction-agent:latest .

# Deploy
docker-compose down
docker-compose up -d
```

---

## Automated Script

Use the provided script:
```bash
export GCP_HOST="user@your-gcp-ip"
./build_and_deploy.sh
```

---

## No Docker Registry Required!

This approach **does not** require:
- GitHub Container Registry (ghcr.io) authentication
- Docker Hub account
- Any container registry setup

Just build locally and transfer the image file directly.

---

## Verification

After deployment, verify the service:
```bash
# Check if running
docker ps | grep user_interaction_agent

# Test health endpoint
curl http://localhost:8084/health

# View logs
docker logs --tail 50 user_interaction_agent
```

Expected health response:
```json
{
  "status": "healthy",
  "service": "user_interaction_agent",
  "version": "3.0.0",
  "features": {
    "psutil": true,
    "docker": true,
    "minimax": true,
    "mcp": true
  }
}
```

---

## Environment Variables

Make sure `.env` file has correct OCI IP:
```bash
AGENT_SERVICE_URL=http://141.147.85.137:8000
```

If OCI IP changes, update `.env` and restart:
```bash
docker-compose down
docker-compose up -d
```
