# Docker Ops SOP

**Objective:** Perform precise, safe, and efficient container operations.

---
## ✅ COMPLETED HOTFIXES (Stabilized in Layered Builds)

The following services have been hotfixed AND rebuilt locally with mounts, stabilizing them for the next cycle:

| Service | Hotfix Date | Status | Details |
|---------|-------------|--------|---------|
| `user_interaction_agent` | 2026-01-25 | ✅ REBUILT | Draft Prompt → `/api/serena/prompt-builder` API sync; Serena model env-driven (`ARCA_SERENA_MODEL=glm-4.7`); Full service mount for live updates; Logger init order fixed |

**Stability Approach**: 
- Rebuilt image locally as `user_interaction_agent:local`
- Added full service directory mount (`./services/user_interaction_agent:/app`) for instant code updates
- Container health check: passing ✅
- All fixes verified and documented in `mcp_skills/ARCA_COMPREHENSIVE_INFRASTRUCTURE_MOUNT_CONFIG.md`

---

## 1. The "Registry First" Protocol
**MANDATORY:** All core services MUST use the normalized GHCR naming scheme.

### 📚 Strategic Standard: Registry Schema
- **Universal Standard**: `ghcr.io/danxalot/arca-{service}:latest`
- **Exclusion**: Slashes in service names are BANNED. Sub-hyphens are BANNED inside service identifiers.
- **Normalization Tool**: Use `scripts/normalize_registry.sh` after builds to ensure consistent tagging/pushing across architectures.

### 🏗️ Build & Push
1.  **PRE-BUILD SCAN (CRITICAL)**: Run the Artifact Scanner to prevent context bloat.
    ```bash
    ./scripts/pre_build_scan.sh services/[service]
    ```
    *   If it fails, **STOP**. Clean the directory.
    *   If it passes, proceed.

2.  **Context**: Ensure `.dockerignore` excludes `.git`, `.terraform`, and cache data.
3.  **Platform**: Favor `linux/amd64,linux/arm64` via `buildx` for production consistency.
4.  **Command**:
    ```bash
    docker buildx build --platform linux/amd64,linux/arm64 \
      -t ghcr.io/danxalot/arca-[service]:latest --push ./services/[service]
    ```

## 2. Safety Constraints
*   **Restart:** NEVER restart [redis, neo4j, postgres, host_bridge] automatically. These are stateful/infra critical.
*   **Logs:** Always inspect logs before deciding to restart a failed service.
*   **Cleanliness:** Prune dangling images if disk usage > 80%.

## 3. Reasoning & Adaptation
*   **Check:** `docker ps` to verify state.
*   **Diagnose:** `docker logs` to find error.
*   **Act:** `restart` or `build`.
## 4. Operational Cheat Sheet

### Pattern: Tag & Push (Normalization Re-sync)
**Trigger**: You built a local image but it lacks the official GHCR tag.
**Action**: Re-tag and push using the normalization script.
**Command**:
```bash
./scripts/normalize_registry.sh [service]
```

### Pattern: Deploy to OCI (OCI Host -> Pull)
**Trigger**: Repository changes merged to `main`.
**Action**: Pull from GHCR and reload.
**Command**:
```bash
# Ensure you are on the OCI host
docker compose -f docker-compose.oci.yml pull
docker compose -f docker-compose.oci.yml up -d
```

### Pattern: Quick Local Fix (Dev Loop)
**Trigger**: Local iterative development.
**Command**:
```bash
docker compose -f docker-compose.local.yml restart [service]
```
