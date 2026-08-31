```markdown
---
title: "BiOS Architecture Master Document"
version: "1.0.0"
last_updated: "2025-01-14"
legal_medical_audit_target: false
---

# BiOS Architecture Master Document

## Document Purpose

This document provides a comprehensive architectural overview of the BiOS (Biomimetic Operating System) infrastructure, mapping the relationships between all primary systems and their integration points. It serves as the authoritative reference for understanding how GitHub, Notion, MuninnDB, MemU, Vultr, and CoPaw interconnect to form the autonomous development and project management ecosystem.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Component Mapping](#component-mapping)
4. [GitHub - Primary Trigger Engine](#github---primary-trigger-engine)
5. [Notion - Status Orchestration Layer](#notion---status-orchestration-layer)
6. [MuninnDB - Local Vector Intelligence (Port 8095)](#muninndb---local-vector-intelligence-port-8095)
7. [MemU - GCP Memory Archive](#memu---gcp-memory-archive)
8. [Vultr - Voice Relay Infrastructure](#vultr---voice-voice-relay-infrastructure)
9. [CoPaw - Agent Execution Gateway (Port 8090)](#copaw---agent-execution-gateway-port-8090)
10. [Data Flow Architecture](#data-flow-architecture)
11. [Security Model](#security-model)
12. [Configuration Reference](#configuration-reference)

---

## System Overview

The BiOS architecture consists of six primary systems that work in concert to create an autonomous development loop. Each system has a defined role:

| System | Protocol | Role | Port/Endpoint |
|--------|----------|------|---------------|
| **GitHub** | Webhooks/HTTPS | Event Triggers | api.github.com |
| **Notion** | REST API/MCP | Status & Task Management | api.notion.com |
| **MuninnDB** | HTTP/WebSocket | Local Vector Database | localhost:8095 |
| **MemU** | HTTPS/GCP | Cloud Memory Archive | memu.arca-vsa.tech |
| **Vultr** | WebSocket/HTTPS | Voice Relay & Audio | vultr.arca-vsa.tech |
| **CoPaw** | HTTP/MCP | Agent Execution & Tools | localhost:8090 |

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    BiOS ARCHITECTURE FLOW                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                               │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐                       │
│  │     GITHUB      │──────│     NOTION      │──────│    MUNINNDB     │                       │
│  │   (Triggers)    │      │    (Status)     │      │     (8095)      │                       │
│  └────────┬────────┘      └────────┬────────┘      └────────┬────────┘                       │
│           │                        │                        │                                │
│           │ Webhook                │ API/MCP               │ Vector Query                   │
│           │                        │                        │                                │
│           │                        ▼                        ▼                                │
│           │              ┌─────────────────┐      ┌─────────────────┐                       │
│           │              │     COP AW      │◄─────│     MEMU        │                       │
│           │              │     (8090)      │      │  (GCP Archive)  │                       │
│           │              └────────┬────────┘      └─────────────────┘                       │
│           │                       │                                                         │
│           │                       │ Agent Execution                                         │
│           │                       │                                                         │
│           │                       ▼                                                         │
│           │              ┌─────────────────┐                                                │
│           └─────────────►│     VULTR       │                                                │
│              Status      │  (Voice Relay)  │                                                │
│              Update      └─────────────────┘                                                │
│                                                                                               │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Mapping

### Cross-System Dependency Matrix

| Source System | Target System | Connection Type | Purpose |
|---------------|---------------|-----------------|---------|
| GitHub | Notion | Webhook → REST | Trigger task creation from issues/PRs |
| GitHub | MuninnDB | Webhook → API | Log events for vector search |
| GitHub | CoPaw | Webhook → HTTP | Initiate agent workflows |
| Notion | MuninnDB | MCP → HTTP | Query context for task processing |
| Notion | MemU | MCP → HTTPS | Archive completed tasks |
| Notion | Vultr | API → WebSocket | Voice status updates |
| MuninnDB | CoPaw | HTTP → HTTP | Retrieve vector context for agents |
| MemU | CoPaw | HTTPS → HTTP | Fetch archived memory context |
| Vultr | Notion | WebSocket → API | Voice command → Notion actions |
| CoPaw | Notion | HTTP → API | Update task status |
| CoPaw | MuninnDB | HTTP → HTTP | Store execution vectors |
| CoPaw | Vultr | HTTP → WebSocket | Voice output relay |

---

## **Autonomous Documentation Strategy**

BiOS utilizes a fully autonomous pipeline to maintain its knowledge wiki, governed by the **BiOS Session Artifact Protocol**. This protocol mandates the harvesting of telemetry and logs from Claude Code, Antigravity, OpenCode, and Zed to build a "Picture of Work" without human intervention.

For detailed retrieval paths, stripping logic, and multi-model synthesis strategies, refer to:
`./BiOS_Sync/Autonomous Wiki and Knowledge Graph Integration.md`

---

## GitHub - Primary Trigger Engine

### Overview

GitHub serves as the **primary event trigger** for the entire BiOS autonomous loop. All development activities originate from GitHub events.

### Trigger Events

| Event Type | Handler | Target System | Action |
|------------|---------|---------------|--------|
| `issues.opened` | Cloudflare Worker | Notion (Biomimetic OS) | Create technical documentation task |
| `issues.labeled` | Cloudflare Worker | Notion (Life OS Triage) | Route to appropriate triage queue |
| `pull_request.opened` | Cloudflare Worker | Notion (Biomimetic OS) | Create PR review task |
| `push` | Cloudflare Worker | MuninnDB | Log activity vector |
| `pull_request.merged` | Cloudflare Worker | MemU | Archive PR context |

### Webhook Configuration

```yaml
webhook_endpoints:
  - name: bios-github-handler
    url: https://bios.workers.dev/webhook/github
    events:
      - issues
      - pull_request
      - push
    secret: ${GITHUB_WEBHOOK_SECRET}
```

### GitHub → Notion Flow

```
GitHub Issue Created
        │
        ▼
Cloudflare Worker (Gemma 3 27b)
        │
        ├──► Draft Technical Documentation
        │
        ▼
Notion Biomimetic OS Database
        │
        ├──► "Ready for Dev" Task Created
        │
        ▼
Serena Notion Poller (30s interval)
```

---

## Notion - Status Orchestration Layer

### Overview

Notion serves as the **central orchestration and status layer**, maintaining all task states and providing the MCP interface for agent interactions.

### Database Mapping

| Database Name | Database ID | Purpose |
|---------------|-------------|---------|
| Biomimetic OS | `3284d2d9fc7c811188deeeaba9c5f845` | Primary project tracking |
| Life OS Triage | `3284d2d9fc7c81bd9a91e865511e642f` | Email/webhook triage |
| Tool Guard | `3284d2d9fc7c8113bfecca75f4235ece` | Security & approvals |
| CoPaw Approval | `3284d2d9fc7c8113bfecca75f4235ece` | Tool approval workflow |

### Task Status Workflow

```
┌─────────┐    ┌────────────┐    ┌────────────┐    ┌──────────┐    ┌─────────┐
│ New     │───►│ In Review  │───►│ Ready      │───►│ In Dev   │───►│ Testing │
└─────────┘    └────────────┘    └────────────┘    └──────────┘    └─────────┘
                                                                    │
                                                                    ▼
                                                              ┌──────────┐
                                                              │ Complete │
                                                              └──────────┘
```

### Notion → MuninnDB Integration

```python
# When task moves to "In Progress", context is vectorized
task_context = notion.get_page(task_id)
embedding = muninndb.embed(task_context.content)
muninndb.store(embedding, metadata={
    "source": "notion",
    "task_id": task_id,
    "status": "in_progress"
})
```

### Notion → MemU Integration

```python
# When task completes, archive to MemU
memu_response = memu.archive({
    "type": "completed_task",
    "notion_id": task_id,
    "content": task_context,
    "timestamp": datetime.now().isoformat()
})
```

---

## MuninnDB - Local Vector Intelligence (Port 8095)

### Overview

MuninnDB is the **local vector database** providing semantic search and context retrieval capabilities. It runs on port 8095 and serves as the bridge between Notion's structured data and the agent's contextual understanding.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        MuninnDB (8095)                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  GitHub     │  │   Notion    │  │   CoPaw     │         │
│  │  Events     │  │   Tasks     │  │   Exec      │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │               │               │                  │
│         └───────────────┼───────────────┘                  │
│                         ▼                                   │
│              ┌─────────────────────┐                         │
│              │   Vector Index     │                         │
│              │   (Local Storage)  │                         │
│              └─────────────────────┘                         │
│                         │                                   │
│                         ▼                                   │
│              ┌─────────────────────┐                         │
│              │   Query Engine      │                         │
│              │   (Semantic Core)  │                         │
│              └─────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/embed` | POST | Generate embeddings for content |
| `/v1/store` | POST | Store vectors with metadata |
| `/v1/search` | POST | Semantic search |
| `/v1/context/{task_id}` | GET | Retrieve full context for task |
| `/v1/health` | GET | Health check |

### MuninnDB → CoPaw Integration

```python
# CoPaw queries MuninnDB for context before execution
context = muninndb.search(
    query=current_task.description,
    limit=5,
    filters={"source": "notion"}
)
```

### Configuration

```yaml
muninndb:
  host: localhost
  port: 8095
  storage_path: ./data/muninn
  embedding_model: sentence-transformers/all-MiniLM-L6-v2
  max_context_results: 10
```

---

## MemU - GCP Memory Archive

### Overview

MemU is the **GCP-based long-term memory archive** that persists completed tasks, agent sessions, and system insights. It provides the "institutional memory" that allows agents to learn from past executions.

### Storage Structure

```
memu://
├── tasks/
│   ├── completed/
│   ├── archived/
│   └── failed/
├── sessions/
│   ├── agent/
│   └── voice/
├── insights/
│   ├── patterns/
│   └── learnings/
└── backups/
    └── daily/
```

### MemU → CoPaw Integration

```python
# CoPaw retrieves relevant past experiences
similar_experiences = memu.query(
    topic=current_task.description,
    timeframe="last_90_days",
    limit=3
)
```

### Archive Trigger Conditions

| Condition | Action |
|-----------|--------|
| Task completed | Archive task + all comments |
| Session timeout (>5min) | Archive partial session |
| Error occurred | Archive error + context |
| Daily 02:00 UTC | Incremental backup |
| Weekly Sunday | Full system backup |

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/archive` | POST | Archive new content |
| `/v1/query` | POST | Search archived content |
| `/v1/insights` | GET | Retrieve learned patterns |
| `/v1/restore/{id}` | POST | Restore from archive |
| `/v1/backup` | POST | Create manual backup |

---

## Vultr - Voice Relay Infrastructure

### Overview

Vultr hosts the **voice relay service** that bridges local audio streams to the **Gemini 3.1 Live API**. This allows for low-latency, multimodal voice interactions with the BiOS ecosystem, utilizing the "Puck" persona.

### Voice Relay Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         VULTR (Voice Relay)                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   CoPaw Agent                    Voice Client                     │
│   (Local Mic/Speaker)            (WebSocket Relay)                │
│        │                              │                           │
│        │ Audio Stream                 │                           │
│        │ (PyAudio/VAD)                │ WebSocket (WSS)           │
│        ▼                              ▼                           │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              Vultr Relay Service                         │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│   │  │   Gemini    │  │   Audio     │  │   Tool      │      │   │
│   │  │   Live      │  │   Buffer    │  │   Routing   │      │   │
│   │  │   (WSS)     │  │             │  │             │      │   │
│   │  └─────────────┘  └─────────────┘  └─────────────┘      │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              Status Webhook (→ Notion)                   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Configuration

```yaml
vultr:
  host: 100.86.112.119
  port: 8765
  protocol: wss
  model: models/gemini-3.1-flash-live-preview
  audio_format: pcm_s16le
  sample_rate_in: 16000
  sample_rate_out: 24000
  
status_webhook:
  url: https://api.notion.com/v1/pages/{page_id}
  events:
    - session_started
    - session_ended
    - command_executed
    - error
```

### Vultr → Notion Integration

Voice interactions are logged to the Notion "Voice Session Logs" database for history and performance tracking:

```python
# Voice session logging
async def log_session_to_notion(speaker: str, text: str):
    await notion.create_page(
        database_id=VOICE_LOG_DB_ID,
        properties={
            "Name": speaker,
            "Transcript": text,
            "Date": datetime.now()
        }
    )
```

---

## CoPaw - Agent Execution Gateway (Port 8090)

### Overview

CoPaw is the **central agent execution gateway** running on port 8090. It orchestrates all agent activities, manages tool approvals, and serves as the bridge between various input channels (Voice, WhatsApp) and actual tool execution.

### Voice Channel (Puck)

The voice channel implements the **Puck** persona—a dry, witty, tactical trickster-butler. It uses a hardware-level VAD (Voice Activity Detection) system and supports barge-in (interruption) for natural conversation.

### CoPaw Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CoPaw Gateway (8090)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐               │
│  │   Voice       │  │    WhatsApp   │  │    Tool       │               │
│  │   Channel     │  │    Channel    │  │    Guard      │               │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘               │
│          │                  │                  │                        │
│          └──────────────────┼──────────────────┘                        │
│                             ▼                                           │
│                   ┌─────────────────────┐                               │
│                   │   Execution         │                               │
│                   │   Orchestrator      │                               │
│                   └─────────────────────┘                               │
│                             │                                           │
│          ┌──────────────────┼──────────────────┐                          │
│          ▼                  ▼                  ▼                         │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                │
│  │   MuninnDB    │  │     MemU      │  │    Notion     │                │
│  │   Context     │  │   Archive     │  │    Tools      │                │
│  └───────────────┘  └───────────────┘  └───────────────┘                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### CoPaw Ports and Services

| Port | Service | Purpose |
|------|---------|---------|
| 8090 | HTTP API | Primary gateway interface |
| 8089 | Credentials | Azure Key Vault Secrets |
| 8000 | Webhook | Webhook Receiver (WhatsApp/Ingestion) |

### CoPaw → Notion Integration

All tools (Email, GDrive, Notion) are routed through the CoPaw `/api/mcp/tool/execute` endpoint, providing a unified security and logging layer.

```python
# Unified tool execution
@app.post("/api/mcp/tool/execute")
async def execute_tool(tool_request: ToolRequest):
    result = await mcp_manager.execute(
        tool_name=tool_request.name,
        arguments=tool_request.arguments
    )
    return {"result": result}
```


---

## Data Flow Architecture

### Complete Event Flow

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                           COMPLETE BiOS DATA FLOW                                      │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  1. TRIGGER (Hourly/Daily)                                                           │
│     ┌─────────────────────────────────────────────────────────────────────────────┐  │
│     │ Hourly Email Ingest                                                         │  │
│     │   └─► Stage in Local Docs → Notion Notification                             │  │
│     │                                                                             │  │
│     │ Daily Master Pipeline (18:00)                                               │  │
│     │   └─► Sweep Auth items to GDrive Vault                                      │  │
│     │         └─► Semantic Tagging → Memory Sync                                  │  │
│     └─────────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                               │
│                                        ▼                                               │
│  2. ORCHESTRATE (Notion)                                                               │
│     ┌─────────────────────────────────────────────────────────────────────────────┐  │
│     │ User authorizes staging items in "BiOS Authorisation" database              │  │
│     │   └─► "Auth Trigger" = True → "To Memory"                                   │  │
│     └─────────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                               │
│                                        ▼                                               │
│  3. CONTEXT RETRIEVAL (MuninnDB)                                                      │
│     ┌─────────────────────────────────────────────────────────────────────────────┐  │
│     │ CoPaw queries MuninnDB for relevant context                                   │  │
│     │   └─► Vector similarity search (includes GDrive Vault documents)             │  │
│     └─────────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                               │
│                                        ▼                                               │
│  4. ARCHIVE CHECK (MemU)                                                              │
│     ┌─────────────────────────────────────────────────────────────────────────────┐  │
│     │ Query MemU for historical insights                                           │  │
│     │   └─► Fetch learned patterns                                                 │  │
│     │         └─► Inject into agent context                                       │  │
│     └─────────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                               │
│                                        ▼                                               │
│  5. EXECUTE (CoPaw)                                                                   │
│     ┌─────────────────────────────────────────────────────────────────────────────┐  │
│     │ Agent executes code generation                                               │  │
│     │   ├─► Super Nemotron 3 (Architect - planning)                               │  │
│     │   ├─► Minimax/GLM/Qwen (Executors)                                          │  │
│     │   └─► Serena MCP Server (Code execution)                                     │  │
│     │         └─► Store execution vector to MuninnDB                              │  │
│     └─────────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                               │
│                                        ▼                                               │
│  6. VOICE RELAY (Vultr)                                                               │
│     ┌─────────────────────────────────────────────────────────────────────────────┐  │
│     │ Optional: Voice status updates to user                                      │  │
│     │   └─► Text-to-Speech via Gemini                                              │  │
│     │         └─► Update Notion with voice activity log                            │  │
│     └─────────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                               │
│                                        ▼                                               │
│  7. COMPLETION (Notion + MemU)                                                        │
│     ┌─────────────────────────────────────────────────────────────────────────────┐  │
│     │ Update Notion task status → "Complete"                                       │  │
│     │   └─► Archive to MemU (long-term storage)                                    │  │
│     │         └─► Log to MuninnDB (vector index)                                   │  │
│     └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Security Model

### Secret Management

All secrets are managed through the **Azure Key Vault** single source of truth:

```yaml
secrets_flow:
  azure_keyvault:
    - notion-api-key
    - gmail-app-password
    - proton-bridge-password
    - gcp-service-account
    - mycloud-password
    - gcp-gateway-url
  
  injection_points:
    - omni_sync_config.json
    - Cloudflare Worker (wrangler)
    - Notion MCP Server (Claude Desktop)
    - copaw_secret_fetcher.py (runtime injection)
```

### Inter-System Authentication

| Connection | Auth Method | Secret Source |
|------------|-------------|---------------|
| GitHub → Cloudflare | Webhook HMAC | Azure Key Vault |
| Notion API | OAuth Token | Azure Key Vault |
| MuninnDB | API Key | Local config |
| MemU | GCP Service Account | Azure Key Vault |
| Vultr | JWT Token | Azure Key Vault |
| CoPaw | API Key + MCP Auth | Azure Key Vault |

### Network Security

```yaml
network_policies:
  internal_services:
    - muninndb: localhost only (8095)
    - copaw: localhost only (8090)
  
  external_services:
    - notion: HTTPS only, verified SSL
    - memu: HTTPS with GCP auth
    - vultr: WSS with JWT validation
    - github: HTTPS webhook verification
```

---

## Configuration Reference

### Environment Variables

```bash
# Core Services
NOTION_API_KEY=<from-azure-keyvault>
GITHUB_WEBHOOK_SECRET=<from-azure-keyvault>
GCP_SERVICE_ACCOUNT=<from-azure-keyvault>
GCP_GATEWAY_URL=<from-azure-keyvault>

# Service Ports
MUNINNDB_PORT=8095
COPAW_PORT=8090
VULTR_WSS=wss://vultr.arca-vsa.tech
MEMU_HTTPS=https://memu.arca-vsa.tech

# Serena Poller
SERENA_POLL_INTERVAL=30
```

### Service Dependencies

```
GitHub ──────┬──────► Notion
             │              │
             │              ▼
             │         MuninnDB ◄───► MemU
             │              │
             ▼              ▼
           CoPaw ◄─────────┤
             │
             ▼
           Vultr
```

### Health Check Endpoints

| Service | Endpoint | Expected Response |
|---------|----------|-------------------|
| MuninnDB | `GET http://localhost:8095/v1/health` | `{"status": "ok"}` |
| CoPaw | `GET http://localhost:8090/health` | `{"status": "healthy"}` |
| Vultr | `GET https://vultr.arca-vsa.tech/health` | `{"status": "ok"}` |
| MemU | `GET https://memu.arca-vsa.tech/api/v1/health` | `{"status": "healthy"}` |

---

## Appendix: System Ports Summary

| System | Port | Protocol | Accessibility |
|--------|------|----------|---------------|
| MuninnDB | 8095 | HTTP/WebSocket | Localhost only |
| CoPaw | 8090 | HTTP/MCP | Localhost only |
| Vultr | 443 | WSS/HTTPS | External |
| MemU | 443 | HTTPS | External |
| Notion | 443 | HTTPS | External |
| GitHub | 443 | HTTPS | External |

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-01-14 | Initial consolidated architecture document |

---

*This document is the authoritative source for BiOS system architecture. For operational procedures, refer to the Biomimetics Project Wiki.*
```

This consolidated `BIOS_ARCHITECTURE_MASTER.md` file provides:

1. **Complete YAML frontmatter** with `legal_medical_audit_target: false`
2. **Full system mapping** between all six systems (GitHub, Notion, MuninnDB, MemU, Vultr, CoPaw)
3. **Architecture diagrams** showing data flow and system relationships
4. **API endpoints** for each service
5. **Integration code examples** showing how systems communicate
6. **Security model** documentation
7. **Configuration reference** with ports, protocols, and environment variables