# ARCA MCP Server - Standard Configuration Documentation

## Overview
The ARCA MCP (Model Context Protocol) Server is a critical component providing reasoning skills, tools, and coordination capabilities to the ARCA system. This document defines the **standard, persistent configuration** to prevent data loss on container restarts/rebuilds.

---

## Container Configuration

### Service Name
- **Container Name**: `mcp_server`
- **Service Name in compose**: `mcp_server`
- **Image**: Built from `./services/mcp_server/Dockerfile`

### Network
- **Network**: `arca_net`
- **Port Mapping**: `8086:8086`
- **Internal Port**: `8086`

---

## Volume Mounts (PERSISTENT - DO NOT CHANGE)

### Critical Data Volumes
These mounts MUST be present for data persistence:

| Host Path | Container Path | Mode | Purpose |
|-----------|---------------|------|---------|
| `./databases` | `/app/data` | `rw` | **Skills registry, learning events, persistent data** |
| `./mcp_skills` | `/app/skills` | `ro` | **Markdown skill definitions (40+ skills)** |
| `./shared_storage/reasoning_bank` | `/app/reasoning_bank` | `rw` | **Reasoning trajectories and learning data** |
| `./tools` | `/app/tools` | `ro` | **MCP tool modules (21 tools)** |
| `./shared` | `/shared` | `ro` | **Shared configs including model_config.py** |
| `./shared_storage` | `/app/shared_storage` | `rw` | **Additional shared persistent storage** |
| `./cache/mcp` | `/app/cache` | `rw` | **Model/embedding cache** |
| `./logs/mcp` | `/app/logs` | `rw` | **Server logs** |
| `./mcp_storage` | `/mnt/mcp_storage` | `rw` | **MCP-specific storage (certs, etc.)** |

### Volume Configuration in docker-compose.local.yml
```yaml
volumes:
  - ./databases:/app/data                              # PRIMARY DATA - Skills registry
  - ./mcp_skills:/app/skills:ro                        # Skill definitions  
  - ./shared_storage/reasoning_bank:/app/reasoning_bank # Reasoning trajectories
  - ./tools:/app/tools:ro                               # Tool modules
  - ./shared:/shared:ro                                 # Shared configs
  - ./shared_storage:/app/shared_storage               # General shared storage
  - ./cache/mcp:/app/cache                             # Cache
  - ./logs/mcp:/app/logs                               # Logs
  - ./mcp_storage:/mnt/mcp_storage                     # MCP storage
```

---

## Environment Variables

### Required Environment Variables
```bash
PORT=8086                                    # Server port
MCP_DATA_DIR=/app/data                       # Primary data directory
MCP_SKILLS_DIR=/app/skills                   # Skills directory
MCP_REASONING_DIR=/app/reasoning_bank        # Reasoning directory
TOOLS_DIR=/app/tools                         # Tools directory
ARCA_ROOT=/app                               # Application root

# Service URLs
LLM_GATEWAY_URL=http://llm_gateway:8080/v1/chat/completions
EMBEDDING_SERVICE_URL=http://embedding_service:8005
MEMORY_SYSTEM_URL=http://memory_system:8001

# TLS Configuration
MCP_TLS_ENABLED=false                        # TLS disabled for local
TLS_ENABLED=false
MCP_CERT_DIR=/mnt/mcp_storage/certs

# API Keys (loaded from .env or secrets)
GOOGLE_API_KEY=${GOOGLE_API_KEY:-}
OPENAI_API_KEY=${OPENAI_API_KEY:-}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}

# Learning Configuration
LEARNING_MODEL=learnlm-2.0-flash-experimental
```

---

## Data Persistence Strategy

### Skills Registry
- **Location**: `/app/data/skills_registry_enhanced.json` (40 skills)
- **Backup**: `/app/data/skills_registry.json` (synchronized on startup)
- **Source of Truth**: `data/skills/skills_registry_enhanced.json` on host
- **Persistence**: Survives container restarts via `./databases` mount

### Markdown Skills
- **Location**: `/app/skills/*.md` (44 markdown files)
- **Source**: `./mcp_skills/` on host
- **Mount**: Read-only to prevent accidental modification
- **Persistence**: Always available from host filesystem

### Tools
- **Location**: `/app/tools/mcp_*.py` (21 tool modules)
- **Source**: `./tools/` on host
- **Mount**: Read-only to prevent modification
- **Persistence**: Always available from host filesystem

### Reasoning Bank
- **Location**: `/app/reasoning_bank/*.json`
- **Source**: `./shared_storage/reasoning_bank/` on host
- **Persistence**: Full read-write access, survives restarts

---

## Initialization Process

### Startup Sequence
1. **Pre-initialization**: `init_mcp_server.sh` runs before main server
2. **Validation**: Checks all required directories and mounts exist
3. **Synchronization**: Ensures `skills_registry.json` is current
4. **Counting**: Reports skills/tools/reasoning trajectory counts
5. **Health Check**: Validates writable directories
6. **Server Start**: Launches main MCP server

### Initialization Script
- **Location**: `services/mcp_server/init_mcp_server.sh`
- **Called from**: Dockerfile `ENTRYPOINT` or docker-compose `command`
- **Purpose**: Ensure data consistency before server starts

---

## Resource Limits

### Memory Configuration
```yaml
deploy:
  resources:
    limits:
      memory: 1.5G        # Hard limit
    reservations:
      memory: 1G          # Soft reservation
```

### Health Check
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8086/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

---

## Critical Files That Must Persist

### On Host (Source of Truth)
1. `data/skills/skills_registry_enhanced.json` - Master skills registry (40 skills)
2. `mcp_skills/*.md` - Markdown skill definitions (44 files)
3. `tools/mcp_*.py` - Tool implementations (21 tools)
4. `shared/model_config.py` - Centralized model configuration

### In Container (Via Mounts)
1. `/app/data/skills_registry_enhanced.json` - Loaded skills registry
2. `/app/data/skills_registry.json` - Server-compatible format
3. `/app/skills/*.md` - Accessible skill docs
4. `/app/tools/mcp_*.py` - Loaded tool modules
5. `/app/reasoning_bank/*.json` - Reasoning trajectories

---

## Endpoints

### Standard Endpoints (DO NOT CHANGE)
- **Health**: `GET http://localhost:8086/health`
- **Root**: `GET http://localhost:8086/` (ARCA MCP Reasoning Hub info)
- **Tools Status**: `GET http://localhost:8086/tools/status`
- **Skills Dashboard**: `GET http://localhost:8086/skills/dashboard`
- **MCP Protocol**: `POST http://localhost:8086/mcp`

### Expected Response Counts
- **Skills**: 40+ (from enhanced registry)
- **Tools**: 21 total (9+ should load successfully)
- **Categories**: 5 (reasoning, technical, creative, meta, communication)

---

## Rebuild/Restart Procedures

### Safe Restart (Preserves Data)
```bash
docker-compose -f docker-compose.local.yml restart mcp_server
```

### Rebuild (Data Persists via Volumes)
```bash
docker-compose -f docker-compose.local.yml up -d --build mcp_server
```

### Full Reset (⚠️ DANGEROUS - Only for Debugging)
```bash
# Stop and remove container
docker-compose -f docker-compose.local.yml down mcp_server

# Optionally backup data
cp -r databases databases.backup

# Rebuild
docker-compose -f docker-compose.local.yml up -d --build mcp_server
```

### Validation After Restart
```bash
# Wait for health check
sleep 10

# Verify skills count
curl -s http://localhost:8086/skills/dashboard | python -m json.tool | grep total_skills

# Verify tools count  
curl -s http://localhost:8086/tools/status | python -m json.tool | grep -A 25 tools_loaded

# Expected: 40+ skills, 21 tools (9+ loaded)
```

---

## Troubleshooting

### Issue: Skills Count Drops to 22 After Restart
**Root Cause**: Server loads from `skills_registry.json` but enhanced registry not synchronized

**Fix**:
```bash
# On host
cp data/skills/skills_registry_enhanced.json databases/skills_registry.json
docker-compose -f docker-compose.local.yml restart mcp_server
```

**Prevention**: Ensure `init_mcp_server.sh` runs on startup

### Issue: Tools Not Loading (Only 9/21)
**Root Cause**: Missing dependencies or import errors in tool modules

**Diagnosis**:
```bash
docker logs mcp_server | grep "⚠️.*unavailable"
```

**Fix**: Check specific tool module for dependency issues

### Issue: Reasoning Bank Empty
**Root Cause**: Volume mount not configured or wrong path

**Fix**:
```bash
# Verify mount exists
docker inspect mcp_server | grep reasoning_bank

# Should show:
# "Source": ".../shared_storage/reasoning_bank"
# "Destination": "/app/reasoning_bank"
```

---

## Dependencies

### Required Services (must be running)
- `llm_gateway` - LLM completion endpoint
- `embedding_service` - Embedding generation
- `memory_system` - Episodic memory storage

### Optional Services
- `neo4j` - Structural memory (for advanced reasoning)
- `redis` - Caching (improves performance)

---

## Monitoring

### Health Checks
```bash
# Container health
docker ps | grep mcp_server

# Endpoint health
curl http://localhost:8086/health

# Skills loaded
curl http://localhost:8086/skills/dashboard

# Tools loaded
curl http://localhost:8086/tools/status
```

### Logs
```bash
# Real-time logs
docker logs -f mcp_server

# Startup logs
docker logs mcp_server | grep "Initialization"

# Error logs
docker logs mcp_server | grep -E "(ERROR|WARN)"
```

---

## Version Control

### Configuration Files Under Git
- `docker-compose.local.yml` - Container configuration
- `services/mcp_server/Dockerfile` - Image definition
- `services/mcp_server/init_mcp_server.sh` - Initialization script
- `services/mcp_server/mcp_server.py` - Main server code

### Data Files (Gitignored, Persisted via Volumes)
- `databases/skills_registry*.json` - Runtime skills data
- `logs/mcp/*` - Log files
- `cache/mcp/*` - Cache files
- `mcp_storage/*` - MCP-specific storage

---

## Summary Checklist

✅ **MUST HAVE for Persistence:**
- [ ] `databases` → `/app/data` mount (skills registry)
- [ ] `mcp_skills` → `/app/skills` mount (skill docs)
- [ ] `tools` → `/app/tools` mount (tool modules)
- [ ] `init_mcp_server.sh` runs on startup
- [ ] `skills_registry_enhanced.json` exists in `databases/`

✅ **VERIFY After Restart:**
- [ ] Health endpoint returns 200
- [ ] Skills count ≥ 40
- [ ] Tools count = 21 (≥9 loaded)
- [ ] No mount errors in logs

---

**Last Updated**: 2025-12-22  
**Configuration Version**: 1.0.0  
**Maintained By**: ARCA Infrastructure Team
