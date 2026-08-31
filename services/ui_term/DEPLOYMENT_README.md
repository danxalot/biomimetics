# User Interaction Agent - Deployment Guide

## Overview
The User Interaction Agent is a FastAPI-based service that provides a web UI and API for interacting with the ARCA agent system. It runs on GCP and connects to the agent_service on OCI.

## Version
**v3.0.0** - Updated 2025-11-08

## Features
- ✅ WebSocket real-time communication
- ✅ System telemetry monitoring (CPU, memory, Docker stats)
- ✅ MiniMax AI reasoning integration
- ✅ Genesis thread management
- ✅ REST API endpoints
- ✅ MCP tool integration

## Architecture
```
GCP: user_interaction_agent (port 8084)
  ↓ HTTPS/HTTP
OCI: agent_service (port 8000) → 141.147.85.137:8000
```

## Critical Configuration

### Environment Variables
Set these when deploying to GCP:

```bash
# Required: Point to OCI agent_service
export AGENT_SERVICE_URL=http://141.147.85.137:8000

# Optional: Override defaults
export USER_AGENT_PORT=8084
export MCP_SERVER_URL=http://localhost:8085
```

### Docker Build Command
```bash
cd /home/ubuntu/ARCA/services/user_interaction_agent
docker build -t arca-user_interaction_agent:v3.0.0 .
```

### Docker Run Command (GCP)
```bash
docker run -d \
  --name user_interaction_agent \
  -p 8084:8084 \
  -e AGENT_SERVICE_URL=http://141.147.85.137:8000 \
  -e USER_AGENT_PORT=8084 \
  -e MCP_SERVER_URL=http://localhost:8085 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  --restart unless-stopped \
  arca-user_interaction_agent:v3.0.0
```

## Files Updated in v3.0.0

### 1. main.py (484 lines)
- Added system telemetry with psutil + docker SDK
- Implemented all WebSocket message handlers
- Added 8 new REST API endpoints
- Integrated MiniMax reasoning
- Enhanced error handling with graceful fallbacks
- Background telemetry cache updates (5s interval)

### 2. minimax_reasoning_integration.py (371 lines)
- Fixed missing headers/payload bug in _call_minimax_api()
- MCP tool client integration
- Iterative reasoning workflow
- Tool execution support

### 3. requirements.txt
Added:
- psutil>=5.9.0 (system metrics)
- docker>=6.1.0 (container stats)

### 4. Dockerfile
- Fixed port configuration (8084)
- Added Docker socket support
- Uses USER_AGENT_PORT env var

## API Endpoints

### Health & Info
- `GET /health` - Service health check
- `GET /` - Serve web UI

### Chat & Messaging
- `POST /api/chat` - Send chat message
- `WebSocket /ws` - Real-time communication

### Telemetry
- `GET /api/telemetry` - System metrics (CPU, memory, Docker stats)

### Genesis Thread Management
- `POST /api/genesis/thread/{id}/pause` - Pause thread
- `POST /api/genesis/thread/{id}/resume` - Resume thread
- `GET /api/genesis/thread/{id}/status` - Get thread status

### MiniMax Reasoning
- `POST /api/reasoning/analyze` - Analyze with MiniMax
- `GET /api/reasoning/proposals` - List proposals
- `POST /api/reasoning/approve/{id}` - Approve proposal

### Interpreter
- `POST /api/interpreter/execute` - Execute command (stub)

## WebSocket Message Types

### Client → Server
- `chat` - Chat message
- `message` - General message
- `interpreter_request` - Interpreter command
- `genesis_message` - Genesis system message
- `telemetry_request` - Request system metrics
- `thread_status_request` - Request thread status
- `pause_thread` - Pause Genesis thread
- `resume_thread` - Resume Genesis thread
- `interpreter_reset` - Reset interpreter

### Server → Client
- `response` - Agent response
- `telemetry` - System metrics data
- `thread_status` - Thread status info
- `confirmation` - Action confirmation

## Testing

### Test Health
```bash
curl http://localhost:8084/health
```

Expected response:
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

### Test Telemetry
```bash
curl http://localhost:8084/api/telemetry
```

### Test Chat (connects to OCI agent_service)
```bash
curl -X POST http://localhost:8084/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello ARCA!", "session_id": "test-001"}'
```

## Troubleshooting

### "Agent service is currently unavailable"
This means the GCP service cannot reach the OCI agent_service.

**Check:**
1. Verify AGENT_SERVICE_URL is set correctly:
   ```bash
   docker exec user_interaction_agent env | grep AGENT_SERVICE_URL
   ```
   Should show: `AGENT_SERVICE_URL=http://141.147.85.137:8000`

2. Test connectivity from GCP to OCI:
   ```bash
   curl -v http://141.147.85.137:8000/docs
   ```

3. Verify OCI port 8000 is open:
   - Check OCI security list allows inbound TCP 8000
   - Check OCI firewall: `sudo iptables -L | grep 8000`

4. Verify agent_service is running on OCI:
   ```bash
   # On OCI server
   docker ps | grep agent_service
   curl http://localhost:8000/docs
   ```

### No telemetry data
Requires Docker socket access:
```bash
docker run ... -v /var/run/docker.sock:/var/run/docker.sock:ro ...
```

### WebSocket connection fails
Check CORS settings and ensure port 8084 is accessible.

## Deployment Checklist

- [ ] Update AGENT_SERVICE_URL to OCI public IP
- [ ] Verify OCI port 8000 is accessible from GCP
- [ ] Build Docker image with v3.0.0 tag
- [ ] Mount Docker socket for telemetry
- [ ] Verify health endpoint responds
- [ ] Test chat endpoint connects to OCI
- [ ] Verify no "unhandled message" warnings in logs
- [ ] Test WebSocket connection from browser
- [ ] Verify telemetry updates every 5 seconds

## Support Files

### docker-compose.yml (optional)
Create this for easier deployment:

```yaml
version: '3.8'

services:
  user_interaction_agent:
    image: arca-user_interaction_agent:v3.0.0
    container_name: user_interaction_agent
    ports:
      - "8084:8084"
    environment:
      - AGENT_SERVICE_URL=http://141.147.85.137:8000
      - USER_AGENT_PORT=8084
      - MCP_SERVER_URL=http://localhost:8085
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8084/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Deploy with:
```bash
docker-compose up -d
```

## Monitoring

### View Logs
```bash
docker logs -f user_interaction_agent
```

### Check Resource Usage
```bash
docker stats user_interaction_agent
```

### Verify Connectivity
```bash
# From GCP container
docker exec user_interaction_agent ping -c 3 141.147.85.137

# Test HTTP connection
docker exec user_interaction_agent wget -O- http://141.147.85.137:8000/docs
```

## Version History

### v3.0.0 (2025-11-08)
- Complete rewrite with comprehensive fixes
- Added system telemetry
- Implemented all WebSocket handlers
- Added 8 REST API endpoints
- Integrated MiniMax reasoning
- Fixed networking configuration for cross-cloud deployment

### v2.0.0 (Previous)
- Basic WebSocket support
- Limited API endpoints
- No telemetry

## Contact
For issues or questions, check the logs and verify network connectivity between GCP and OCI.
