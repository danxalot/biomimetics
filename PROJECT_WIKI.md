# Biomimetics Project Wiki

## Overview
Biomimetics is the infrastructure automation system that provides project management and optimization layer for the BiOS development ecosystem. This document serves as a comprehensive guide to all systems, integrations, functionality, and potentials for optimization and augmentation.

## Table of Contents
1. [Core Systems](#core-systems)
2. [Integrations](#integrations)
   - [IDE Integration](#0-ide-integration-vs-code-zed-antigravity)
   - [MCP Integration](#1-model-context-protocol-mcp-integration)
   - [Email MCP Server](#email-mcp-server-proton-bridge)
   - [MoE Provider Registry](#7-mixture-of-experts-moe-provider-registry)
   - [Gemma-3 Router](#8-gemma-3-dynamic-model-router)
   - [Serena MCP Servers](#9-serena-mcp-servers-workspace-segregation)
3. [Functionality](#functionality)
4. [Optimization Potentials](#optimization-potentials)
5. [Remaining Tasks](#remaining-tasks)
6. [Secrets Management](#secrets-management)
7. [Configuration Reference](#configuration-reference)

---

## Core Systems

### 1. Secret Management System
**Location**: `azure/azure_secrets_init.py`
**Purpose**: Centralized secret management via Azure Key Vault (single source of truth)

**Features**:
- Fetches secrets from Azure Key Vault
- Injects into `omni_sync_config.json`
- Updates Cloudflare Worker secrets via `wrangler`
- Configures Notion MCP Server for Claude Desktop
- Creates local encrypted backup

**Managed Secrets**:
| Secret Name | Used By |
|-------------|---------|
| `notion-api-key` | Notion API, Cloudflare Worker, MCP Server |
| `gmail-app-password` | Gmail IMAP sync |
| `proton-bridge-password` | ProtonMail 5-account sync |
| `gcp-service-account` | Google Drive API |
| `mycloud-password` | SMB NAS mount |
| `gcp-gateway-url` | GCP Cloud Functions endpoint |

### 2. Email Synchronization System
**Components**:
- **ProtonMail Sync**: `scripts/email/email_backfill.py` and daemon (5 ProtonMail accounts via local bridge on port 1143).
- **Processing Pipeline**: Local IMAP (Unverified SSL Context) → Qwen3.5-2b LLM Filter → Direct Notion API → BiOS Triage Database.
- **LLM Intelligence**: Uses a "Ruthless SKIP" prompt to specifically extract personal, financial, legal, and business affairs related to Daniel Exall or Sheila Tilmouth. Default behavior: **SKIP on ambiguity** (highly skeptical filtering).

**LLM Prompt Configuration**:
```
You are a ruthless, precision email triage agent. Your ONLY job is to identify 
emails directly related to the personal, financial, legal, or business affairs 
of 'Daniel Exall' or 'Sheila Tilmouth'. You must be highly skeptical. If an email 
is marketing, a newsletter, a generic automated alert, or spam, classify it as 
'SKIP'. ONLY classify an email as 'KEEP' if you have high confidence it requires 
human review by Daniel or Sheila. When in doubt, default to 'SKIP'.
```

**Accounts**:
| Email | Purpose |
|-------|---------|
| dan.exall@gmail.com | Primary personal |
| dan.exall@pm.me | Primary personal |
| dan@arca-vsa.tech | BiOS business |
| claws@arca-vsa.tech | AI identity |
| arca@arca-vsa.tech | BiOS projects |
| info@arca-vsa.tech | General info |

**Database Purge Utility**:
- **Script**: `scripts/email/purge_notion_triage.py`
- **Purpose**: Bulk-archive all pages in BiOS Triage database
- **Auth**: Securely fetches `notion-api-key` from Credentials Server at runtime
- **Usage**: `python3 scripts/email/purge_notion_triage.py`

### 3. File Processing System
**Location**: `scripts/omni_sync.py`
**Purpose**: Google Drive file watching with intelligent circuit breakers

**Features**:
- Google Drive file watching with circuit breakers
- Local file processing
- Notion database creation
- File size filtering (10MB limit)
- Content keyword filtering (z-lib, libgen, epub, pdf, torrent, crack, warez)

### 4. Project Tracking System
**Location**: Notion databases + MCP Server integration
**Purpose**: Task and issue management

**Databases**:
- **Biomimetic OS** (`3224d2d9fc7c80deb18dd94e22e5bb21`): Project tracking
- **Life OS Triage** (`3254d2d9fc7c81228daefc564e912546`): Email/webhook triage
- **Tool Guard** (`3254d2d9fc7c81228daefc564e912546`): Security & approvals
- **CoPaw Approval** (`3274d2d9fc7c8161a00cd9995cff5520`): Tool approvals

### 5. Event Processing System (Automated Dev Loop)
**Location**: `cloudflare/index.js` (Cloudflare Worker) & `scripts/serena/serena_notion_poller.py`
**Purpose**: Autonomous code generation and project management loop.

**The Pipeline**:
1. **Trigger**: GitHub Webhook (Issues/PRs).
2. **The Project Manager**: Cloudflare Worker using **Gemma 3 (27b/12b)** ingests the issue, drafts technical documentation, and pushes a "Ready for Dev" task to the Notion `BiOS Tasks` Database.
3. **The Architect**: The local Serena Notion Poller fetches the task and routes it to **Super Nemotron 3** via OpenCode Go to formulate a deep repository implementation plan.
4. **The Executor**: Code generation is delegated to fallback executors (Minimax 2.5 / GLM-5 / Qwen 3.5 Max).
5. **The Hands**: The LLM executes the edits locally using the **Oraios Serena MCP Server** (Language Server Protocol) running in the project directory.

**Model Hierarchy**:
```
┌─────────────────────────────────────────────────────────────────────────┐
│  THE SELF-DEVELOPING LOOP                                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Agent PM (Gemma 3 27b/12b)                                          │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ GitHub Issue → Technical Documentation → Notion             │    │
│     │ - Drafts comprehensive technical documentation              │    │
│     │ - Extracts requirements, acceptance criteria                │    │
│     │ - Links Notion URLs back to GitHub issue comments           │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                          ↓                                              │
│  2. The Architect (Nemotron 3 Super)                                    │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ "Ready for Dev" → Deep Repository Planning (1M context)     │    │
│     │ - Full repository understanding                             │    │
│     │ - High-thinking mode for architectural decisions            │    │
│     │ - Multi-file change coordination                            │    │
│     │ - Recommends best executor model                            │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                          ↓                                              │
│  3. The Executors (Minimax / GLM / Qwen)                                │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ Code Generation → Git Commit → Review                       │    │
│     │ - Minimax 2.5 (Free) - Primary for code generation          │    │
│     │ - Zhipu GLM-5 - Fallback for complex reasoning              │    │
│     │ - Qwen 3.5 Max - Fallback via Qwen Code                     │    │
│     └─────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```
<<<<<<< HEAD
=======

**Triggers**:
- **GitHub Webhooks** (Issues, PRs, Pushes) → Biomimetic OS database
  - New Issues → **Gemma 3 27b (Agent PM)** → Technical documentation → Notion
  - PRs → Status tracking in Notion
  - Pushes → Activity logging
- **Serena Agent Tasks** → Life OS Triage & Biomimetic OS databases
- **GCP Memory Insights** → Biomimetic OS (task suggestions, context updates)
- **CoPaw Requests** → Tool approval workflow, skill queuing
- **Agent Session Status**: Short session durations (e.g., 14-30s) appearing in logs are **User-Initiated Disconnects** (manual closure of the session) rather than system failures or timeouts. These are typically triggered by the user when the response is not as expected or the session needs to be reset manually.
- **Current Operational Status**: The system is operating in **Degraded Mode** for MCP services to ensure high availability. The voice relay has been stabilized to use the standard Gemini Live `audio` JSON schema.

### 5.5 Serena Code Agent - The Architect Loop
**Location**: `scripts/serena/serena_notion_poller.py` + `~/Documents/VS Code Projects/BiOS/services/agent_service/`
**Purpose**: Autonomous code execution with two-stage AI planning (Architect → Executors)

**Architecture**:
```
Notion "Ready for Dev" Tasks
       ↓ (poll every 30s)
Serena Notion Poller
       ↓ (claim task → "In Progress")
       │
       ├─ Stage 1: THE ARCHITECT (Nemotron 3 Super)
       │   ┌─────────────────────────────────────────────────────────┐
       │   │ 1M Context | High-Thinking Mode | Deep Planning        │
       │   │                                                        │
       │   │ - Repository analysis (which files affected)           │
       │   │ - Architecture decisions (patterns, interfaces)        │
       │   │ - Implementation plan (step-by-step)                   │
       │   │ - File manifest (create/modify/delete)                 │
       │   │ - Testing strategy                                     │
       │   │ - Risk assessment                                      │
       │   │ - Recommended executor model                           │
       │   └─────────────────────────────────────────────────────────┘
       │                  ↓
       └─ Stage 2: THE EXECUTORS (Fallback Matrix)
           ┌─────────────────────────────────────────────────────────┐
           │ 1. Minimax 2.5 (Free) - Primary code generation         │
           │ 2. Zhipu GLM-5 - Complex reasoning fallback             │
           │ 3. Qwen 3.5 Max - Qwen Code fallback                    │
           │                                                         │
           │ Tries models in order until success                    │
           └─────────────────────────────────────────────────────────┘
                  ↓
Code Execution (MCP tools / git)
       ↓ (git commit)
Update Notion → "Review"
       ↓
WhatsApp Notification
```

**Model Configuration**:

| Role | Model | Provider | Context | Use Case |
|------|-------|----------|---------|----------|
| **The Architect** | `nemotron-3-super-free` | NVIDIA | 1M tokens | Deep repository planning |
| **Executor (Primary)** | `minimax-m2.5-free` | MiniMax | 256K tokens | Code generation |
| **Executor (Fallback 1)** | `glm-5` | Zhipu | 128K tokens | Complex reasoning |
| **Executor (Fallback 2)** | `qwen-3.5-max` | Qwen | 256K tokens | General coding |

**Environment Variables**:
```bash
# The Architect
export OPENCODE_MODEL="nemotron-3-super-free"

# The Executors
export EXECUTOR_MODEL_PRIMARY="minimax-m2.5-free"
export EXECUTOR_MODEL_FALLBACK_1="glm-5"
export EXECUTOR_MODEL_FALLBACK_2="qwen-3.5-max"
```

**Notion Polling Behavior**:

| Setting | Default | Description |
|---------|---------|-------------|
| Poll Interval | 30 seconds | How often to check for new tasks |
| Task Timeout | 30 minutes | Auto-release if not completed |
| Sort Order | Priority DESC, Timestamp ASC | Highest priority first |
| Batch Size | 10 tasks | Max tasks per query |

**Task State Machine**:
```
Ready for Dev → In Progress → Review → Done
     ↑              ↑           ↑
     │              │           │
  Notion        Serena      Manual
  Created       Claims      Approval
```

**Indexed Project Directories**:

| Directory | Purpose |
|-----------|---------|
| `~/Documents/VS Code Projects/BiOS` | Main BiOS codebase |
| `~/biomimetics` | BiOS infrastructure |
| `~/.copaw` | CoPaw agent configuration |

**Cloud Infrastructure Access**:

| Provider | Integration |
|----------|-------------|
| **Vultr** | VM management, GPU instances |
| **Cloudflare** | Workers, Tunnels, DNS |
| **GCP** | Cloud Functions, Memory Gateway |
| **OCI** | Container instances, Key Vault |

**Example Task Flow**:

1. **GitHub Issue Created**: "Add user authentication"
2. **Gemini Parses** (Cloudflare Worker): Extracts requirements, priority, complexity
3. **Notion Task Created**: ✨ [Ready for Dev] Add user authentication
4. **Serena Polls & Claims**: Updates status to "In Progress"
5. **OpenCode Execution Plan**: 
   ```json
   {
     "analysis": "Need to implement OAuth2 flow...",
     "files": [{"path": "src/auth/google.py", "action": "create"}],
     "commit_message": "feat: Add Google OAuth2 authentication"
   }
   ```
6. **Task Completed**: Notion → "Review", WhatsApp notification sent

**Configuration**:
```bash
# Notion
export NOTION_API_KEY="ntn_xxx"
export NOTION_BIOMIMETIC_DB_ID="3224d2d9fc7c80deb18dd94e22e5bb21"

# OpenCode
export OPENCODE_API_KEY="your_key"
export OPENCODE_MODEL="minimax-m2.5-free"

# Polling
export SERENA_POLL_INTERVAL="30"
```

**Cost**: $0/month (all free tier)

**Documentation**: `scripts/serena/OPENCODE_INTEGRATION.md`

#### GitHub → Gemini → Notion Flow (The Planner)

```
┌─────────────────┐
│  GitHub Issue   │
│     Created     │
└────────┬────────┘
         │ Webhook (POST)
         ▼
┌─────────────────────────────────────────┐
│   Cloudflare Worker                     │
│   (arca-github-notion-sync)             │
│                                         │
│  1. Validate webhook signature          │
│  2. Parse issue payload                 │
│  3. Route to Gemini handler             │
└────────┬────────────────────────────────┘
         │
         │ POST /v1beta/models/gemini-3.1-flash-lite-preview:generateContent
         ▼
┌─────────────────────────────────────────┐
│   Gemini 3.1 Flash Lite Preview API     │
│   (Free Tier)                           │
│                                         │
│  Prompt:                                │
│  "Analyze this GitHub issue and         │
│   extract technical requirements..."    │
│                                         │
│  Returns JSON:                          │
│  - summary                              │
│  - technical_requirements[]             │
│  - acceptance_criteria[]                │
│  - dependencies[]                       │
│  - priority (Low/Medium/High)           │
│  - estimated_complexity                 │
└────────┬────────────────────────────────┘
         │
         │ Parsed JSON
         ▼
┌─────────────────────────────────────────┐
│   Cloudflare Worker                     │
│                                         │
│  4. Format Notion payload               │
│  5. Create "Ready for Dev" task         │
└────────┬────────────────────────────────┘
         │
         │ POST /v1/pages
         ▼
┌─────────────────────────────────────────┐
│   Notion API                            │
│   (Biomimetic OS Database)              │
│   ID: 3224d2d9fc7c80deb18dd94e22e5bb21 │
│                                         │
│  Creates page with:                     │
│  - Title: ✨ [Ready for Dev] {title}    │
│  - Status: Ready for Dev                │
│  - Priority: {from Gemini}              │
│  - Complexity: {from Gemini}            │
│  - Description: Formatted requirements  │
│  - GitHub Link                          │
│  - Memory UUID                          │
└────────┬────────────────────────────────┘
         │
         │ Forward to GCP Memory
         ▼
┌─────────────────────────────────────────┐
│   GCP Memory Gateway                    │
│   (memory-orchestrator)                 │
│                                         │
│  Stores context in:                     │
│  - MuninnDB (long-term memory)          │
│  - MemU (contextual AI)                 │
└─────────────────────────────────────────┘
```

**Gemini Flash Lite Prompt Template**:
```
You are a technical requirements analyst for a software development team.
Analyze this GitHub issue and extract technical requirements.

GitHub Issue:
- Title: {issue.title}
- Repository: {repository.full_name}
- Author: {issue.user.login}
- Labels: {labels}

Description:
{issue.body}

Extract and format the following:
1. **Summary**: One-sentence summary of what needs to be built/fixed
2. **Technical Requirements**: Bullet list of specific technical requirements
3. **Acceptance Criteria**: Bullet list of conditions that must be met
4. **Dependencies**: Any mentioned dependencies or related systems
5. **Priority**: Low/Medium/High based on urgency indicators

Respond in valid JSON format:
{
  "summary": "...",
  "technical_requirements": ["req1", "req2"],
  "acceptance_criteria": ["criteria1", "criteria2"],
  "dependencies": ["dep1", "dep2"],
  "priority": "Medium",
  "estimated_complexity": "Low/Medium/High"
}
```

**Notion Task Format**:
```json
{
  "Name": "✨ [Ready for Dev] Add user authentication",
  "Status": "Ready for Dev",
  "Priority": "High",
  "Complexity": "Medium",
  "Description": "## Summary\nImplement OAuth2 authentication...\n\n## Technical Requirements\n- Add Google OAuth provider\n- Store tokens securely\n...",
  "Github Link": "https://github.com/org/repo/issues/123",
  "Memory_UUID": "uuid-here"
}
```

**Benefits**:
- ✅ **Free AI Processing**: Gemini 3.1 Flash Lite Preview is free tier
- ✅ **Structured Output**: JSON parsing ensures consistent formatting
- ✅ **Priority Detection**: Auto-prioritization based on issue content
- ✅ **Ready for Dev**: Tasks are immediately actionable
- ✅ **Fallback**: Basic sync if Gemini API unavailable

### 6. Native VPC Memory Architecture (CRITICAL)
**Location**: Dedicated GCP VM (`muninn-global`) & GCP Cloud Function (`memory-orchestrator`).
**Purpose**: Unified, cloud-native memory system for high-availability agent context featuring ACT-R activation/decay logic and vector-semantic search.

#### Hardware & Network Topology
- **Working Memory (MuninnDB)**: Hosted on a persistent GCP Compute Engine VM (`muninn-global`).
  - **Service**: Native Go-based MuninnDB service binding to `0.0.0.0:8475`.
  - **Native VPC Routing**: Secured via **Serverless VPC Access** (`muninn-connector`) using **Internal IP** (`10.128.0.3`).
  - **Developer Access**: Secured via **Tailscale** (`100.114.166.88`) for direct agent/developer access.
  - **Performance**: High-availability configuration with a **60s gateway timeout** to support deep semantic scans.
- **Archive Memory (MemU)**: Hosted on **GCP Cloud Run** (Stateless).
  - **Backend**: Qdrant Cloud (Vector) + Firebase Firestore (Metadata).
  - **Embedding**: `gemini-embedding-2-preview` (1536 dimensions).

#### Operational Logic & Pipelines
1. **Direct API Access**: Interaction occurs via the native Go REST API:
   - `/api/activate`: Main activation endpoint for memory retrieval.
   - `/api/engrams`: Endpoint for memory storage and persistence.
2. **ACT-R Memory Tiering**:
   - **Tier 1 (MuninnDB)**: High-priority, high-volatility working memory with activation/decay logic.
   - **Tier 2 (MemU)**: Long-term archive memory for stability and scale (Medical, Disability, Business context).
3. **Cloud-to-Cloud Ingestion**: GDrive `Obsidian-life` vault is directly ingested into MuninnDB via GCP Service Account auth, bypassing local storage.
4. **Stateless Policy**: CoPaw nodes operate as stateless executors; all long-term context is externalized to the GCP Gateway.

#### Memory Orchestration Invariants
- **API Keys**: MUST be fetched dynamically via the `credentials_server.py`. Hardcoded keys (e.g., `google_api_key`) are forbidden.
- **Service Account**: All GCP operations use the centralized service account defined in `gcp-service-agent.json`.
- **Latency Targets**: Vector retrieval should complete within <300ms; full semantic pipeline within <2s.
- **Error Visibility (The GCP Tax)**: The `CoPawAgent` implements robust `try...except` blocks that capture and log `response.status_code` and `response.text`. This is critical for identifying GCP IAM errors (e.g., "Audience mismatch") which return 401/403 with descriptive bodies.

### 7. Approval Workflow System
**Location**: CoPaw tool guard & Cloudflare Worker (`whatsapp-notifier`)
**Purpose**: Safe AI agent operations and human-in-the-loop (HITL) authorization.

**Integration**: 
- CoPaw ↔ Cloudflare Worker ↔ Green API ↔ WhatsApp (End User)
- **Bypass Mechanism**: Utilizes the 3rd-party Green API to bypass Meta Business API restrictions, allowing seamless, always-on WhatsApp routing to a personal number.

**Architecture**:
```
CoPaw Tool Guard
       ↓ (approval request)
Cloudflare Worker (/notify)
       ↓ (Green API sendMessage)
Green API (7107.api.greenapi.com)
       ↓ (WhatsApp message)
User WhatsApp (End User)
       ↓ (user replies "APPROVE abc123")
Green API Webhook
       ↓ (incomingMessageReceived)
Cloudflare Worker (/webhook)
       ↓ (parsed command)
CoPaw Webhook Receiver (via Tunnel)
       ↓ (update Notion)
Notion Tool Guard Database
```
| `/webhook` | POST | Receive incoming messages from Green API |
| `/response` | POST | Handle parsed approval responses |
| `/health` | GET | Health check |
| `/test` | POST | Send test message |

**Environment Variables** (wrangler.toml):

```bash
# Green API credentials (set via wrangler secret put)
GREEN_API_ID="7107560335"
GREEN_API_TOKEN="your_token_here"
GREEN_API_URL="https://7107.api.greenapi.com"
USER_WHATSAPP_NUMBER="1234567890@c.us"
COPAW_WEBHOOK_URL="https://your-tunnel.cloudflare.com/webhook"
```

**Approval Message Format**:
```
🔒 *Tool Approval Required*

*Tool:* `execute_shell_command`
*Arguments:* `{"command": "git push origin main"}`
*Context:* Deploying to production

*Risk Level:* high

*Approval ID:* `abc123`

*Reply with:*
✅ APPROVE abc123
❌ DENY abc123

*⏱️  Timeout: 5 minutes*
```

**Supported Commands**:

| Command | Example | Confidence |
|---------|---------|------------|
| APPROVE + ID | `APPROVE abc123` | 95% |
| DENY + ID | `DENY abc123` | 95% |
| Emoji APPROVE | `✅ APPROVE abc123` | 95% |
| Emoji DENY | `❌ DENY abc123` | 95% |
| ID only | `abc123` | 70% (implicit approve) |

**Green API Webhook Payload**:
```json
{
  "typeWebhook": "incomingMessageReceived",
  "instanceData": { "idInstance": 7107560335 },
  "timestamp": 1234567890,
  "idMessage": "...",
  "senderData": { "chatId": "1234567890@c.us" },
  "messageData": {
    "typeMessage": "textMessage",
    "textMessageData": { "text": "APPROVE abc123" }
  }
}
```

**CoPaw Forward Payload**:
```json
{
  "type": "whatsapp_approval_response",
  "from": "1234567890@c.us",
  "approval_id": "abc123",
  "action": "approve",
  "timestamp": "2026-03-23T12:00:00Z",
  "raw_message": "APPROVE abc123",
  "confidence": 0.95,
  "source": "green-api"
}
```

**Setup Steps**:

1. **Green API Account**:
   - Visit https://greenapi.com/
   - Create account and get instance ID + token
   - Configure webhook URL in Green API dashboard

2. **Cloudflare Worker**:
   ```bash
   cd cloudflare/whatsapp-notifier
   wrangler secret put GREEN_API_ID
   wrangler secret put GREEN_API_TOKEN
   wrangler secret put GREEN_API_URL
   wrangler secret put USER_WHATSAPP_NUMBER
   wrangler secret put COPAW_WEBHOOK_URL
   wrangler deploy
   ```

3. **Green API Webhook Configuration**:
   - In Green API dashboard, set webhook URL to:
     `https://whatsapp-notifier.your-subdomain.workers.dev/webhook`
   - Enable incoming message webhooks

4. **Test Integration**:
   ```bash
   curl -X POST https://whatsapp-notifier.your-subdomain.workers.dev/test \
     -H "Content-Type: application/json" \
     -d '{"message": "Test message"}'
   ```

**Credentials Server Integration**:

Green API credentials are stored in Azure Key Vault and fetched via Credentials Server:

```python
from copaw_secret_fetcher import get_secret

green_api_id = get_secret("green_api_id")
green_api_token = get_secret("green_api_token")
green_api_url = get_secret("green_api_url")
```

**Troubleshooting**:

| Issue | Solution |
|-------|----------|
| "Green API not configured" | Check wrangler secrets are set |
| "Message not sent" | Verify Green API token is valid |
| "Webhook not received" | Check Green API dashboard webhook URL |
| "Command not parsed" | Ensure message matches APPROVE/DENY pattern |

**Cost**:

| Component | Cost |
|-----------|------|
| Green API | Free tier: 1,000 messages/month |
| Cloudflare Worker | Free: 100K requests/day |
| **Total** | **$0/month** (typical usage) |

**Related Documentation**:

- `cloudflare/whatsapp-notifier/src/worker.js` - Worker implementation
- `scripts/copaw/copaw-tool-guard.py` - Tool guard with approval workflow
- [Green API Docs](https://greenapi.com/docs/)

### 8. System Monitoring System
**Location**: macOS LaunchAgents
**Purpose**: Continuous operation monitoring

**Agents**:
| Agent | Interval | Purpose |
|-------|----------|---------|
| `com.arca.omni-sync.plist` | Continuous | Main sync heartbeat |
| `com.arca.proton-sync.plist` | 3600s (1hr) | Email sync |
| `com.arca.mycloud-watchdog.plist` | 60s | NAS mount keepalive |

## 5. BiOS Phase 1.5.2 - Tailscale VPN Integration

The BiOS voice relay has been migrated from a public IP to a secure private Tailscale network.

### Refactor Highlights
- **Dynamic Config**: `VoiceChannel` now reads `relay_url` from `config.json`.

### 9. Live Voice Interface (BiOS Voice)
**Location**: `bios-voice.sh` / `src/copaw/app/channels/voice/`
**Purpose**: Native terminal-based Gemini 3.1 Live API interaction with integrated browser HUD.

**Features**:
- Real-time voice interaction with ultralow latency (<100ms pipeline).
- Integrated with BiOS project briefings and repositories.
- **PTT Override**: Spacebar interrupts AI output instantly.
- **Mic Mute**: 'm' key for privacy with visual status feedback.
- **Native HUD**: Renders visual payloads directly in the browser console.

> [!WARNING]
> Background or daemonized execution of the voice agent is strictly forbidden. All sessions must be started manually via `./scripts/sys/bios-voice.sh` to ensure user control and process visibility.

### 9.5 BiOS True Architecture (Phase 1.5.1)
**Objective**: Hard decommission of legacy "Jarvis" logic in favor of a high-performance, Python-native WebSocket Relay.

**Architecture (Tailscale VPN)**:
- **VPN Mesh**: Secure private networking via Tailscale. Connects local terminal to Vultr VPS `100.86.112.119`.
- **Client (CoPaw)**: Uses a dedicated `VoiceChannel` with a `VultrRelayClient` implemented in Python (`websockets` + `PyAudio`). Relay URL is configurable in `config.json`.
- **Relay (Vultr)**: `100.86.112.119:8765/ws/live` handles the Gemini 3.1 Live API handshake.
- **Protocol**: Raw 16-bit PCM, 16kHz audio I/O via `PyAudio`.

**Manual Controls & Interrupt Schema**:
| Key | Action | Function |
|-----|--------|----------|
| **Spacebar (PTT)** | Interrupt / Force Talk | Overrides "ducking" (echo cancellation) and tells Gemini to yield its turn. |
| **'m' Key (Toggle)** | Mic Mute | Stop mic transmission. Displays `[🔇 MIC MUTED]` or `[🎤 MIC LIVE]` in terminal. |
| **Ctrl+C** | Termination | Graceful shutdown of the WebSocket and audio streams. |

**Voice Processing (VAD & Noise Floor)**:
- **WebRTCVAD**: Aggressive voice activity detection (Mode 3) eliminates background noise transmission.
- **Noise Floor Tuning**: Uses a rolling RMS history (100 samples) and `statistics.median` to calculate a dynamic baseline, capped at 400 to prevent adaptation to loud transients.
- **Async Efficiency**: Math overhead (RMS/Median) is rate-limited and optimized to prevent blocking the `asyncio` loop, maintaining <50ms latency.
- **Queue Drainage Policy**: During mic mute, the microphone queue is still drained to prevent buffer backlogs, but frames are discarded before transmission.

**Verification**:
- Jarvis logic (daemon/wake scripts) permanently removed.
- Background process execution (daemonization) decommissioned.
- Manual entry point: [bios-voice.sh](file:///Users/danexall/biomimetics/scripts/sys/bios-voice.sh).

### 9.6 BiOS HUD - Visual Event Emitter (Phase 3)
**Objective**: Enable the voice terminal to push visual components to the CoPaw browser UI without interrupting the audio stream.

**Architecture (Native Integration)**:
1. **Gemini**: Invokes the `render_canvas` tool with a visual payload (`view`/`content`).
2. **Vultr Relay**: Passes the tool call as a JSON message to the CoPaw `VultrRelayClient`.
3. **CoPaw Backend**: `VultrRelayClient` intercepts the tool call and pushes it to the native CoPaw console via HTTP POST `/console/push`.
4. **Native Console HUD**: The built-in console (`index.html`) is patched with `hud.js`, which polls `/console/push-messages` and renders the payload.
5. **Rendering**: Uses `marked.js` to natively render Markdown inside a glassmorphism overlay (`#copaw-hud-container`) on top of the main UI.

**Key Components**:
- [render_canvas.py](file:///Users/danexall/biomimetics/scripts/copaw/src/copaw/agents/tools/render_canvas.py): The tool definition (signaling anchor).
- [hud.js](file:///Users/danexall/biomimetics/scripts/copaw/src/copaw/console/assets/hud.js): The frontend bridge that manages the overlay and state tracking.
- [hud.css](file:///Users/danexall/biomimetics/scripts/copaw/src/copaw/console/assets/hud.css): Modern styling for the visual overlay.

> [!NOTE]
> The legacy React app in `DEPRECATED_gemini-live-voice/` is decommissioned. All visual feedback is now routed to the primary CoPaw console at `http://localhost:8090/`.



### 10. Cloud Infrastructure (Vultr + Tailscale)
**Purpose**: Always-on, decoupled edge endpoints for high-availability services (e.g., Gemini Live Relay). 

**Network Architecture**:
- **Tailscale VPN**: The VPS is joined to the private BiOS Tailscale network.
- **Relay Endpoint**: `ws://100.86.112.119:8765/ws/live` (Private Tailscale IP).
- **Access Procedure (CRITICAL)**:
  - **Primary Access**: SSH via Tailscale IP `100.86.112.119`.
  - **SSH Key Management**: The **Azure Key Vault managed SSH key** (`vultr-ssh-key` in `arca-mcp-kv-dae`) is the mandatory primary authentication method for agents and automated systems.
    - **Note on UUIDs vs Keys**: Previously, the `vultr-ssh-key` secret erroneously contained `7a9a0937-916b-416a-ba31-6006630b0b78` (which was merely an internal Vultr UUID identifier, NOT the PEM private key). This caused automated access to fail. The secret has now been securely updated to contain the valid `arca_vultr` Ed25519 private key material.
  - **Key Security & Agent Log Retrieval**: Under NO circumstances should an agent download or save the SSH private key to a local file on disk. When an agent needs to retrieve logs via SSH, the key MUST be kept entirely in-memory or passed securely without leaving a persistent file (e.g., by fetching it via the credentials server or standard Azure CLI and passing it via memory/process substitution to standard tools, or using SSH agent directly).
  - **Authorized Keys**: Do **NOT** modify `/root/.ssh/authorized_keys` manually on the VPS. The authorized keys are synced from the Azure Key Vault.
  - **Password Access**: Password authentication (`9[NorZ3)X2+G$[oM`) is strictly a **break-glass fallback** for manual recovery by the user. Agents are forbidden from using or recording this password except in emergencies directed by the user.
- **Hardening**: Services no longer bind to public IP `149.248.32.53`. Firewalls only allow Tailscale traffic on the relay port.

**Actionable VPS Setup**:
```bash
# 1. Install Tailscale on Vultr VPS
curl -fsSL https://tailscale.com/install.sh | sh

# 2. Authenticate and bring up the node
sudo tailscale up

# 3. Retrieve the private 100.X.X.X IP
tailscale ip -4

# 4. Bind the Gemini Relay to the Tailscale interface (in gemini_relay/main.py)
# Ensure host="0.0.0.0" or explicitly the Tailscale IP.
```

**Management**: Managed via `scripts/cloud_infrastructure/vultr_provision.py`.

---

## Integrations

### 0. IDE Integration (VS Code, Zed, Antigravity)
**Purpose**: Unified MCP server configuration across all IDEs with dynamic secret injection from Credentials Server.

**Architecture**:
```
┌─────────────────────────────────────────────────────────────────┐
│  Credentials Server (localhost:8089)                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Azure Key Vault Gateway                                  │   │
│  │ - notion-api-key                                         │   │
│  │ - github-token                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         │ GET /secrets/...   │ GET /secrets/...   │ GET /secrets/...
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  VS Code        │  │  Zed Editor     │  │  Antigravity    │
│  ~/.vscode/     │  │  ~/.zed/        │  │  ~/.antigravity/│
│  mcp.json       │  │  settings.json  │  │  mcp_config.json│
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
                              ▼
                   ┌─────────────────────┐
                   │  MCP Wrapper        │
                   │  ~/.bios/mcp/       │
                   │  - notion-mcp-wrapper.sh │
                   │  - github-mcp-wrapper.sh │
                   └─────────────────────┘
                              │
                              ▼
                   Fetches secrets at runtime
                   Sets env vars → Executes npx
```

**Configuration Script**: `scripts/ide/sync_ide_mcp.py`

**Usage**:
```bash
# Ensure Credentials Server is running
python3 -m scripts.secret_manager.credentials_server

# Run IDE synchronization
python3 scripts/ide/sync_ide_mcp.py
```

**Generated Files**:

| File | Purpose |
|------|---------|
| `~/.bios/mcp/notion-mcp-wrapper.sh` | Wrapper that fetches Notion token at runtime |
| `~/.bios/mcp/github-mcp-wrapper.sh` | Wrapper that fetches GitHub token at runtime |
| `~/.vscode/mcp.json` | VS Code MCP server configuration |
| `~/.zed/settings.json` | Zed MCP server configuration |
| `~/.antigravity/mcp_config.json` | Antigravity MCP server configuration |

**Wrapper Script Behavior**:
```bash
#!/bin/bash
# 1. Fetch secret from Credentials Server
NOTION_TOKEN=$(curl -s http://localhost:8089/secrets/notion-api-key \
  -H "X-API-Key: $CREDENTIALS_API_KEY" | jq -r '.value')

# 2. Set environment variable
export NOTION_TOKEN

# 3. Execute MCP server
exec npx -y @notionhq/notion-mcp-server
```

**Benefits**:
- ✅ **No hardcoded secrets** in IDE configuration files
- ✅ **Centralized secret management** via Azure Key Vault
- ✅ **Automatic secret rotation** - update in Azure KV, all IDEs get new value
- ✅ **Audit logging** via Credentials Server
- ✅ **Consistent configuration** across VS Code, Zed, Antigravity

**Troubleshooting**:

| Issue | Solution |
|-------|----------|
| "Credentials Server not accessible" | Start with: `python3 -m scripts.secret_manager.credentials_server` |
| "Secret not found" | Add to Azure KV: `az keyvault secret set --vault-name arca-mcp-kv-dae --name <name> --value <value>` |
| "MCP server not starting" | Check wrapper script permissions: `chmod +x ~/.bios/mcp/*.sh` |
| "IDE doesn't see MCP servers" | Restart IDE after running `sync_ide_mcp.py` |

**Related Documentation**:
- `scripts/ide/sync_ide_mcp.py` - IDE synchronization script
- `scripts/secret_manager/credentials_server.py` - Credentials Server
- `scripts/secret_manager/copaw_secret_fetcher.py` - Secret fetching utility

### 1. Model Context Protocol (MCP) Integration
**Purpose**: Standardized interface for AI models to access external tools and data

**Servers**:

#### Email MCP Server (Proton Bridge)
**Location**: `scripts/copaw/mcp_email_server.py`
**Purpose**: Secure IMAP reading and SMTP sending via local Proton Mail Bridge

**Architecture**:
```
┌─────────────────────────────────────────────────────────────────┐
│  Credentials Server (localhost:8089)                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Azure Key Vault Gateway                                  │   │
│  │ - proton-bridge-password                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │
         │ GET /secrets/proton-bridge-password
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  MCP Email Server (FastMCP)                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Tools:                                                   │   │
│  │ - read_recent_emails(account, limit)                     │   │
│  │ - send_email(to, subject, body)                          │   │
│  │ - search_emails(query)                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```
