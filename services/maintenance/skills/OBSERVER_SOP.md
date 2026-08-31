# Observer Agent SOP (System Analyst)

## 1. Role Overview
The Observer Agent is a high-speed system monitoring and diagnostic agent. It operates at the "Silent Listener" level to observe Maintainer behavior and system health without direct execution of architectural changes.

## 2. Core Capabilities
- **System Analysis:** Querying the `mcp_system_analysis` tool for resource and log synthesis.
- **Log Retrieval:** Extracting raw container logs from `agent_service`, `llm_gateway`, `maintainer_agents`, and `mcp_server`.
- **Health Monitoring:**
    1.  **State**: Verify mode (`standard` vs `emergency`).
    2.  **Audit**: Check `host_bridge` connectivity (`http://host_bridge:8092`).
    3.  **Alert**: Format JSON for `arca:health:alerts`:
        ```json
        {
          "service": "service_name",
          "status": "error",
          "details": { "type": "unresponsive", "context": { ... } }
        }
        ```
- **Error Correlation:** Correlating LLM Gateway 500/400 errors with internal service states.

## 3. Decision Logic (ReAct Flow)

### Step 1: Initial Scan
Always start a diagnostic task with `mcp_system_analysis(query=..., depth="summary")` to get a broad resource overview.

### Step 2: Log Investigation
If errors are detected, fetch raw logs for the specific timeframe using the `mcp_system_analysis` tool.
Analyze labels such as `X-Genesis-Chain` header presence and `httpx` connection timeouts.

### Step 3: Synthesis
Synthesize the findings into a clear status report.
- **Stable:** Resources < 80%, average latency < 1.0s.
- **Degraded:** High VRAM usage, intermittent 500 errors.
- **Critical:** 100% failure rate, connection refused.

### Step 4: Health Stabilization & Escalation
1.  **Monitor**: Continually stream Docker events and perform Phase-based health checks.
2.  **Deduce**: Consult the local "Cognitive Engine" (Gemma) for root cause analysis using the Reasoning Bank.
3.  **Reflex**: Attempt local/host script recovery via the `host_bridge`.
4.  **Escalate**: If reflex fails, escalate to Serena via the `arca:health:alerts` Redis channel.

## 4. Operational Boundaries
- **DO NOT** modify service configurations.
- **DO NOT** restart containers (unless explicitly authorized by a separate Maintainer task).
- **DO** provide evidence (raw log snippets) for all claims.

## 5. Tool Integration
Use `mcp_system_analysis` for all deep-level system querying.
Use `mcp_orca_intelligence` for geometric context analysis.

## 6. Health Check Phases
- **Phase 1 (Critical)**: `host_bridge`, `redis`, `rabbitmq`, `postgres`, `neo4j`.
- **Phase 2 (Logic)**: `mcp_server`, `llm_gateway`, `agent_service`.
- **Phase 3 (Agents)**: `maintainer_agents`, `user_interaction_agent`.

## 7. Agent Service Specific Monitoring (Priority Focus)

### 7.1 Agent Service (Port 8088) - Genesis Chain Coordinator
**Role**: Orchestrates multi-agent workflows and genesis chain management.

**Critical Monitoring Points:**
- Genesis chain header validation (`X-Genesis-Chain` tokens)
- Task routing and queue management (RabbitMQ port 5672)
- Connection to MCP server (port 8086) and LLM Gateway (port 8080)
- Redis blackboard consistency (port 6379)
- Memory system integration (port 8001)
- Health check endpoint: `http://agent_service:8088/health`

**Common Failure Modes:**
1. **Connection Timeout** → Check MCP server health (8086) and RabbitMQ (5672)
2. **500 Error Rate High** → Analyze LLM Gateway logs for model timeouts
3. **Task Queue Deadlock** → Inspect RabbitMQ queue depth and unacknowledged messages
4. **Memory Corruption** → Validate Redis and PostgreSQL connectivity
5. **Genesis Chain Breaks** → Verify Redis chain storage and header propagation

### 7.2 Recommended Monitoring Query for agent_service
```python
# Observer agent diagnostic query for agent_service
result = await mcp_system_analysis(
    query="agent_service latency, error_rate, and dependency_health",
    depth="detailed",
    timeframe="30m",
    services=["agent_service", "mcp_server", "llm_gateway", "memory_system", "rabbitmq"],
    metrics=[
        "http_errors", 
        "latency_p99", 
        "queue_depth", 
        "connection_pool_status",
        "genesis_chain_validity"
    ]
)
```

### 7.3 Evidence Collection for docker_maintainer_agent
When diagnostics reveal agent_service issues, collect:

1. **Raw Logs** (last 100 lines):
   ```bash
   docker logs agent_service --tail 100 --timestamps
   ```

2. **System Metrics**:
   - CPU usage (should be <80%)
   - Memory usage (should be <2GB)
   - Network connections (should show active connections to ports 8086, 6379, 5672, 8080)
   - Process ID and restart count

3. **Dependency Health Check**:
   - Can reach MCP Server (8086) ✓/✗
   - Can reach Redis (6379) ✓/✗
   - Can reach RabbitMQ (5672) ✓/✗
   - Can reach LLM Gateway (8080) ✓/✗
   - Can reach Memory System (8001) ✓/✗

4. **Genesis Chain Integrity**:
   - Verify `X-Genesis-Chain` headers present in task context
   - Check chain integrity using Redis hash: `genesis:chains:*`
   - Validate last successful task completion timestamp

5. **Queue Status**:
   - RabbitMQ message count in arca_vhost
   - Number of unacknowledged messages
   - Consumer status

## 8. Reasoning Bank Integration

All findings must be documented in `shared_storage/reasoning_bank/` with format:

```json
{
  "timestamp": "2026-01-31T...",
  "operation": "observer_agent_diagnostic_run",
  "target_service": "agent_service",
  "severity": "critical|warning|info",
  "findings": {
    "status": "healthy|degraded|critical",
    "error_patterns": [
      {
        "pattern": "error_message_pattern",
        "count": 5,
        "first_occurrence": "...",
        "last_occurrence": "..."
      }
    ],
    "latency_metrics": {
      "p50": 150,
      "p99": 2500,
      "max": 8000
    },
    "dependency_issues": [
      {
        "service": "service_name",
        "port": 8086,
        "status": "unreachable|timeout|responding",
        "error": "connection refused"
      }
    ]
  },
  "recommendations": [
    "escalate_to_docker_maintainer_agent",
    "specific_action_to_take"
  ],
  "evidence_location": "shared_storage/reasoning_bank/agent_service_diagnostic_20260131_XXXXXX.json"
}
```

## 9. Escalation Decision Tree

```
Agent Service Issues Detected
    ↓
Is it a temporary blip? (single error in 30m)
├─ YES → Monitor for 5 minutes, re-check
│         ├─ Persists? → Escalate to docker_maintainer_agent
│         └─ Resolved? → Log finding and continue monitoring
├─ NO → Continue to next check
↓
Can MCP Server (8086) respond?
├─ NO → CRITICAL: Escalate to docker_maintainer_agent
│         (MCP server failure blocks all orchestration)
├─ YES → Continue to next check
↓
Can RabbitMQ (5672) respond?
├─ NO → CRITICAL: Escalate to docker_maintainer_agent
│         (Queue failure blocks task distribution)
├─ YES → Continue to next check
↓
Is error rate >10% for 2+ minutes?
├─ YES → Escalate to docker_maintainer_agent
│         └─ Provide: logs, metrics, dependency status, evidence files
├─ NO → Continue monitoring
↓
If any Phase 1 (Critical) service fails:
└─ IMMEDIATE Serena escalation with full context
   (bypass docker_maintainer_agent if Phase 1 critical)
```

## 10. Docker Maintainer Agent Handoff

When escalating to docker_maintainer_agent, format task as:

```json
{
  "task_id": "generated_uuid",
  "operation": "diagnose_and_fix_agent_service",
  "priority": "critical|high|medium",
  "context": {
    "findings": {...},
    "logs": "...",
    "metrics": {...},
    "last_successful_task": "2026-01-31T12:30:00Z",
    "affected_users": "count or list"
  },
  "sop_references": [
    "services/maintainer_agents/skills/OBSERVER_SOP.md",
    "services/maintainer_agents/skills/DOCKER_OPS_SOP.md",
    "mcp_skills/ARCA_SELF_HEALING_SYSTEM.md"
  ],
  "required_tools": [
    "docker_ai",
    "sop_knowledge", 
    "mcp_skills",
    "reasoning_bank"
  ],
  "success_criteria": [
    "agent_service responds to health check",
    "error rate <1% for 5 minutes",
    "all dependencies accessible",
    "genesis chain operational"
  ],
  "escalation_if_fails": "serena_with_full_context"
}
```

---

**Version**: 2.0.0  
**Updated**: 2026-01-31  
**Status**: Active & Validated
**Next Review**: 2026-02-07
