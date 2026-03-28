# Biomimetics Project Wiki

## Overview
Biomimetics is the infrastructure automation system that provides project management and optimization layer for the ARCA development ecosystem. This document serves as a comprehensive guide to all systems, integrations, functionality, and potentials for optimization and augmentation.

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
| dan.exall@pm.me | Primary personal |
| dan@arca-vsa.tech | ARCA business |
| claws@arca-vsa.tech | AI identity |
| arca@pm.me | ARCA projects |
| info@pm.me | General info |

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
2. **The Project Manager**: Cloudflare Worker using **Gemma 3 (27b/12b)** ingests the issue, drafts technical documentation, and pushes a "Ready for Dev" task to the Notion `ARCA Tasks` Database.
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

**Triggers**:
- **GitHub Webhooks** (Issues, PRs, Pushes) → Biomimetic OS database
  - New Issues → **Gemma 3 27b (Agent PM)** → Technical documentation → Notion
  - PRs → Status tracking in Notion
  - Pushes → Activity logging
- **Serena Agent Tasks** → Life OS Triage & Biomimetic OS databases
- **GCP Memory Insights** → Biomimetic OS (task suggestions, context updates)
- **CoPaw Requests** → Tool approval workflow, skill queuing

### 5.5 Serena Code Agent - The Architect Loop
**Location**: `scripts/serena/serena_notion_poller.py` + `~/Documents/VS Code Projects/ARCA/services/agent_service/`
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
| `~/Documents/VS Code Projects/ARCA` | Main ARCA codebase |
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
**Location**: GCP Cloud Function (`memory-orchestrator`) & Dedicated VM (`muninn-global`)
**Purpose**: Unified, cloud-native memory system for high-availability agent context with ACT-R decay logic.

#### Hardware & Network Topology
- **Working Memory (MuninnDB)**: Hosted on a persistent GCP Compute Engine VM (`muninn-global`).
  - **Native VPC Routing**: Secured via **Serverless VPC Access** (`muninn-connector`) using **Internal IP** (`10.128.0.3`).
  - **Developer Access**: Secured via **Tailscale** (`100.114.166.88`) for direct agent/developer access.
  - **Performance**: Increased gateway timeout to **30s** to accommodate deep vector searches.
- **Archive Memory (MemU)**: Hosted on **GCP Cloud Run** (Stateless).
  - **Backend**: Qdrant Cloud (Vector) + Firebase Firestore (Metadata).
  - **Embedding**: `gemini-embedding-2-preview` (1536 dimensions).

#### Operational Logic & Pipelines
1. **Proactive Retrieval**: Agent intercepts user messages, queries `/search` via GCP Orchestrator, and injects context into system prompts before inference.
2. **ACT-R Memory Tiering**:
   - **Tier 1 (MuninnDB)**: High-priority, high-volatility working memory with activation/decay logic.
   - **Tier 2 (MemU)**: Long-term archive memory for stability and scale (Medical, Disability, Business context).
3. **Cloud-to-Cloud Ingestion**: GDrive `Obsidian-life` vault is directly ingested into MuninnDB via GCP Service Account auth, bypassing local storage.
4. **Stateless Policy**: CoPaw nodes operate as stateless executors; all long-term context is externalized to the GCP Gateway.

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

⏱️  Timeout: 5 minutes
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

### 9. Live Voice Interface
**Location**: `gemini-live-voice/`
**Purpose**: Gemini Live API for voice/vision interaction

**Features**:
- Voice/Vision interaction via Gemini Live API
- Real-time conversation capabilities
- Integrated with ARCA project briefings

### 10. Cloud Infrastructure (Vultr Edge)
**Purpose**: Always-on, decoupled edge endpoints for high-availability services (e.g., Gemini Live Relay).

**Specifications**:
- **Provider**: Vultr (API automated via `vultr_provision_headless.py`)
- **Instance**: `vc2-1c-0.5gb-free` (0.5 vCPU, 512MB RAM, 10GB disk)
- **OS**: Debian 12 (Bookworm)
- **Routing**: Secured and exposed via persistent Cloudflare Tunnel (`gemini-relay.arca-vsa.tech`).

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
│  │ - send_email(account, to, subject, body)                 │   │
│  │ - list_accounts()                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │
         │ IMAP: 127.0.0.1:1143 (STARTTLS)
         │ SMTP: 127.0.0.1:1025 (STARTTLS)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Proton Mail Bridge                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 5 ProtonMail Accounts:                                   │   │
│  │ - dan.exall@pm.me                                        │   │
│  │ - dan@arca-vsa.tech                                      │   │
│  │ - arca@arca-vsa.tech                                     │   │
│  │ - info@arca-vsa.tech                                     │   │
│  │ - claws@arca-vsa.tech                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Tools**:

| Tool | Parameters | Description |
|------|------------|-------------|
| `read_recent_emails` | `account: str`, `limit: int = 5` | Fetch recent emails from specified account |
| `send_email` | `account: str`, `to_address: str`, `subject: str`, `body: str` | Send email from specified account |
| `list_accounts` | None | List all configured ProtonMail accounts |

**Connection Details**:
- **IMAP**: `127.0.0.1:1143` (STARTTLS upgrade)
- **SMTP**: `127.0.0.1:1025` (STARTTLS upgrade)
- **SSL**: Unverified context (localhost bypass)

**Usage Example**:
```python
# Read 5 recent emails from dan@arca-vsa.tech
read_recent_emails(account="dan@arca-vsa.tech", limit=5)

# Send an email
send_email(
    account="dan@arca-vsa.tech",
    to_address="recipient@example.com",
    subject="Test Email",
    body="Hello from MCP Email Server!"
)

# List available accounts
list_accounts()
```

**Response Format** (read_recent_emails):
```
📧 Recent Emails for dan@arca-vsa.tech (5 emails):

1. Subject: Your credit is expiring soon!
   From: alerts@creditcard.com
   Date: Mon, 24 Mar 2026 10:30:00 +0000
   Body: Your credit line is expiring soon. Please renew...

2. Subject: Vultr.com: Cloud Server Activated
   From: noreply@vultr.com
   Date: Sun, 23 Mar 2026 15:45:00 +0000
   Body: Your cloud server has been activated...
```

**Security**:
- ✅ Credentials fetched from Credentials Server at runtime
- ✅ No hardcoded passwords in script
- ✅ STARTTLS encryption for IMAP and SMTP
- ✅ Localhost-only connections (Proton Bridge)

**Dependencies**:
```bash
pip install mcp
```

**Running the Server**:
```bash
# Start MCP Email Server (stdio transport - for MCP client integration)
python3 scripts/copaw/mcp_email_server.py

# For CoPaw integration, add to MCP configuration (see CoPaw MCP config below)
```

**CoPaw MCP Configuration** (`~/.copaw/config.json`):
```json
{
  "mcp": {
    "clients": {
      "email_mcp": {
        "name": "email_mcp",
        "description": "Email MCP server for Proton Bridge and Gmail integration",
        "enabled": true,
        "transport": "stdio",
        "url": "",
        "headers": {},
        "command": "python3",
        "args": [
          "/Users/danexall/biomimetics/scripts/copaw/mcp_email_server.py"
        ],
        "env": {},
        "cwd": "/Users/danexall/biomimetics/scripts/copaw"
      },
      "tavily_search": {
        "name": "tavily_mcp",
        "description": "",
        "enabled": false,
        "transport": "stdio",
        "url": "",
        "headers": {},
        "command": "npx",
        "args": [
          "-y",
          "tavily-mcp@latest"
        ],
        "env": {
          "TAVILY_API_KEY": ""
        },
        "cwd": ""
      },
      "serena_arca": {
        "name": "serena_arca_mcp",
        "description": "Serena MCP server for ARCA project - semantic code analysis",
        "enabled": true,
        "transport": "stdio",
        "url": "",
        "headers": {},
        "command": "uvx",
        "args": [
          "--from",
          "git+https://github.com/oraios/serena",
          "serena",
          "start-mcp-server",
          "/Users/danexall/Documents/VS Code Projects/ARCA"
        ],
        "env": {},
        "cwd": "/Users/danexall/Documents/VS Code Projects/ARCA"
      },
      "serena_bios": {
        "name": "serena_bios_mcp",
        "description": "Serena MCP server for BiOS project - semantic code analysis",
        "enabled": true,
        "transport": "stdio",
        "url": "",
        "headers": {},
        "command": "uvx",
        "args": [
          "--from",
          "git+https://github.com/oraios/serena",
          "serena",
          "start-mcp-server",
          "/Users/danexall/biomimetics"
        ],
        "env": {},
        "cwd": "/Users/danexall/biomimetics"
      },
      "notion": {
        "name": "notion_mcp",
        "description": "Notion MCP server for BiOS Root sync",
        "enabled": true,
        "transport": "stdio",
        "url": "",
        "headers": {},
        "command": "npx",
        "args": [
          "-y",
          "@mieubrisse/notion-mcp-server"
        ],
        "env": {},
        "cwd": ""
      }
    }
  }
}
```

**Integration with CoPaw**:
 1. The Email MCP server is already configured in `~/.copaw/config.json` under `mcp.clients.email_mcp`
 2. Restart CoPaw to load the MCP server
 3. Email tools (`read_recent_emails`, `send_email`, `list_accounts`) will be available alongside Serena and other MCP servers

**Testing**:
```bash
# Test the MCP server directly (shows available tools)
python3 -c "
from scripts.copaw.mcp_email_server import mcp
print('Available tools:', [t.name for t in mcp._tools.values()])
"
```
- **Notion MCP Server**: `@notionhq/notion-mcp-server`
- **GitHub MCP Server**: Custom deployment on Azure ACI

**Configuration**:
```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "[NOTION_TOKEN_REDACTED]"
      }
    },
    "github": {
      "url": "http://github-mcp-sse.westus2.azurecontainer.io:8080/sse",
      "transport": "sse",
      "description": "GitHub MCP via Azure ACI"
    }
  }
}
```

**Integrated Clients**:
- Claude Desktop ✅
- Qwen Code ✅
- Zed Editor (Partial - needs GitHub MCP) ⚠️
- Antigravity (Not configured) ❌
- ARCA Project (Not configured) ❌

**Serena MCP Server**: `oraios/serena` installed locally via `uv`/`pipx`. Operates via `stdio` to provide Language Server Protocol (LSP) semantic code retrieval and editing to the local LLM executors.

**Universal IDE Synchronization**: `scripts/ide/sync_ide_mcp.py` automatically generates MCP configs for Zed, VS Code, and Antigravity. It points them to wrapper scripts (`~/.bios/mcp/*.sh`) that dynamically fetch secrets from the Credentials Server at runtime, ensuring no hardcoded keys exist in IDE configs.

### 2. Azure Key Vault Integration
**Purpose**: Centralized secret management

**Resources**:
- Container Registry: `arcamcpconsolidated` (eastus)
- Key Vault: `arca-mcp-kv-dae` (67 secrets including `github-token`)
- Key Vault: `arca-mcp-kv-dae2` (backup)
- Resource Group: `arca-consolidated` (eastus)


### 4. Cloudflare Workers Integration
**Purpose**: Multi-system integration hub

**Worker URL**: `https://arca-github-notion-sync.dan-exall.workers.dev`

**Capabilities**:
- GitHub → Notion bridge (Issues, PRs, Pushes)
- Serena Agent → Notion integration
- GCP Memory ↔ Biomimetic OS routing
- CoPaw approval workflow integration

### 5. Proton Mail Bridge Integration
**Purpose**: Secure email access for 5 ProtonMail accounts

**Configuration**:
- Port: 1143 (localhost)
- Accounts: 5 ProtonMail accounts configured
- Processing: IMAP access via local bridge

### 6. NAS Storage Integration
**Purpose**: Persistent storage for large files

**Target**: 192.168.0.103 (MyCloud Home NAS)
**Mount Point**: `/Volumes/danexall`
**Maintenance**: Watchdog script maintains SMB connection

### 7. Cloud Infrastructure (Vultr)
**Purpose**: Free tier VPS hosting for lightweight services (Gemini Relay, etc.)

**Provisioning Script**: `scripts/cloud_infrastructure/vultr_provision.py`

**Free Tier Specifications**:

| Specification | Value |
|---------------|-------|
| **Plan** | `vc2-1c-0.5gb-free` |
| **vCPU** | 0.5 cores |
| **RAM** | 512 MB |
| **Storage** | 10 GB SSD |
| **Bandwidth** | 0.5 TB |
| **Monthly Cost** | $0.00 |

**Default Configuration**:

| Setting | Value | Notes |
|---------|-------|-------|
| **Region** | `lhr` (London) | Primary, falls back to Amsterdam/Frankfurt |
| **OS** | Debian 12 (bookworm) | OS ID: 477 |
| **Backups** | Disabled | No hidden charges |
| **IPv6** | Disabled | Keep configuration simple |
| **DDoS Protection** | Disabled | Not needed for free tier |

**Usage**:

```bash
# Set API key
export VULTR_API_KEY="your_api_key_here"

# Run provisioner (interactive)
python3 scripts/cloud_infrastructure/vultr_provision.py

# The script will:
# 1. Verify your Vultr account
# 2. Check free tier plan availability
# 3. Verify Debian 12 OS availability
# 4. Prompt for cloud-init script path (optional)
# 5. Show configuration summary
# 6. Wait for user confirmation
# 7. Create instance and wait for activation
# 8. Display SSH connection details
```

**Cloud-Init Integration**:

The provisioner supports automatic script injection via cloud-init user-data:

1. Script prompts: "Please provide the local path to your startup/provisioning scripts"
2. User provides path (e.g., `/path/to/gemini_relay/scripts/setup_vps.sh`)
3. Script is base64-encoded and attached as `user_data`
4. On first boot, cloud-init automatically executes the script
5. Log output available at `/var/log/cloud-init-output.log`

**Example Cloud-Init Script** (Gemini Relay Setup):

```bash
#!/bin/bash
# /Users/danexall/biomimetics/gemini_relay/scripts/setup_vps.sh

# Update system
apt-get update && apt-get upgrade -y

# Install Python 3.12
apt-get install -y python3.12 python3.12-venv python3-pip

# Install cloudflared
curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i /tmp/cloudflared.deb

# Create gemini user
useradd -r -s /bin/false -d /opt/gemini_relay gemini

# Setup application directory
mkdir -p /opt/gemini_relay
chown gemini:gemini /opt/gemini_relay

# Install Python dependencies
cd /opt/gemini_relay
python3 -m venv venv
./venv/bin/pip install websockets fastapi uvicorn httpx

# Create systemd service (see gemini_relay/systemd/)
# ... (full script in gemini_relay/scripts/setup_vps.sh)
```

**Management Commands**:

```bash
# List all instances
python3 scripts/cloud_infrastructure/vultr_provision.py --list

# Delete instance
python3 scripts/cloud_infrastructure/vultr_provision.py --delete INSTANCE_ID

# Dry run (test configuration)
python3 scripts/cloud_infrastructure/vultr_provision.py --dry-run
```

**SSH Connection**:

```bash
# After provisioning, connect via SSH
ssh root@<instance_ip>

# Your SSH key must be configured in Vultr account settings
# Settings → SSH Keys → Add SSH Key
```

**Security Considerations**:

1. **SSH Key**: Configure in Vultr dashboard before provisioning
2. **Firewall**: Configure UFW on Debian (allow only necessary ports)
3. **Fail2Ban**: Install to prevent brute-force attacks
4. **Auto-updates**: Enable unattended-upgrades for security patches

**Cost Monitoring**:

- Free tier is $0/month when within limits
- Backups disabled to avoid hidden charges
- Monitor usage in Vultr dashboard: Billing → Usage History
- Set up billing alerts to prevent unexpected charges

**Troubleshooting**:

| Issue | Solution |
|-------|----------|
| "Free tier plan not available" | Try different region (ams, fra, cdg) |
| "OS not available" | Debian 12 may be unavailable in some regions |
| Instance stuck in "pending" | Wait up to 5 minutes, check Vultr status page |
| SSH connection refused | Wait for OS to fully boot, check SSH key config |

**Related Documentation**:

- `scripts/cloud_infrastructure/vultr_provision.py` - Provisioning script
- `gemini_relay/scripts/setup_vps.sh` - Example cloud-init script
- [Vultr API Docs](https://www.vultr.com/api/)
- [Vultr Free Tier](https://www.vultr.com/products/free-tier/)

---

## Functionality

### Data Flow Systems

#### 1. Email Processing Pipeline
```
Proton Bridge (localhost:1143) 
    → email_backfill.py 
    → Qwen3.5-2b (Entity-Targeted Classification)
    → Direct HTTPS POST 
    → Notion Database (BiOS Triage)
```

#### 2. File Processing Pipeline
```
Google Drive API 
    → omni_sync.py (GDrive processor) 
    → Circuit Breaker (size/keyword filtering) 
    → [Full Content (< 10MB)] → Notion Processing
                                 ↓
                            [Metadata Only] → Notion Processing
                                 ↓
                            [Skip (blocked)] → Logging
```

#### 3. Event Processing Pipeline
```
GitHub Webhook 
    → Cloudflare Worker 
    → Notion Database (Biomimetic OS)
                    ↓
           GCP Memory System (contextual AI)
                    ↓
           Notion Updates ↔ CoPaw Approval System
```

#### 4. Memory System Pipeline
```
User Interaction
    → Zed/Antigravity
    → Cloudflare Worker (routing)
    → GCP Memory Gateway
    → MuninnDB + MemU Storage
                    ↓
           Contextual Insights → Task Suggestions
```

#### 5. Automated Dev Loop Pipeline
```
GitHub Issue Created
    ↓ (webhook)
Cloudflare Worker (Gemma 3 Project Manager)
    ↓ (technical documentation)
Notion "ARCA Tasks" Database
    ↓ (serena_notion_poller.py)
Super Nemotron 3 (The Architect)
    ↓ (implementation plan)
Minimax / GLM-5 (The Executor)
    ↓ (tool calls)
Oraios Serena MCP Server (Local Code Edits)
    ↓ (git commit)
Review → Complete
```

### Key Functional Capabilities

1. **Automated Sync**: Continuous synchronization across email, files, and data platforms
2. **Intelligent Filtering**: Circuit breakers prevent system overload from large files or spam
3. **Stateful Processing**: Tracks processed items to avoid duplicates using Message-ID and file hash tracking
4. **Modular Design**: Each system operates independently with clear interfaces
5. **Passive Collection**: Gathers data without user intervention
6. **Bi-directional Sync**: Changes in external systems propagate back to source systems where appropriate

---

## Optimization Potentials

### 1. Performance Optimizations
- **Circuit Breaker Tuning**: Adjust file size limits and keyword filters based on actual usage patterns
- **Batch Processing**: Implement batch email processing instead of individual item processing
- **Caching Layer**: Add Redis or similar caching for frequently accessed Notion data
- **Async Processing**: Convert synchronous operations to asynchronous where possible

### 2. Architecture Improvements
- **Microservice Decomposition**: Split omni_sync.py into specialized services
- **Event Streaming**: Implement Apache Kafka or similar for real-time event processing
- **Database Sharding**: Separate Notion databases by function for better query performance
- **Load Balancing**: Distribute Cloudflare Worker load across multiple instances

### 3. Security Enhancements
- **Zero Trust Architecture**: Implement stricter access controls between components
- **Audit Logging**: Comprehensive logging of all data accesses and modifications
- **Encryption at Rest**: Encrypt sensitive data in local storage and backups
- **Secrets Rotation**: Automate secret rotation for all integrated services

### 4. Monitoring & Observability
- **Distributed Tracing**: Implement OpenTelemetry for cross-service tracing
- **Metrics Collection**: Prometheus/Grafana integration for system metrics
- **Health Checks**: Automated health monitoring for all services
- **Alerting**: Proactive alerting for system anomalies

### 5. AI/ML Enhancements
- **Model Fine-tuning**: Fine-tune local LLMs on project-specific data
- **Embedding Optimization**: Improve semantic search with better embedding models
- **Predictive Analytics**: Use historical data to predict project timelines and risks
- **Auto-tagging**: Implement automatic categorization of incoming data

### 6. User Experience Improvements
- **Unified Dashboard**: Single pane view of all system statuses
- **Customizable Workflows**: User-definable automation rules
- **Mobile Companion**: iOS/Android app for on-the-go access
- **Voice Commands**: Enhanced voice control for system operations

---

## Remaining Tasks

### Immediate Priority (0-24 hours)
1. **GitHub MCP Redeployment**
   ```bash
   cd ~/biomemetics/azure
   ./deploy_github_mcp_with_keyvault.sh
   ```
   - Retrieve GitHub token from Azure Key Vault
   - Deploy GitHub MCP container in East US
   - Update configurations with new endpoint

2. **Zed Editor GitHub MCP Configuration**
   ```json
   {
     "mcp_servers": {
       "github": {
         "url": "http://<new-azure-ip>:8080/sse",
         "transport": "sse",
         "description": "GitHub MCP via Azure ACI"
       }
     }
   }
   ```

3. **Antigravity MCP Configuration**
   Create `~/.antigravity/settings.json` with Notion, GitHub, and GCP Gateway configuration

### Short-term Priority (1-7 days)
1. **ARCA Project Notion Database Creation**
   - Create ARCA Projects database with required properties
   - Create ARCA Tasks database with required properties
   - Create ARCA Memory database for project-specific context
   - Share databases with Notion integration

2. **ARCA Project Integration**
   - Configure ARCA-specific Zed settings
   - Configure ARCA-specific Antigravity settings
   - Update Cloudflare Worker for ARCA project routing
   - Configure ARCA-specific GCP memory namespace

3. **Documentation Updates**
   - Update `MCP_INTEGRATION.md` with complete configurations
   - Create integration test script
   - Update troubleshooting guides
   - Create architecture diagrams

### Long-term Priority (2-4 weeks)
1. **System Optimization**
   - Implement circuit breaker tuning based on usage analytics
   - Add caching layer for frequently accessed Notion data
   - Optimize email processing batch sizes
   - Implement async processing for I/O bound operations

2. **Enhanced Monitoring**
   - Deploy Prometheus/Grafana stack for metrics collection
   - Implement distributed tracing with OpenTelemetry
   - Add health check endpoints for all services
   - Create automated alerting for system anomalies

3. **AI Enhancements**
   - Fine-tune local LLMs on ARCA project documentation
   - Implement semantic search with improved embeddings
   - Add predictive analytics for project timeline estimation
   - Develop auto-tagging for incoming emails and files

4. **Security Hardening**
   - Implement zero trust architecture between components
   - Add comprehensive audit logging
   - Automate secrets rotation for all services
   - Encrypt sensitive data at rest

---

## Secrets Management

### Azure Key Vault (Primary Source of Truth) ✅

**Vault**: `arca-mcp-kv-dae`

**Status**: Fully populated via automated migration script (2026-03-23)

**Managed Secrets** (100+ secrets including):

| Category | Secret Name | Used By |
|----------|-------------|---------|
| **Google** | `google-api-key` | Google AI Studio, Gemini |
| | `google-ai-studio-key` | Gemini API |
| | `gcp-service-account-json` | Google Drive API |
| **Notion** | `notion-api-key` | Notion MCP, Cloudflare Worker |
| | `notion-bios-agent-api-key` | BiOS Notion integration |
| **OpenAI** | `openai-api-key` | OpenAI API |
| **GitHub** | `github-models-token` | GitHub Models (Azure) |
| | `github-webhook-secret` | GitHub webhooks |
| **Anthropic** | `anthropic-api-key` | Claude API |
| **Cloudflare** | `cloudflare-api-key` | Cloudflare Workers |
| | `cloudflare-client-id` | Cloudflare OAuth |
| | `cloudflare-service-token` | Cloudflare Tunnel |
| **AWS** | `aws-access-key-id` | AWS services |
| | `aws-secret-access-key` | AWS authentication |
| **AI Services** | `groq-api-key` | Groq inference |
| | `cohere-api-key` | Cohere models |
| | `huggingface-token` | Hugging Face |
| | `minimax-api-key` | MiniMax models |
| | `opencode-api-key` | Opencode Zen |
| | `openrouter-api-key` | OpenRouter |
| | `gemini-api-key` | Gemini Live API |
| **Infrastructure** | `tailscale-auth-key` | Tailscale VPN |
| | `qdrant-api-key` | Qdrant vector DB |
| | `oci-config` | Oracle Cloud |
| **Monitoring** | `grafana-api-key` | Grafana |
| | `langfuse-credentials` | Langfuse observability |
| | `wandb-api-key` | Weights & Biases |
| **Email** | `proton-bridge-password` | ProtonMail Bridge |
| | `telegram-bot-token` | Telegram bot |
| | `whatsapp-verify-token` | WhatsApp Business API |

### Secret Migration Automation

**Script**: `scripts/secret_manager/azure_secret_migrator.py`

**Purpose**: Automates the transfer of local secrets from `/Users/danexall/biomimetics/secrets/` to Azure Key Vault, ensuring Azure is the fully populated single source of truth.

**Usage**:
```bash
# Dry run (preview what would be migrated)
python3 scripts/secret_manager/azure_secret_migrator.py --dry-run

# Migrate all secrets
python3 scripts/secret_manager/azure_secret_migrator.py

# Force overwrite existing secrets
python3 scripts/secret_manager/azure_secret_migrator.py --force
```

**Features**:
- ✅ Automatic secret name mapping (local filename → Azure Key Vault name)
- ✅ Skip detection (avoids re-migrating existing secrets)
- ✅ SHA256 hash verification for integrity
- ✅ Dry-run mode for preview
- ✅ Detailed migration report
- ✅ Skips binary files, archives, and large files (>1MB)
- ✅ Uses Azure CLI for secure secret upload

**Requirements**:
- Azure CLI installed and authenticated (`az login`)
- Access to `arca-mcp-kv-dae` Key Vault
- Read access to local secrets directory

**Migration Process**:
1. Script scans local secrets directory (140+ files)
2. Maps local filenames to Azure Key Vault secret names
3. Checks if secret already exists in vault
4. Uploads new/updated secrets with metadata
5. Generates detailed migration report

**Post-Migration**:
After migration, all systems should reference Azure Key Vault as the primary source:
- Credentials Server fetches from Azure KV
- CoPaw secrets wrapper uses Credentials Server
- Cloudflare Worker uses wrangler secrets
- Local configs are generated from Azure KV via `azure_secrets_init.py`

### Headless Credentials Server (Port 8089)
The system utilizes a central `credentials_server.py` daemon running as a macOS LaunchAgent.

- **Primary Source**: Azure Key Vault (`arca-mcp-kv-dae`).
- **Auth Mode**: Headless Service Principal (Client ID/Secret from local `.env`).
- **Policy**: **Single Source of Truth**. Stale local files are ignored. If Vault is unreachable, the server returns 503 instead of falling back to insecure files.
- **Client Protocol**:
    1. Scripts read `credentials_api_key` from `/Users/danexall/biomimetics/secrets/credentials_api_key` (mode 600).
    2. Authentication with `http://localhost:8089` provides operational keys directly to memory.

### Local Storage (Secondary/Cache)

**Directory**: `/Users/danexall/biomimetics/secrets/`

**Purpose**: Legacy storage, kept for backup and reference. All secrets should be migrated to Azure Key Vault.

**Contents**:
- Historical secret files (pre-migration)
- Binary certificates and keys (`.pem`, `.key`, `.pub`)
- Configuration JSON files
- Backup archives

**Note**: After migration, local files are considered **read-only cache**. Always update Azure Key Vault first, then propagate to local configs.

### GCP Secrets (Tertiary)

**Used For**:
- Service account authentication
- Cloud Function invocation credentials
- Memory gateway access tokens

**Storage**: GCP Secret Manager (for GCP-native services)


---

## Core Identity & Memory Architecture (CRITICAL)

**This section defines the non-negotiable architectural requirements for CoPaw operation.**

### 1. LLM Engine: Gemini / Gemma Stack

**Standard LLM**: `gemini-flash-lite-latest` (via Google AI Studio)
**Refinement LLM (Archive)**: `gemma-3-12b-it` (running on MemU Cloud Run)

**API Key Configuration**:
```python
# MUST use dynamic secret fetching - NO hardcoded keys
from copaw_secrets_wrapper import fetch_secret

GEMINI_API_KEY = fetch_secret('google_api_key')

# Set environment variable for Gemini SDK
import os
os.environ['GEMINI_API_KEY'] = GEMINI_API_KEY
```

**Invariant**: All API keys MUST be fetched dynamically via the `credentials_server.py`. Hardcoded keys are strictly forbidden.

### 2. Memory Orchestration Pipeline

The system uses a tiered memory architecture managed by a central **Memory Orchestrator** gateway.


### 3. Core Tool Nodes (Mandatory Access)

CoPaw MUST ALWAYS have access to these three core tool nodes:

| Node | Provider | Purpose | Configuration |
|------|----------|---------|---------------|
| **Serena** | Local MCP | Code editing, local OS operations | `~/.copaw/bin/serena-mcp-server.py` |
| **Email** | Local MCP (Proton Bridge) | Email reading/sending via ProtonMail + Gmail | `~/biomimetics/scripts/copaw/mcp_email_server.py` |
| **MemU/MuninnDB** | GCP Cloud Function | Contextual memory retrieval | GCP Memory Orchestrator endpoint |

**Invariant**: Removal of any core tool node requires explicit approval. These nodes are essential for CoPaw's operational capability.

### 4. Secret Fetching Invariants

| Secret | Canonical Name | Source | Env Var |
|--------|---------------|--------|---------|
| Gemini API Key | `google_api_key` | Credentials Server | `GEMINI_API_KEY` |
| GCP Service Account | `gcp-service-account` | Local file | N/A |
| Proton Bridge Password | `proton-bridge-password` | Credentials Server | N/A |
| Notion API Key | `notion-api-key` | Credentials Server | `NOTION_TOKEN` |

**Fetching Pattern**:
```python
# ALWAYS use the secrets wrapper - never read files directly
from copaw_secrets_wrapper import fetch_secret

# Correct:
api_key = fetch_secret('google_api_key')

# INCORRECT (forbidden):
# with open('~/.copaw/.secrets/google_api_key') as f: ...
# api_key = os.environ.get('HARDCODED_KEY')
```

### 5. Failure Modes & Fallbacks

| Component | Primary | Fallback | Failure Action |
|-----------|---------|----------|----------------|
| LLM | Gemini Flash (Google) | Local Qwen3.5-2b | Degrade to local inference |
| Memory | GCP MemU | Local cache | Use cached context only |
| Email | Proton Bridge | Gmail IMAP | Continue with available accounts |
| Secrets | Credentials Server | Local files | Use cached secrets |


**Strict Invariants**:
```python
GCP_SERVICE_ACCOUNT_PATH = "/Users/danexall/biomimetics/secrets/gcp-service-agent.json"
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
TARGET_VAULT_NAME = "Obsidian-life"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
```

**Usage**:
```bash
# Dry-run (discover files, don't send)
python3 scripts/memory/gdrive_obsidian_ingest.py

# Live ingestion (send to MuninnDB)
python3 scripts/memory/gdrive_obsidian_ingest.py --live
```

**Target Folders** (auto-detected namespaces):
- Medical, Personal, Disability, Health → disability_context, medical_context
- Complaints, Legal, Evidence_Pack → legal_context
- Living, People, Projects, Resources → personal_context

### 7. Mixture-of-Experts (MoE) Provider Registry

**Purpose**: Dynamic model selection across multiple AI providers with automatic fallback.

**Configuration File**: `/Users/danexall/biomimetics/config_copaw/providers.json`

**Registered Providers**:
| Provider | Base URL | Auth Type | Secret Name | Models |
|----------|----------|-----------|-------------|--------|
| **google_ai_studio** | generativelanguage.googleapis.com/v1beta | api_key | `google_api_key` | gemini_flash_lite_latest, gemma-3-12b |
| **opencode_go** | api.opencode.go/v1 | api_key | `opencode_go_api` | minimax_m2.5_free, minimax_2.7, super_nemotron_3_free, kimi_k2.5_thinking, glm-5-opencode |
| **alibaba_studio** | dashscope.aliyuncs.com/compatible-mode/v1 | oauth_bearer | `qwen_oauth_token` | qwen-max, qwen-coder |
| **zhipu_native** | open.bigmodel.cn/api/paas/v4 | api_key | `zhipu_api_key` | glm-5, glm-5-turbo |

**Model Specializations**:
| Task Type | Recommended Models |
|-----------|-------------------|
| Code Generation | minimax_m2.5_free, qwen-coder |
| Deep Planning | super_nemotron_3_free (The Architect) |
| Reasoning | kimi_k2.5_thinking, qwen-max |
| High Volume | gemini_flash_lite_latest |
| Vision | gemini_flash_lite_latest, qwen-max |

**Fallback Chain**:
```
google_ai_studio → opencode_go → alibaba_studio → zhipu_native
```

### 8. Gemma-3 Dynamic Model Router

**Purpose**: Self-evaluating AI dispatcher that analyzes tasks and selects optimal executor models.

**Location**: `scripts/serena/serena_notion_poller.py`

**Architecture**:
```
┌─────────────────────────────────────────────────────────────────────────┐
│  GEMMA-3 DISPATCHER FLOW                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Task from Notion ("Ready for Dev")                                  │
│       ↓                                                                 │
│  2. Gemma-3-12b Router (Google AI Studio)                               │
│     Prompt: "Analyze task, return best model name from list"            │
│       ↓                                                                 │
│  3. Selected Model → os.environ["EXECUTOR_MODEL_PRIMARY"]               │
│       ↓                                                                 │
│  4. Nemotron Architect receives pre-selected executor                   │
│       ↓                                                                 │
│  5. Executor generates code with optimal model                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Router Prompt**:
```
You are the ARCA Model Dispatcher. Analyze this task and return ONLY the 
string name of the best model to use from this list:

- minimax_2.7 (For adventurous architecture/refactoring)
- super_nemotron_3_free (For deep investigation/troubleshooting)
- kimi_k2.5_thinking (For complex reasoning/logic mapping)
- qwen-coder (For standard, fast code generation)
- glm-5 (For native Zhipu free-tier general tasks)

Task Title: {title}
Task Description: {description}
Priority: {priority}
Complexity: {complexity}

Return ONLY the model name, nothing else.
```

**Configuration**:
```python
# Gemma-3 Router Configuration (Dynamic Model Selection)
GEMMA_ROUTER_ENABLED = os.getenv("GEMMA_ROUTER_ENABLED", "true").lower() == "true"
GEMMA_MODEL = "gemma-3-12b"
GEMMA_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMMA_API_KEY = fetch_secret_from_credentials_server("google_api_key")
```

**Usage**:
```bash
# Enable/disable router via environment
export GEMMA_ROUTER_ENABLED=true  # Default: enabled
export GEMMA_ROUTER_ENABLED=false # Use default executor
```

### 9. Serena MCP Servers (Workspace Segregation)

**Purpose**: Semantic code analysis with separate MCP instances per workspace.

**Configuration**: `/Users/danexall/biomimetics/config_copaw/config.json`

**Dual MCP Server Setup**:
```json
{
  "mcp": {
    "clients": {
      "serena_arca": {
        "name": "serena_arca_mcp",
        "description": "Serena MCP server for ARCA project",
        "command": "uvx",
        "args": [
          "--from", "git+https://github.com/oraios/serena",
          "serena", "start-mcp-server",
          "/Users/danexall/Documents/VS Code Projects/ARCA"
        ],
        "cwd": "/Users/danexall/Documents/VS Code Projects/ARCA"
      },
      "serena_bios": {
        "name": "serena_bios_mcp",
        "description": "Serena MCP server for BiOS project",
        "command": "uvx",
        "args": [
          "--from", "git+https://github.com/oraios/serena",
          "serena", "start-mcp-server",
          "/Users/danexall/biomimetics"
        ],
        "cwd": "/Users/danexall/biomimetics"
      }
    }
  }
}
```

**Why Segregation?**:
- ✅ Prevents "unexpected extra argument" crashes
- ✅ Each workspace gets dedicated LSP context
- ✅ Independent indexing and caching
- ✅ No cross-project symbol confusion

**Workspaces**:
| Server | Target Directory | Purpose |
|--------|-----------------|---------|
| `serena_arca` | `/Users/danexall/Documents/VS Code Projects/ARCA` | ARCA codebase |
| `serena_bios` | `/Users/danexall/biomimetics` | BiOS infrastructure |

**Installation**:
```bash
# Serena is installed via uvx (no manual install needed)
# CoPaw auto-starts both MCP servers on launch
```

---

**Payload Structure**:
```json
{
  "action": "store",
  "namespace": "medical",
  "source": "gdrive_vault",
  "vault_name": "Obsidian-life",
  "content": {
    "title": "Health.md",
    "path": "Personal/Health.md",
    "content": "...",
    "headers": [{"level": 1, "title": "Health"}],
    "word_count": 57,
    "content_hash": "eb7cc72add5876c2"
  },
  "metadata": {
    "modified": "2026-03-27T...",
    "created": "2026-03-27T...",
    "frontmatter": ""
  },
  "context": {
    "active": true
  }
}
```

---


---
    "disability_context": true,
    "medical_context": true,
    "personal_context": false
  }
}
```

**Authentication Flow**:
1. **Drive API**: Service account credentials from `gcp-service-agent.json`
2. **Cloud Function**: OIDC token generated from same service account
3. **No local storage**: Content streamed directly from Drive to Cloud Function

**Benefits**:
- ✅ No local NAS mount required
- ✅ Real-time sync from any device with Drive access
- ✅ Single service account for both auth flows
- ✅ Automatic namespace detection from folder structure

---

### Secret Rotation Process

1. **Update in Azure Key Vault**:
   ```bash
   az keyvault secret set --vault-name arca-mcp-kv-dae --name <secret-name> --value <new-value>
   ```

2. **Run propagation script**:
   ```bash
   python3 scripts/secret_manager/azure_secrets_init.py --refresh
   ```

3. **System automatically propagates to**:
   - Local config files (`config/omni_sync_config.json`)
   - Cloudflare Worker secrets (via `wrangler secret put`)
   - Notion MCP server configuration
   - Credentials Server cache (5-min TTL)
   - All dependent services

### Credentials Server Integration

**Service**: `com.bios.credentials-server` (port 8089)

All applications should fetch secrets from the Credentials Server, which acts as a local gateway to Azure Key Vault:

```python
# Example: Fetch secret from Credentials Server
import httpx

response = httpx.get(
    "http://127.0.0.1:8089/secrets/google-api-key",
    headers={"X-API-Key": os.getenv("CREDENTIALS_API_KEY")}
)
api_key = response.json()["value"]
```

**Benefits**:
- Single point of access for all secrets
- Centralized audit logging
- Automatic Azure AD token refresh
- 5-minute local caching for performance
- API key authentication for local services

---

## Configuration Reference

### Main Configuration Files

#### 1. Omni Sync Configuration
**Location**: `config/omni_sync_config.json`
```json
{
  "IDENTITY": {
    "PRIMARY_EMAIL": "claws@arca-vsa.tech",
    "IDENTITY_NAME": "Claws"
  },
  "NOTION_API_KEY": "ntn_xxx",
  "NOTION_PAGE_ID": "3244d2d9fc7c808b97c3ce78648d77a1",
  "PROTONMAIL_ACCOUNTS": [
    {"email": "dan.exall@pm.me", "password": "..."},
    {"email": "dan@arca-vsa.tech", "password": "..."},
    {"email": "claws@pm.me", "password": "..."},
    {"email": "arca@pm.me", "password": "..."},
    {"email": "info@pm.me", "password": "..."}
  ],
  "GMAIL_USER": "dan.exall@gmail.com",
  "GMAIL_APP_PASSWORD": "...",
  "GOOGLE_SERVICE_ACCOUNT_PATH": "/path/to/gcp_credentials.json",
  "GCP_GATEWAY_URL": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
}
```

#### 2. Cloudflare Worker Configuration
**Location**: `cloudflare/wrangler.toml`
```toml
name = "arca-github-notion-sync"
main = "src/index.js"
compatibility_date = "2026-03-01"

[vars]
NOTION_PAGE_ID = "3224d2d9fc7c80deb18dd94e22e5bb21"
GCP_GATEWAY = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"

[vars]
# ARCA Project vars (to be added)
ARCA_PROJECTS_DB_ID = "your-arca-projects-db-id"
ARCA_TASKS_DB_ID = "your-arca-tasks-db-id"
```

#### 3. Zed Editor Configuration
**Location**: `~/.zed/settings.json`
```json
{
  "mcp_servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "[NOTION_TOKEN_REDACTED]"
      }
    }
    // GitHub MCP to be added
  },
  "agent_servers": {
    "BiOS_PM": {
      "type": "custom",
      "command": "python3",
      "args": ["~/.copaw/bios_orchestrator.py"],
      "env": {
        "NOTION_DB_ID": "3224d2d9fc7c80deb18dd94e22e5bb21",
        "GCP_GATEWAY": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
      }
    }
  }
}
```

#### 4. CoPaw Configuration
**Location**: `~/.copaw/config.json`

**MCP Servers**:
```json
{
  "mcp_servers": {
    "email": {
      "command": "python3",
      "args": ["/Users/danexall/biomimetics/scripts/copaw/mcp_email_server.py"],
      "env": {}
    },
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "[NOTION_TOKEN_REDACTED]"
      }
    }
  }
}
```

**Secrets Wrapper** (Dynamic Pass-Through):
**Location**: `~/.copaw/bin/copaw-secrets-wrapper.py`

The CoPaw secrets wrapper has been converted to a **dynamic, unbound pass-through** to the ARCA Credentials Server:

```python
def fetch_secret(secret_name: str) -> Optional[str]:
    """
    Fetch a secret dynamically from Credentials Server.
    No hardcoded allowlists - any secret name can be requested.
    
    Fallback: Check local secrets directory if server is unavailable.
    Handles both hyphen and underscore naming conventions.
    """
    # 1. Get the Master Key from secure file
    master_key_path = "/Users/danexall/biomimetics/secrets/credentials_api_key"
    with open(master_key_path, 'r') as f:
        master_key = f.read().strip()

    # 2. Query the Credentials Server Dynamically
    url = f"http://localhost:8089/secrets/{secret_name}"
    req = urllib.request.Request(url)
    req.add_header("X-API-Key", master_key)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get("value")
    except Exception:
        # Fallback: Check local directory directly
        alt_name = secret_name.replace('-', '_')
        for name in [secret_name, alt_name]:
            local_path = f"/Users/danexall/biomimetics/secrets/{name}"
            if os.path.exists(local_path):
                with open(local_path, 'r') as f:
                    return f.read().strip()
        return None
```

**Key Features**:
- ✅ **No hardcoded secret lists** - Any secret can be requested dynamically
- ✅ **Zero dependencies** - Uses `urllib.request` (stdlib only)
- ✅ **Master key authentication** - Reads from `/Users/danexall/biomimetics/secrets/credentials_api_key`
- ✅ **Fallback to local files** - Checks `/Users/danexall/biomimetics/secrets/` if server unavailable
- ✅ **Naming convention handling** - Automatically tries both `hyphen` and `underscore` variants

**Test**:
```bash
python3 -c "
from importlib.machinery import SourceFileLoader
wrapper = SourceFileLoader('wrapper', '~/.copaw/bin/copaw-secrets-wrapper.py').load_module()
print('Proton Bridge:', wrapper.fetch_secret('proton-bridge-password') is not None)
"
# Output: Proton Bridge: True
```

**Available Secrets** (via Credentials Server):
- `proton-bridge-password` - Proton Mail Bridge authentication
- `gmail-app-password` - Gmail IMAP/SMTP authentication
- `notion-api-key` - Notion API integration
- `green-api-id` / `green-api-token` - WhatsApp integration
- All Azure Key Vault secrets (see Secrets Management section)

#### 5. Notion MCP Server Configuration
**Location**: Generated by `scripts/setup_notion_mcp.sh`
```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "[NOTION_TOKEN_REDACTED]"
      }
    }
  }
}
```

### Environment Variables
- `NOTION_TOKEN`: Notion API integration token
- `GITHUB_TOKEN`: GitHub API token for MCP server
- `GCP_SERVICE_ACCOUNT`: Base64-encoded Google service account JSON
- `GCP_GATEWAY_URL`: URL for GCP memory orchestrator function
- `PROTON_BRIDGE_PASSWORD`: Password for Proton Mail Bridge
- `MYCLOUD_PASSWORD`: Password for NAS SMB mount

---

## System Dependencies

### Required Services
1. **Azure Subscription**: For Key Vault and Container Instances
2. **Google Cloud Account**: For Cloud Functions and Drive API
3. **Proton Mail Bridge**: Running locally on port 1143
4. **Notion Account**: With API integration enabled
5. **GitHub Account**: For webhook integration
6. **Local NAS**: MyCloud Home or equivalent SMB storage
7. **Ollama**: Running locally for LLM inference
8. **Node.js**: For Cloudflare Worker development
9. **Python 3.12+**: For synchronization scripts
10. **Azure CLI**: For secret management

### Software Dependencies
#### Python (requirements.txt)
```
google-api-python-client
google-auth-httplib2
requests
```

#### Node.js (cloudflare/package.json)
```
(minimal - wrangler handles dependencies)
```

#### System Services
- LaunchAgents (macOS) for process automation
- Ollama service for local LLM
- Proton Mail Bridge for email access
- SMB mounting for NAS access

---

## Troubleshooting Guide

### Common Issues and Solutions

#### 1. GitHub MCP Connection Fails
**Symptoms**: Unable to access GitHub resources through MCP
**Solutions**:
```bash
# Test SSE endpoint
curl -v http://github-mcp-sse.westus2.azurecontainer.io:8080/sse

# Check Azure container status
az container show -g arca-mcp-services -n github-mcp-sse

# View logs
az container logs -g arca-mcp-services -n github-mcp-sse

# Restart if needed
az container restart -g arca-mcp-services -n github-mcp-sse
```

#### 2. Notion MCP Not Working
**Symptoms**: Notion operations failing through MCP
**Solutions**:
```bash
# Test Notion token
npx -y @notionhq/notion-mcp-server

# Check database access in Notion UI
# Open Notion → Database → ... → Connect to → Select integration

# Verify token in Azure secrets
az keyvault secret show --vault-name arca-mcp-kv-dae --name notion-api-key
```

#### 3. GCP Gateway Unreachable
**Symptoms**: Memory operations failing
**Solutions**:
```bash
# Test endpoint
curl -X POST https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator \
  -H "Content-Type: application/json" \
  -d '{"action": "ping"}'

# Check GCP credentials
cat ~/.gcp/google_drive_credentials.json | jq .

# Verify GCP Gateway URL in config
grep GCP_GATEWAY cloudflare/wrangler.toml
```

#### 4. Email Sync Issues
**Symptoms**: ProtonMail or Gmail sync failing
**Solutions**:
```bash
# Check Proton Bridge
nc -zv 127.0.0.1 1143

# Check email sync logs
tail -f ~/.arca/proton_sync.log
tail -f ~/.arca/omni_sync.log

# Verify credentials in config
cat config/omni_sync_config.json | grep -A5 -B5 "PROTONMAIL_ACCOUNTS\|GMAIL_USER"
```

#### 5. File Processing Problems
**Symptoms**: Google Drive files not processing
**Solutions**:
```bash
# Check Drive API quota
# Verify service account has Drive API enabled
# Re-authenticate if needed: gcloud auth application-default login

# Check omni_sync logs
tail -f ~/.arca/omni_sync.log

# Verify circuit breaker settings
cat scripts/omni_sync.py | grep -A3 -B3 "MAX_FILE_SIZE\|IGNORE_KEYWORDS"
```

---

## Glossary

- **MCP**: Model Context Protocol - Standardized interface for AI models to access external tools and data
- **SSE**: Server-Sent Events - Technology used for GitHub MCP real-time communication
- **ACI**: Azure Container Instances - Where GitHub MCP is deployed
- **BiOS**: Biomimetic Operating System - The overarching system architecture
- **ARCA**: Advanced Research and Computational Architecture - The project ecosystem
- **CoPaw**: Collaborative Permissioning and Workflow system - AI agent approval workflow
- **MuninnDB**: Memory database system for long-term storage
- **MemU**: Memory unit system for contextual AI
- **Omni Sync**: Main synchronization heartbeat process
- **Backfill Claws**: ProtonMail email synchronization process
- **MyCloud Watchdog**: NAS connection maintenance process

---

## Conclusion

The Biomimetics project represents a sophisticated infrastructure automation system that integrates multiple services and platforms to create an intelligent development ecosystem for ARCA. While many components are already functional and integrated, there are clear opportunities for optimization, enhancement, and completion of pending integrations.

The immediate focus should be on completing the GitHub MCP deployment and integration, followed by establishing the ARCA project-specific configurations across all systems. Once these foundations are in place, the system can be optimized for performance, security, and enhanced AI capabilities.

Regular maintenance, monitoring, and iterative improvements will ensure the system continues to meet the evolving needs of the ARCA development ecosystem.