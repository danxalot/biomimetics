---
skill_id: ARCH_AWARE_DEPLOYMENT_SOP
layer: orchestration
domain: oci_deployment
prerequisites: [SECURITY_MAINTAINER_SOP]
---
# Architecture-Aware Deployment SOP

## 1. Environment Profiling (Mandatory First Step)

Before deploying any container to a remote host, the Agent MUST profile the environment.

**Procedure**:

1. **Check Host Arch**:

   ```bash
   ssh {target} "uname -m"
   ```

   - Output `aarch64` = **linux/arm64**
   - Output `x86_64` = **linux/amd64**
2. **Check Network**:

   ```bash
   ssh {target} "docker network ls"
   ```

   - Ensure `arca_net` exists. If not, create it.

## 2. Image Selection & Building

Agent must ensuring the Docker Image matches the Target Arch.

**Procedure**:

1. **Check Registry**:

   - Does `ghcr.io/...:latest` exist?
   - Does it support the Target Arch? (Manifest check not available? Assume 'latest' is multi-arch OR explicit tag needed).
   - *Default Policy*: Assume `latest` is multi-arch.
2. **Fallback Build**:

   - If deployment fails with `exec format error`, **TRIGGER BUILD**.
   - **Build Command**:
     ```bash
     docker buildx build --platform {TARGET_PLATFORM} -t {IMAGE_NAME} --push .
     ```
   - **Note**: Requires GHCR Auth (See Security SOP).

## 3. Deployment Topology & Environments

### A. Environment Types

1. **Local (Dev/MacOS)**:

   - Config: `docker-compose.local.yml`
   - Images: Local builds (`build: .`) or GHCR.
   - Context: Fast iteration.
2. **OCI (Production/Remote)**:

   - Config: `docker-compose.oci.yml`
   - Images: **GHCR ONLY** (`image: ghcr.io/danxalot/arca/...`).
   - Context: Stable, Long-running.
   - **Note**: `mcp_client` is deployed here as a standalone container to check-in with the Host Bridge or remote MCP Server.

### B. Service Dependencies

- **Core Stack**: `redis`, `postgres`, `neo4j`, `rabbitmq` (Start First).
- **Service Layer**: `agent_service`, `mcp_server`, `memory_system,` `user_interaction_agent`, `maintainer_agents`, `observer_agent`, `llm_gateway, llama.cpp [Vulkan 0; Qwen3-VL-Instruct-2B-Q4_K_M.gguf - no mmproj,& Qwen3-0.6B-Q6_0.gguf`], `mcp_client` (Connects back to MCP Server). (Depend on Core).
- **Edge Layer**: Remaining stack in docker-compose.local.yml

## 4. Verification

After `docker run` or `docker compose up -d`:

1. Wait 10s.
2. Check `docker ps`.
3. If status is `Restarting` or `Exited`:
   - Fetch Logs: `docker logs {container} --tail 20`
   - Analyze Logic: `ModuleNotFoundError` -> Build Error. `Exec format error` -> Arch Error.
   - **Auto-Remediate**: Rebuild (for Arch/Deps) and Redeploy.
