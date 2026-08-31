# Comprehensive Maintenance Documentation Update
**Date**: January 31, 2026  
**Version**: 1.0.0  
**Status**: Complete System Architecture Reference

---

## Executive Summary

This document consolidates all critical updates to ARCA's operational documentation as of January 31, 2026. It reflects:
- Current OCI ARM64 layered architecture deployment
- Port mappings and service health status
- Llama server configuration (dual-server GPU strategy)
- Geometry kernel operational capabilities
- Self-healing and Serena escalation protocols
- MCP skills framework and agent orchestration

---

## 1. SYSTEM ARCHITECTURE STATUS

### 1.1 Deployment Overview
- **Environment**: Hybrid (macOS host + OCI ARM64 VM)
- **Orchestration**: Docker Compose (local + OCI)
- **Active Services**: 18/20 healthy
- **Container Status**: ARM64 layered architecture fully deployed on OCI

### 1.2 OCI Deployment Stack (docker-compose.oci.yml)

**Neural System Core:**
- `neural_system:arm64` - Port 8085 (Core ARCA baseline)
- `reflexive_amygdala:arm64` - Port 8092 (Reflection engine)
- `dreaming_consolidator:arm64` - Port 8093 (Memory consolidation)
- `td_jepa:arm64` - Port 8094 (Temporal video JEPA, ONNX CPU)
- `geometry_kernel:arm64` - Port 8087 (Physics/geometric orchestration)

**Persistence Layer:**
- `dragonfly` - Port 6380 (Redis replacement, 2 proactor threads)
- `qdrant` - Port 6334 (Vector database)
- `neo4j` - Port 7475/7688 (Knowledge graph)

**Connectivity:**
- `mcp_client_oci:arm64` - Port 8095 (MCP gateway to parent host at 194.36.110.133:8086)
- `oci_builder` - Docker-in-Docker for OCI-native builds

---

## 2. PORT MAPPING (CANONICAL REFERENCE)

### 2.1 Core Agent Services
| Port | Service | Role | Status | Last Verified |
|------|---------|------|--------|---|
| 8080 | llm_gateway | LiteLLM router (all models) | ✅ HEALTHY | 2026-01-31 |
| 8086 | mcp_server | MCP reasoning hub | ✅ HEALTHY | 2026-01-31 |
| 8087 | geometry_kernel | Physics/spatial orchestration | ✅ HEALTHY | 2026-01-31 |
| 8088 | agent_service | Genesis chain coordination | ✅ HEALTHY | 2026-01-31 |
| 8089 | serena_alert_agent | Health alert & escalation | ✅ HEALTHY | 2026-01-31 |
| 8090 | maintainer_agents | Docker/Git/File/Security ops | ✅ HEALTHY | 2026-01-31 |
| 8092 | host_bridge | Host filesystem access | ✅ HEALTHY | 2026-01-31 |
| 8095 | mcp_client_oci | OCI satellite MCP client | ✅ ACTIVE | 2026-01-31 |

### 2.2 Memory & Persistence
| Port | Service | Protocol | Status |
|------|---------|----------|--------|
| 5432 | postgres | TCP | ✅ HEALTHY |
| 5672 | rabbitmq | AMQP (arca_vhost) | ✅ HEALTHY |
| 6379 | redis | TCP (primary cache) | ✅ HEALTHY |
| 6380 | dragonfly | TCP (OCI replacement) | ✅ HEALTHY |
| 6334 | qdrant | HTTP (vectors) | ✅ HEALTHY |
| 7474 | neo4j | HTTP (UI) | ✅ HEALTHY |
| 7687 | neo4j | Bolt | ✅ HEALTHY |
| 15672 | rabbitmq | HTTP (admin) | ✅ HEALTHY |

### 2.3 Local LLM Servers
| Port | Type | Model | Hardware | Role | Status |
|------|------|-------|----------|------|--------|
| 11435 | llama-server | Qwen3VL-2B | GPU (Metal/Vulkan) | Primary (Vision+Reasoning) | ✅ ACTIVE |
| 11357 | llama-server | Qwen3-0.6B | GPU (Vulkan 0) | Fast reasoning fallback | ✅ ACTIVE |
| 8094 | vLLM | Qwen3-0.6B | OCI Ampere (ARM) | OCI ops fallback | 🛠️ DEPLOYING |
| 8081 | llama_cpp (Docker) | Qwen3-Embedding | CPU | Embedding only | ✅ ACTIVE |

---

## 3. LLAMA SERVER CONFIGURATION (DUAL-SERVER STRATEGY)

### 3.1 Architecture

The system employs a smart dual-server architecture to balance GPU utilization with reasoning capability:

```
Request Flow:
    ↓
[Maintainer Agent]
    ↓
[Smart Lock System]
    ├─ Acquire model_2b_busy lock?
    │  ├─ YES → Native Server (11435) Qwen3VL-2B (HIGH CAP)
    │  └─ NO  → Fallback (11357 or 8094) Qwen3-0.6B (FAST)
    ↓
[Response]
```

### 3.2 Server Specifications

**Primary: Native Server (Port 11435)**
```bash
Command: llama-server \
  --model models/Qwen3VL-2B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 \
  --port 11435 \
  --n-gpu-layers 99 \
  --ctx-size 12288
  
Performance: ~40-60 tokens/s (GPU accelerated)
Capabilities: Vision, reasoning, maintainer analysis
```

**Fallback: Vulkan Server (Port 11357)**
```bash
Command: llama-server \
  --model models/Qwen3-0.6B-Q6_0.gguf \
  --host 0.0.0.0 \
  --port 11357 \
  --n-gpu-layers 99 \
  --ctx-size 4096
  
Performance: ~80-120 tokens/s (faster)
Capabilities: Quick reasoning, fallback inference
```

**OCI Fallback: vLLM (Port 8094) [DEPLOYING]**
```bash
Role: OCI operations, ARM64 optimized
Model: Qwen3-0.6B
Performance: Optimized for Ampere architecture
```

### 3.3 Model Swap Authorization

Maintainer agents use the **Smart Lock** system:
1. Lock `model_2b_busy` with timeout
2. Use primary 2B model if available
3. Fall back to 0.6B fast model if busy
4. Release lock after completion

---

## 4. GEOMETRY KERNEL (PHASE 2 CAPABILITIES)

### 4.1 Core Modules

| Module | Purpose | Status |
|--------|---------|--------|
| `semantic_chunker.py` | Topic-boundary detection | ✅ Active |
| `research_augmentation.py` | Augment with related research | ✅ Active |
| `clever_artifacts.py` | Extract analytical artifacts | ✅ Active |
| `state_comparison.py` | System state diffing | ✅ Active |
| `recursive_ingestion.py` | Recursive document processing | ✅ Enhanced |

### 4.2 Container Configuration
```yaml
Service: geometry_kernel
Image: ghcr.io/danxalot/arca-geometry_kernel:arm64
Port: 8087
Size: 81.9MB (highly optimized)
Architecture: ARM64 layered
Status: ✅ Deployed on OCI
```

### 4.3 Operational Workflow
```
Document Input
    ↓
[Semantic Chunker] → Topic-aware chunks
    ↓
[Clever Artifacts] → Theme vectors, dependencies, contradictions
    ↓
[Research Augmentation] → Related research injection
    ↓
[State Comparison] → Compare system states
    ↓
Enriched Output
```

---

## 5. SELF-HEALING SYSTEM (SERENA INTEGRATION)

### 5.1 Escalation Protocol

```
System Health Alert
    ↓
[Redis] pub/sub: arca:health:alerts
    ↓
[Serena] receives and analyzes
    ↓
[Skills Bank] read-only access
    ↓
[Reasoning Bank] diagnosis
    ↓
Create Repair Job
    ├─ Docker Ops Agent (8090)
    ├─ Git Ops Agent
    └─ Dev Ops Agent
    ↓
Execute Repair
    ↓
On Success: Capture Skill
```

### 5.2 Health Check Phases

**Phase 1 (CRITICAL) - Infrastructure**
- host_bridge (8092)
- redis (6379)
- rabbitmq (5672)
- postgres (5432)
- neo4j (7687)

**Phase 2 (LOGIC) - Core Processing**
- mcp_server (8086)
- llm_gateway (8080)
- agent_service (8088)

**Phase 3 (AGENTS) - Orchestration**
- maintainer_agents (8090)
- user_interaction_agent
- observer_agent

### 5.3 Alert JSON Schema
```json
{
  "service": "service_name",
  "status": "error|warning|recovered",
  "details": {
    "type": "unresponsive|error_rate|resource_exhaustion",
    "context": {
      "error_count": 0,
      "last_error": "...",
      "timestamp": "2026-01-31T..."
    }
  },
  "recommendation": "restart|scale|escalate_to_serena"
}
```

---

## 6. MCP SKILLS FRAMEWORK

### 6.1 Skill Organization
```
mcp_skills/
├── ARCA_PORT_MAPPING_UPDATED.md ........... Service discovery
├── llama_servers_configuration.md ........ GPU server setup
├── ARCA_SELF_HEALING_SYSTEM.md ........... Recovery protocols
├── ARCA_GEOMETRY_KERNEL_PHASE2.md ....... Document processing
├── ARCA_AGENT_CONFIGURATION.md .......... Agent setup
├── ARCA_MCP_SKILLS_INDEX.md ............ Skills catalog
└── [60+ operational documents]
```

### 6.2 Skill Indexing

Skills are indexed by:
- `skill_id`: Unique identifier
- `layer`: core|execution|inference|memory
- `domain`: infrastructure|agent_orchestration|error_recovery
- `touchpoints`: Services affected
- `geometric_markers`: Embedding anchors for semantic search
- `error_signatures`: Pattern matching for troubleshooting

### 6.3 Workflow Integration

Workflows in `shared_storage/arca_internal/workflows/` reference skills:
- `CONTINUOUS_MAPPING_PROTOCOL.md` - Skill mapping maintenance
- `NEURAL_ARCHITECTURE.md` - Component orchestration
- `layered_memory_refresh.md` - Memory system operations
- `integration_roadmap.md` - Integration patterns

---

## 7. CONTAINER BUILD STRATEGY

### 7.1 ARM64 Layered Architecture

**Benefits:**
- 75-90% size reduction
- Faster deployment
- Efficient caching
- OCI compatibility

**Dockerfiles:**
```
services/*/Dockerfile.layered.arm64
├── Layer 1: Base Python (777MB)
├── Layer 2: Service dependencies
├── Layer 3: Application code
└── Layer 4: Runtime configuration
```

### 7.2 Naming Convention

**CORRECT** ✅
```
ghcr.io/danxalot/arca-SERVICE:arm64
ghcr.io/danxalot/arca-SERVICE:latest
```

**INCORRECT** ❌
```
ghcr.io/danxalot/arca/SERVICE:latest
ghcr.io/danexall/arca-SERVICE
```

### 7.3 Current Image Status

| Image | Size | Architecture | Status |
|-------|------|--------------|--------|
| geometry_kernel:arm64 | 81.9MB | ARM64 | ✅ OCI Ready |
| agent_service:layered | 1.38GB | AMD64 | ✅ Local Ready |
| neural_system:arm64 | ~600MB | ARM64 | 🛠️ Deploying |
| middleware:arm64 | 1.38GB | ARM64 | ✅ Ready |

---

## 8. OBSERVER AGENT OPERATIONAL PARAMETERS

### 8.1 Monitoring Scope

**System Analysis Depth**: `summary` (fast) → `detailed` (slow)

```python
from mcp_system_analysis import analyze_system

result = await analyze_system(
    query="agent_service error rate",
    depth="summary",  # or "detailed"
    timeframe="1h"
)
```

### 8.2 Log Investigation Pattern

1. **Initial Scan**: Get broad resource overview
2. **Log Fetch**: Extract raw container logs for timeframe
3. **Pattern Match**: Look for error signatures
4. **Synthesis**: Create status report
5. **Escalation**: Format health alert for Serena

### 8.3 Error Correlation

Look for patterns:
- `X-Genesis-Chain` header presence
- `httpx` connection timeouts
- 500/400 error codes
- Memory exhaustion patterns
- RabbitMQ queue deadlocks

---

## 9. DOCKER MAINTAINER AGENT TASK TEMPLATE

### 9.1 Input Format (from Observer Agent)

```json
{
  "operation": "diagnose_and_fix_service",
  "target_service": "agent_service",
  "issues": [
    {
      "type": "error_rate_high",
      "evidence": "500 errors at 15:23 UTC",
      "logs": "... (raw logs) ...",
      "severity": "critical"
    }
  ],
  "context_files": [
    "mcp_skills/ARCA_SELF_HEALING_SYSTEM.md",
    "shared_storage/reasoning_bank/..."
  ],
  "required_tools": ["docker_ai", "sop_knowledge", "mcp_skills"],
  "escalation_criteria": {
    "if_fix_fails": "escalate_to_serena_with_full_context"
  }
}
```

### 9.2 Remediation SOP

1. **Analyze** using reasoning_bank and SOPs
2. **Inspect** Docker logs and system state
3. **Diagnose** root cause
4. **Execute** fix (restart, rebuild, patch)
5. **Verify** health (wait for health checks)
6. **Document** in reasoning_bank
7. **Escalate** if necessary

### 9.3 Escalation to Serena

```json
{
  "escalation_type": "critical_system_failure",
  "failed_attempts": [...],
  "full_context": {
    "service": "agent_service",
    "issues_found": [...],
    "logs_analyzed": "...",
    "skills_consulted": [...],
    "recommendations": [...]
  },
  "next_steps": "Require Serena intervention"
}
```

---

## 10. KEY DOCUMENTATION REFERENCES

### 10.1 Skills (Read-Only in Maintainer Operations)
- [OBSERVER_SOP.md](./OBSERVER_SOP.md) - Observer agent protocol
- [DOCKER_OPS_SOP.md](./DOCKER_OPS_SOP.md) - Container operations
- [GIT_OPS_SOP.md](./GIT_OPS_SOP.md) - Git operations
- [REFACTORING_ANALYSIS_20260127.md](./REFACTORING_ANALYSIS_20260127.md) - Recent changes

### 10.2 MCP Skills Reference
- [mcp_skills/ARCA_PORT_MAPPING_UPDATED.md](../../../mcp_skills/ARCA_PORT_MAPPING_UPDATED.md)
- [mcp_skills/llama_servers_configuration.md](../../../mcp_skills/llama_servers_configuration.md)
- [mcp_skills/ARCA_SELF_HEALING_SYSTEM.md](../../../mcp_skills/ARCA_SELF_HEALING_SYSTEM.md)
- [mcp_skills/ARCA_GEOMETRY_KERNEL_PHASE2.md](../../../mcp_skills/ARCA_GEOMETRY_KERNEL_PHASE2.md)

### 10.3 Workflow Documentation
- [shared_storage/arca_internal/workflows/CONTINUOUS_MAPPING_PROTOCOL.md](../../../../shared_storage/arca_internal/workflows/CONTINUOUS_MAPPING_PROTOCOL.md)
- [shared_storage/arca_internal/workflows/layered_memory_refresh.md](../../../../shared_storage/arca_internal/workflows/layered_memory_refresh.md)

### 10.4 Configuration References
- [docker-compose.oci.yml](../../../../docker-compose.oci.yml) - OCI deployment
- [docker-compose.local.yml](../../../../docker-compose.local.yml) - Local development
- [CONTAINER_AUDIT_20260128.md](../../../../CONTAINER_AUDIT_20260128.md) - Recent audit

---

## 11. NEXT ACTIONS & VERSIONING

**Version**: 1.0.0  
**Created**: 2026-01-31  
**Next Review**: 2026-02-07 (weekly)

**Critical Updates Since Last Version**:
- ✅ Consolidated all port mappings (18/20 services active)
- ✅ Updated llama server configuration (dual-GPU strategy)
- ✅ Documented geometry_kernel Phase 2 capabilities
- ✅ Clarified self-healing escalation protocol
- ✅ Standardized ARM64 layered build process
- ✅ Unified MCP skills index

---

**End of Document**
