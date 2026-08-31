# BiOS: Microservices Transition Plan

## 1. The "To-Be" State
The future state of the `biomimetics` project focuses on containerizing the **network routing and API backbone**, while preserving the integrity of specialized hardware and distributed memory systems.

### Container Mesh Topology
*   **`bios-net`**: A dedicated Docker bridge network for internal service discovery.
*   **Containerized Backbone (The "To-Be" Compose Stack)**
    *   `credentials-server`: Port 8089 (SSOT for Azure/Local secrets)
    *   `llm-gateway`: Port 8080 (Provider rotation & routing)
    *   `webhook-receiver`: Port 8000 (Cloudflare tunnel ingress)
*   **Host-Native Systems (Protected)**
    *   `muninndb` & `memU`: The distributed memory mesh remains as-is, functioning as the shared proactive state for all agents.
    *   `voice-relay`: Remains on the host to protect the highly tuned Acoustic Echo Cancellation (AEC) pipeline.
    *   `copaw-backend`: Remains largely host-native or securely volume-mounted to ensure unrestricted access to the `~/biomimetics` workspace for agent operations.

---

## 2. Transition Roadmap (Step-by-Step)

### Step 1: Isolate ARCA R&D
1.  **Delineation**: Clearly separate `Inference/`, `services/neural_system/`, and `services/geometry_kernel/` from BiOS infrastructure logic. These will not be touched by the BiOS containerization effort.

### Step 2: Foundation & Orchestration
1.  **Initialize Master Compose**: Create a `docker-compose.yml` focused strictly on the API backbone.
2.  **Secret Injection Pattern**: Ensure `credentials-server` boots first, allowing other containers to fetch API keys dynamically at runtime.

### Step 3: Backbone Containerization
1.  **`credentials-server`**:
    *   Create `services/credentials_server/Dockerfile`.
    *   Map host `~/.azure` or use ENV vars for Azure authentication.
2.  **`llm-gateway`**:
    *   Create `services/gateway/Dockerfile`.
    *   Ensure it resolves `credentials-server` via the Docker internal DNS.

### Step 4: Internal DNS & Routing Updates
1.  Update the host-native CoPaw and Voice Relay systems to point to the newly containerized backbone (e.g., updating localhost ports to reflect the exposed Docker ports if mapping changes, though keeping 8080/8089 mapped to the host is recommended).

### Step 5: The Purge
1.  **Legacy Cleanup**: Delete `DEPRECATED_gemini-live-voice/` and all root-level `.bak`/`.revert` files.

---

## 3. Implementation Checklist

| Task | Priority | Status |
| :--- | :--- | :--- |
| Obscure ARCA R&D folders from BiOS scope | High | Pending |
| Purge deprecated backup files | High | Pending |
| Create backbone `docker-compose.yml` | High | Pending |
| Build `credentials-server` image | High | Pending |
| Build `llm-gateway` image | High | Pending |
| Update `PROJECT_WIKI.md` with new topology | Medium | Pending |