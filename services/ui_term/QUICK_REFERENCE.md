# Quick Reference - User Interaction Agent v3.0.0

## TL;DR - Deploy from MacBook

```bash
cd /path/to/ARCA/services/user_interaction_agent
./build_and_deploy.sh
```

## Critical Environment Variable

```bash
AGENT_SERVICE_URL=http://141.147.85.137:8000
```

This points the GCP service to the OCI agent_service.

## One-Line Deploy (GCP)

```bash
docker run -d --name user_interaction_agent -p 8084:8084 \
  -e AGENT_SERVICE_URL=http://141.147.85.137:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  --restart unless-stopped arca-user_interaction_agent:v3.0.0
```

## Test Commands

```bash
# Health check
curl http://localhost:8084/health

# Telemetry
curl http://localhost:8084/api/telemetry

# Chat (tests OCI connection)
curl -X POST http://localhost:8084/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "session_id": "test"}'
```

## Common Issues

### "Agent service is currently unavailable"
**Problem:** Cannot reach OCI agent_service from GCP

**Fix:**
1. Check AGENT_SERVICE_URL env var is set
2. Verify OCI port 8000 is open:
   ```bash
   # From GCP
   curl http://141.147.85.137:8000/docs
   ```
3. Check OCI security list allows TCP 8000
4. Verify agent_service is running on OCI

### No Telemetry Data
**Problem:** Docker socket not mounted

**Fix:**
```bash
-v /var/run/docker.sock:/var/run/docker.sock:ro
```

## Files Updated

✅ `main.py` - Fixed (484 lines, v3.0.0)
✅ `minimax_reasoning_integration.py` - Fixed API bug
✅ `requirements.txt` - Added psutil, docker
✅ `Dockerfile` - Fixed port config
✅ `.env.production` - NEW
✅ `docker-compose.production.yml` - NEW
✅ `build_and_deploy.sh` - NEW
✅ `DEPLOYMENT_README.md` - NEW

## API Endpoints (8 new in v3.0.0)

- GET `/health` - Health check
- GET `/api/telemetry` - System metrics
- POST `/api/chat` - Chat with agent
- POST `/api/genesis/thread/{id}/pause`
- POST `/api/genesis/thread/{id}/resume`
- GET `/api/genesis/thread/{id}/status`
- POST `/api/reasoning/analyze` - MiniMax analysis
- GET `/api/reasoning/proposals`
- POST `/api/reasoning/approve/{id}`
- POST `/api/interpreter/execute`

## WebSocket (ws://localhost:8084/ws)

Supported message types:
- chat, message, interpreter_request
- genesis_message, telemetry_request
- thread_status_request, pause_thread
- resume_thread, interpreter_reset

All message types now handled (0 warnings).

## Architecture

```
┌─────────────────────┐
│ GCP: MacBook/Cloud  │
│  user_interaction   │ Port 8084
│  agent v3.0.0       │
└──────────┬──────────┘
           │ HTTP
           ▼
┌─────────────────────┐
│ OCI: 141.147.85.137 │
│  agent_service      │ Port 8000
│                     │
└─────────────────────┘
```

## Verification Checklist

- [ ] Built Docker image v3.0.0
- [ ] Set AGENT_SERVICE_URL=http://141.147.85.137:8000
- [ ] Deployed to GCP
- [ ] Health check returns v3.0.0
- [ ] Telemetry returns real data
- [ ] Chat connects to OCI (no "unavailable" message)
- [ ] Zero "unhandled message" warnings in logs
- [ ] WebSocket connections work

## Support

Logs: `docker logs -f user_interaction_agent`
Test OCI: `curl http://141.147.85.137:8000/docs`
