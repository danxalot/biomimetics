# ARCA Container Build Strategy

**Status:** authoritative | **Scope:** All ARCA Services

## 🎯 Strategic Goal: Layered Architecture
All services **MUST** be refactored to use a 3-tier layered build process. This ensures maximum cache reuse, rapid deployment, and guaranteed consistency across environments (Local/Mac, OCI/Linux).

## 🏗️ The 3-Layer Pattern

### 🧱 Layer 1: The Foundation (`arca-base`)
*   **Content:** OS (Debian/Alpine), Python Runtime (3.11+), System Dependencies (curl, git, build-essential).
*   **Tag:** `ghcr.io/danxalot/arca/base-python:latest`
*   **Why:** Security patches and OS updates happen here once.
*   **Frequency:** Rare updates (Monthly).

### 🔧 Layer 2: The Middleware (`arca-middleware`)
*   **Content:** ARCA's shared Python libraries.
    *   `shared/` (Model Config, Utils)
    *   `database_manager.py`
    *   `arca_logging.py`
    *   Common PyPI packages (`fastapi`, `pydantic`, `requests`).
*   **Tag:** `ghcr.io/danxalot/arca/middleware:latest`
*   **From:** `FROM ghcr.io/danxalot/arca/base-python:latest`
*   **Why:** 80% of our services share the same 90% of code. This layer catches that redundancy.
*   **Frequency:** Medium updates (Weekly/Bi-weekly).

### 🚀 Layer 3: The Service (`arca-[service]`)
*   **Content:** Service-specific logic exclusively.
    *   `main.py`
    *   Service-specific tools/skills.
*   **From:** `FROM ghcr.io/danxalot/arca/middleware:latest`
*   **Why:** Builds are instant. Only the changed logic bytes are transferred.
*   **Frequency:** High updates (Daily/Hourly).

---

## 📋 Refactoring Roadmap (Priority Order)

### Phase 1: Missing Images (Immediate)
*Maintainer Agents: Apply the pattern to these first when creating their initial GHCR images.*
1.  `maintainer_agents`
2.  `observer_agent`
3.  `conversational_hdc`
4.  `geometry_kernel`
5.  `hse_encoder`
6.  `alert_manager`
7.  `policy_manager`
8.  `host_bridge`

### Phase 2: Core Refactor (Next Build Cycle)
*Refactor these existing services when significant changes occur.*
- `agent_service`
- `mcp_server`
- `user_interaction_agent`
- `memory_system`

## 🛡️ Security & Authorization (Genesis Chain)
All service builds **MUST** incorporate the `X-Genesis-*` header propagation logic. 
*   **MCP Server:** Must capture `incoming` headers and propagate them to internal tool dispatches.
*   **Agent Services:** Must accept `X-Genesis-Chain` authorization and pass it through the cognitive loop.
*   **Host Bridge:** Must verify `X-Genesis-Signature` for sensitive filesystem/git operations.

## 🛠 Maintainer Agent Instruction
When receiving a task to "Update Service X":
1.  Check `Dockerfile`.
2.  **Verify Header Logic:** Ensure `mcp_server.py` and delegating tool handlers (Git, FileOps, etc.) propagate security context.
3.  **Refactor** to use `FROM arca/middleware` (if applicable).
4.  **Build** Multi-arch (`linux/amd64`, `linux/arm64`).
5.  **Push** to GHCR.
