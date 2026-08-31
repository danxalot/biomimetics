# Geometry Kernel — Lyceum Cloud Runbook

This runbook describes the full process to run `geometry_kernel` on Lyceum Cloud (or a Lyceum-like VM/container environment). It assumes the service code is present in `services/geometry_kernel` and you have SSH access to a VM (example: `arca-oci-workhorse` with user `ubuntu`). The repository includes a `Dockerfile` and `requirements.txt`.

## Assumptions & Prerequisites
- Local repository contains `services/geometry_kernel`.
- SSH key for the target instance: `/Users/danexall/.ssh/arca-oci-key` (user `ubuntu`).
- Lyceum Cloud provides: container runtime (Docker), Redis, Neo4j or managed equivalents, and network to LLM gateway or ability to run LLM gateway containers.
- Container registry available (GHCR, Docker Hub, or Lyceum registry) and credentials.

## High-level Steps
1. Prepare target VM (ubuntu) — system packages, Docker, Docker Compose (or Podman/Kubernetes).
2. Build and push Docker image for `geometry_kernel`.
3. Provision supporting services: Redis, Neo4j, LLM gateway (DeepSeek / Qwen-VL) and storage if needed.
4. Deploy container with environment variables & secrets.
5. Run Neo4j bootstrap script to initialize the system graph.
6. Validate service health and simulate/validate/apply flow.
7. Monitor OTEL signals and tune throttling thresholds.

## Detailed Commands — Target VM Setup
SSH to VM (example):

```bash
ssh -i /Users/danexall/.ssh/arca-oci-key ubuntu@<ARCA_OCI_WORKHORSE_IP>
```

On the VM, install Docker (Ubuntu example):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

If you prefer `docker-compose` v1, install accordingly. For production, consider Kubernetes.

## Build & Publish Container
From your development machine (or on VM), build and push image:

```bash
cd services/geometry_kernel
docker build -t ghcr.io/<your-org>/geometry_kernel:latest .
# Authenticate & push (example GHCR)
echo $CR_PAT | docker login ghcr.io -u <your-gh-username> --password-stdin
docker push ghcr.io/<your-org>/geometry_kernel:latest
```

Alternatively, build on the VM directly to avoid pushing to registry.

## Required Supporting Services
- Redis (for blackboard, HSE pub/sub). Default host name used by code: `redis` (configure via `REDIS_HOST`).
- Neo4j (for system graph) — accessible at bolt/http endpoints.
- LLM gateway (`LLM_GATEWAY_URL`) that proxies DeepSeek R1, Qwen-VL, Guardian. The code expects an OpenAI-like `/v1/chat/completions` endpoint.

You can run these as containers on the same host or provision managed services. Example `docker compose` fragment (minimal):

```yaml
version: '3.8'
services:
  redis:
    image: redis:7
    restart: unless-stopped
    ports: ["6379:6379"]

  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/test
    ports: ["7474:7474","7687:7687"]

  llm_gateway:
    image: ghcr.io/<your-org>/llm_gateway:latest
    ports: ["8080:8080"]

  geometry_kernel:
    image: ghcr.io/<your-org>/geometry_kernel:latest
    environment:
      - REDIS_HOST=redis
      - LLM_GATEWAY_URL=http://llm_gateway:8080
    depends_on:
      - redis
      - llm_gateway
    ports:
      - "8087:8087"
    restart: unless-stopped

# NOTE: adjust images/registry as appropriate
```

Run:

```bash
docker compose up -d
```

## Environment Variables & Secrets
Set at least the following environment variables for the `geometry_kernel` container:

- `REDIS_HOST` (e.g., `redis`)
- `LLM_GATEWAY_URL` (e.g., `http://llm_gateway:8080`)
- `QWEN_VL_URL`, `QWEN_VL_API_KEY`, `QWEN_MODEL_NAME` as needed by `llm_interface.py`.

For production, put secrets into a secret manager and inject at runtime.

## Neo4j Bootstrap
Generate and run the bootstrap Cypher script to create the system graph.

On the VM (or locally with `neo4j-shell`):

```bash
python - <<'PY'
from geometry_kernel.neo4j_schema import BootstrapCypher
print(BootstrapCypher.generate_full_script())
PY

# Save output to bootstrap.cypher then run it against Neo4j
# Example using cypher-shell (Neo4j must accept bolt auth)
cat bootstrap.cypher | cypher-shell -u neo4j -p test
```

If using Neo4j Browser, paste the script and execute.

## Start Service (alternatives)

- Docker (recommended): run via `docker compose` as above; the container `CMD` runs `python api.py`.
- Systemd (VM-native): create a systemd unit that runs a container or Python directly.

Example systemd unit running Docker container (create `/etc/systemd/system/geometry_kernel.service`):

```ini
[Unit]
Description=Geometry Kernel service
After=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker run --rm \
  -e REDIS_HOST=redis \
  -e LLM_GATEWAY_URL=http://llm_gateway:8080 \
  -p 8087:8087 \
  ghcr.io/<your-org>/geometry_kernel:latest

[Install]
WantedBy=multi-user.target
```

Reload systemd and enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now geometry_kernel.service
```

## Smoke Tests & Verification
1. Health endpoint:

```bash
curl -sS http://<HOST>:8087/health | jq
```

2. Kernel initialized and state present:

```bash
curl -sS http://<HOST>:8087/geometry/state | jq .
```

3. Simulate a simple force (local example):

```bash
curl -sS -X POST http://<HOST>:8087/geometry/simulate \
  -H 'Content-Type: application/json' \
  -d '{"mode":"wake","base_state_id":null,"forces":[{"target_id":"concept:agent_reliability","vector":[0,0,-1],"magnitude":0.1,"source":"evidence","rationale":"smoke test"}] }' | jq
```

4. Validate route (if present) and apply (apply should be restricted):

```bash
# Use returned simulation_id to validate/apply via /geometry/validate and /geometry/apply
```

## Operational Considerations
- Rate limiting: controlling how often agents call `/simulate` is essential. Use orchestrator or API gateway.
- Security: restrict `/apply` to internal orchestrator (mTLS / internal network / firewall + service account).
- Resource planning: LLM gateway and VL are the largest CPU/GPU consumers. Place them near the kernel to reduce latency.

## OTEL & Telemetry Integration
- `otel_mapping.py` expects OTEL/Loki/Prometheus signals to be pre-processed into `OTELSignal` objects and then mapped to `Force` instances by `SignalForceMapper`.
- Strategy: forward relevant metrics (error rate, latency, throughput, retry spikes, CPU, queue depth) to a translator job that calls the kernel `simulate` or publishes to Redis key consumed by `_poll_hse_loop()`.

## Backup, Recovery & Rollback
- Kernel stores `state_history` in memory and serializes to JSON when needed — ensure periodic external persistence (S3/GCS or DB) for long-term recovery.
- For rollbacks: since kernel states are versioned, the orchestrator can call a specialized admin API (not currently present) to set `current_state` to a previous `state_history` id. Implement this carefully and gate behind auth.

## Example Full Deploy (quick summary)
1. On VM: install Docker.
2. Start supporting services (Redis, Neo4j, LLM gateway) via `docker compose`.
3. Build/pull `geometry_kernel` image and run with env vars.
4. Run neo4j bootstrap.
5. Run smoke tests.
6. Monitor OTEL and tune `HealthDependentThrottling` thresholds.

## Troubleshooting Checklist
- `curl /health` returns 503: check container logs; look for missing Redis connection or import errors.
- OOM / Memory pressure: ensure swap and resource limits; large LLMs belong on separate GPU hosts.
- LLm gateway 502/timeout: verify `LLM_GATEWAY_URL`, check gateway logs and connectivity.
- `cypher-shell` failures: check Neo4j auth or network.

## Post-deploy Hardening (recommended)
- Put `geometry_kernel` behind an internal API gateway; require mTLS and service-auth for `/apply`.
- Configure resource limits and autoscaling for LLM gateway.
- Add persistent storage & periodic dumps of `state_history` to object storage.
- Implement a small admin API to list and revert `state_history` entries with RBAC.

---
If you want, I can: (A) generate a `docker-compose.yml` tuned for Lyceum, (B) create a systemd unit and health-check script, or (C) produce Kubernetes manifests for deployment.
