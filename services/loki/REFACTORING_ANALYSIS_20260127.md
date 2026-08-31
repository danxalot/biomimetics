# ARCA Services Refactoring Analysis
**Date:** 27 January 2026  
**Analysis Scope:** All 50 services, Dockerfiles, requirements.txt patterns

---

## Phase A Summary ✅
**Status:** COMPLETE - All three target services now running cleanly with mounts

| Service | Issue | Fix | Status |
|---------|-------|-----|--------|
| `agent_service` | Old 4-day image, no Optional import | Added mount to ./services/agent_service | ✅ Running |
| `user_interaction_agent` | Import path wrong (shared.model_config) | Changed to local model_config import | ✅ Healthy |
| `resource_monitor` | Curl missing, health check broken | Added curl to Dockerfile.local, corrected port 9090 | ✅ Healthy |

---

## Refactoring Opportunities

### 1. Dependency Analysis

**Total Services:** 50  
**Services with requirements.txt:** ~45  
**Common Dependencies Found:**

| Package | Usage | Services | Refactor Priority |
|---------|-------|----------|-------------------|
| `pydantic` | 10 services | Config validation across all services | Layer 2 (Middleware) |
| `numpy` | 9 services | ML services (conversational_hdc, embedding, neural_system, etc.) | Layer 2 |
| `fastapi` | 8 services | Web framework for most services | Layer 2 |
| `uvicorn` | 7 services + variants | ASGI server | Layer 2 |
| `redis` | 6 services | Caching/state (memory_system, embedding, maintainer_agents, etc.) | Layer 2 |
| `httpx` | 6 services | Async HTTP client | Layer 2 |
| `requests` | 4 services | Sync HTTP client | Layer 2 |
| `python-dotenv` | 4 services | Environment config | Layer 2 |
| `opentelemetry-*` | 8+ services (scattered) | Observability/tracing | Layer 2 |

### 2. Top Candidates for Layered Refactoring

**Tier 1 (Immediate - by size & reusability):**
1. **agent_service** (45 deps, 13.4GB) → Can reduce to ~10 unique by layering
2. **maintainer_agents** (17+ deps, 18.5GB) → Phase 1 priority per strategy doc
3. **mcp_server** (33 deps, 8.49GB) → Core infrastructure dependency
4. **user_interaction_agent** (19 deps, 560MB) → Recently fixed, good candidate
5. **conversational_hdc** (13 deps, 12.1GB) → Phase 1 priority

**Tier 2 (Medium - moderate dependencies):**
- embedding_system (22 deps)
- sync (29 deps)
- neural_system (11 deps)
- memory_system (11 deps)
- observer_agent (10 deps)
- alert_manager (11 deps)

**Tier 3 (Low - few unique deps):**
- hse_encoder (20 deps)
- geometry_kernel
- policy_manager
- docker_helper

### 3. Layered Build Structure Recommendation

```
📦 Layer 1: Base Image (ghcr.io/danxalot/arca-base-python:latest)
├─ OS: Debian/Alpine slim
├─ Python: 3.11+ 
├─ System Packages: curl, git, build-essential, libpq-dev (for psycopg2)
├─ Size: ~200-300MB
└─ Update Frequency: MONTHLY (security patches)

📦 Layer 2: Middleware (ghcr.io/danxalot/arca-middleware:latest)
├─ FROM arca-base-python
├─ Core Python Packages:
│  ├─ pydantic (validation)
│  ├─ fastapi + uvicorn (web framework)
│  ├─ redis, httpx, requests (client libs)
│  ├─ python-dotenv (config)
│  ├─ opentelemetry-* (observability)
│  ├─ numpy, scipy (numerics)
│  ├─ google-generativeai (LLM)
│  └─ neo4j, psycopg2 (databases)
├─ ARCA Shared Code:
│  ├─ /app/shared/model_config.py
│  ├─ /app/shared/__init__.py
│  ├─ Common utilities
│  └─ arca_logging.py, database_manager.py
├─ Size: ~400-600MB (300MB deps + 100MB shared code)
└─ Update Frequency: WEEKLY (new shared features, package updates)

📦 Layer 3: Service Images (ghcr.io/danxalot/arca-{service}:latest)
├─ FROM arca-middleware
├─ Service-Specific Code:
│  ├─ /app/main.py
│  ├─ /app/model_config.py (service-specific overrides)
│  └─ /app/service_modules/*.py
├─ Size: ~20-200MB (depends on service code size)
└─ Update Frequency: DAILY/HOURLY (active development)
```

### 4. Benefits of Layering

| Metric | Current (Monolithic) | Layered | Improvement |
|--------|----------------------|---------|-------------|
| Base rebuild time | N/A | 2-3min | New baseline |
| Middleware rebuild | N/A | 3-5min | Shared dependencies reused |
| Service rebuild | 5-15min | 30sec-2min | 75-90% faster ✅ |
| Layer reuse across 50 services | 0% | ~40-50% cache hits | Huge bandwidth/CI savings |
| GHCR storage | 50 × 500MB-13GB | 3 images + deltas | 60-70% smaller registry |

### 5. Implementation Roadmap

#### Week 1: Create Base & Middleware Layers
1. **Create Dockerfile.base** - OS + system deps (200-300MB)
2. **Create Dockerfile.middleware** - FROM base, add shared Python + ARCA code (300-600MB)
3. **Build locally & verify** - Test with 2-3 services
4. **Push to GHCR** - Multi-arch (linux/amd64, linux/arm64)

#### Week 2: Migrate Phase 1 Services
1. **agent_service** - Create Dockerfile.layered (uses middleware)
2. **maintainer_agents** - Same pattern
3. **mcp_server** - Same pattern
4. **user_interaction_agent** - Already clean, easy migration
5. **observer_agent** - Phase 1 priority

#### Week 3: Migrate Remaining Services (By Priority)
- Phase 2 services (embedding_system, neural_system, etc.)
- Multi-arch builds with buildx
- Push all to GHCR

#### Week 4: Legacy Cleanup & Optimization
- Remove old monolithic images from GHCR
- Update OCI docker-compose to use middleware-layered images
- Document completion in DOCKER_OPS_SOP.md

### 6. Critical Implementation Details (Per DOCKER_OPS_SOP.md)

**Security & Authorization:**
- ✅ All service Dockerfiles must include Genesis chain header propagation logic
- ✅ MCP Server must capture incoming `X-Genesis-*` headers
- ✅ Agent services must accept `X-Genesis-Chain` and pass through cognitive loop
- ⚠️ **ACTION NEEDED:** Validate all services have header logic before pushing to GHCR

**Registry Naming:**
- ✅ Use normalized pattern: `ghcr.io/danxalot/arca-{service}:latest`
- ✅ Leverage `scripts/normalize_registry.sh` for tagging/pushing
- ⚠️ **ACTION NEEDED:** Verify normalize_registry.sh exists and is functional

**Multi-Arch Builds:**
- Use `docker buildx build --platform linux/amd64,linux/arm64 --push`
- Test locally on both architectures before GHCR push
- ⚠️ **ACTION NEEDED:** Set up buildx context if not already done

### 7. Immediate Action Items (Next Step)

**Priority 1 - Today:**
- [ ] Verify all three Phase A services (agent_service, user_interaction_agent, resource_monitor) remain stable through push cycle
- [ ] Test HTTP endpoints on all three services to ensure functionality
- [ ] Commit hotfixes to git

**Priority 2 - This Week:**
- [ ] Create Dockerfile.base with OS + system deps
- [ ] Create Dockerfile.middleware with shared Python + ARCA code
- [ ] Build and test locally with agent_service
- [ ] If successful, push to GHCR

**Priority 3 - Validation:**
- [ ] Check all services for Genesis chain header logic (MCP propagation)
- [ ] Run security audit on shared code
- [ ] Document any new patterns discovered during refactoring

### 8. Potential Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Breaking changes in middleware layer | Use semantic versioning (arca-middleware:v2.0) during transition |
| Layer cache invalidation causing rebuilds | Pin specific versions in Layer 2, not `latest` |
| OCI host pulls old images from GHCR | Update docker-compose.oci.yml with explicit versions |
| Services with custom model_config conflicts | Document override patterns in shared code |
| Missing system dependencies | Comprehensive Dockerfile.base testing on both amd64 + arm64 |

---

## Next Steps - Your Input Needed

1. **Proceed with baseline push of Phase A services** to establish current stable state in GHCR?
2. **Begin Layer 1 (Base Image) creation** this week?
3. **Prioritize which services** for Layer 2/3 refactoring (recommended: agent_service, maintainer_agents, mcp_server)?
4. **Security audit** - should I validate Genesis chain headers in all services before pushing?

