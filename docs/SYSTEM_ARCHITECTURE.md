---
tags: [bios/architecture, bios/infrastructure, bios/memory, bios/security, bios/swarm, source/legacy]
status: active
---

# Biomimetics System Architecture

> **Biomimetics** is the project management and optimization layer that brings structure, automation, and intelligence to the ARCA development ecosystem and related projects.

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Component Details](#component-details)
4. [Data Flow](#data-flow)
5. [Configuration Reference](#configuration-reference)
6. [Deployment Guide](#deployment-guide)
7. [Troubleshooting](#troubleshooting)

---

## Overview

### Purpose

Biomimetics provides:
- **Automated Sync**: Email, files, and data synchronization across platforms
- **Project Tracking**: Notion-based task and issue management
- **Event Processing**: Real-time webhook handling via Cloudflare Workers (GitHub, Serena agents, GCP memory, CoPaw)
- **System Monitoring**: LaunchAgents for continuous operation
- **AI Integration**: Local model inference for summarization and analysis
- **Intelligent Memory**: GCP Cloud Function integration for contextual AI
- **Approval Workflows**: CoPaw tool guard for safe AI agent operations

### Core Principles

1. **Passive Collection**: Gather data without user intervention
2. **Intelligent Filtering**: Circuit breakers prevent overload
3. **Stateful Processing**: Track processed items to avoid duplicates
4. **Modular Design**: Each component operates independently

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         BIOMIMETICS ECOSYSTEM                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │  ProtonMail │     │   Gmail     │     │Google Drive │               │
│  │  (5 accts)  │     │   IMAP      │     │   API       │               │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘               │
│         │                   │                   │                       │
│         ▼                   ▼                   ▼                       │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │              omni_sync.py (Heartbeat)                   │           │
│  │         ┌──────────┬──────────┬──────────┐             │           │
│  │         │  Email   │   File   │  Notion  │             │           │
│  │         │  Sync    │  Process │  Create  │             │           │
│  │         └──────────┴──────────┴──────────┘             │           │
│  └────────────────────────┬────────────────────────────────┘           │
│                           │                                             │
│                           ▼                                             │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │              GCP Gateway (Cloud Functions)              │           │
│  │         memory-orchestrator endpoint                    │           │
│  └────────────────────────┬────────────────────────────────┘           │
│                           │                                             │
│         ┌─────────────────┼─────────────────┐                          │
│         │                 │                 │                          │
│         ▼                 ▼                 ▼                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │
│  │   Notion    │  │   Local     │  │   Cloud     │                    │
│  │  Databases  │  │   Storage   │  │   Storage   │                    │
│  └─────────────┘  └─────────────┘  └─────────────┘                    │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                         LAUNCH AGENTS (macOS)                           │
│  ┌─────────────┐ ┌─────────────────┐ ┌─────────────────┐           │
│  │  omni-sync      │ │  proton-sync    │ │  mycloud-       │           │
│  │  (continuous)   │ │  (hourly)       │ │  watchdog (60s) │           │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘           │
├─────────────────────────────────────────────────────────────────────────┤
│                         EXTERNAL INTEGRATIONS                           │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │  Cloudflare │     │   GitHub    │     │   Ollama    │               │
│  │   Workers   │◄────│   Webhooks  │     │   (Local)   │               │
│  │                 │     │           │◄────┤  GCP Memo   │               │
│  │                 │     │           │     │  ry       │               │
│  │                 │     │           │◄────┤  CoPaw    │               │
│  │                 │     │           │     │  Tool     │               │
│  │                 │     │           │     │  Guard    │               │
│  └─────────────┘     └─────────────┘     └─────────────┘               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 0. Azure Secrets-Init (`azure/azure_secrets_init.py`)

**Purpose**: Centralized secret management via Azure Key Vault

**Features**:
- Fetches secrets from Azure Key Vault
- Injects into `omni_sync_config.json`
- Updates Cloudflare Worker secrets via `wrangler`
- Configures Notion MCP Server for Claude Desktop
- Creates local encrypted backup

**Secrets Managed**:
| Secret Name | Used By |
|-------------|---------|
| `notion-api-key` | Notion API, Cloudflare Worker, MCP Server |
| `gmail-app-password` | Gmail IMAP sync |
| `proton-bridge-password` | ProtonMail 5-account sync |
| `gcp-service-account` | Google Drive API |
| `mycloud-password` | SMB NAS mount |
| `gcp-gateway-url` | GCP Cloud Functions endpoint |

**Usage**:
```bash
# Authenticate with Azure
az login

# Initialize all secrets
python3 azure/azure_secrets_init.py --refresh

# Specify custom vault
python3 azure/azure_secrets_init.py --vault my-custom-vault
```

---

### 1. Omni Sync (`scripts/omni_sync.py`)

**Purpose**: Main synchronization heartbeat

**Features**:
- Google Drive file watching with circuit breakers
- Gmail IMAP integration
- Notion database creation
- Local file processing

**Circuit Breakers**:
```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit
IGNORE_KEYWORDS = ['z-lib', 'libgen', 'epub', 'pdf', 'torrent', 'crack', 'warez']
MAX_CONTENT_LENGTH = 100000  # Max chars to extract
```

**Configuration**: `config/omni_sync_config.json`

---

### 2. ProtonMail Sync (`scripts/backfill_claws.py`)

**Purpose**: Fetch and process emails from 5 Proton accounts

**Accounts**:
| Email | Purpose |
|-------|---------|
| dan.exall@pm.me | Primary personal |
| dan@arca-vsa.tech | ARCA business |
| claws@arca-vsa.tech | AI identity |
| arca@pm.me | ARCA projects |
| info@pm.me | General info |

**Process**:
1. Connect via Proton Bridge (localhost:1143)
2. Fetch last 100 emails per account
3. Filter by date (90-day window)
4. Skip already-processed (Message-ID tracking)
5. Summarize with Ollama (deepseek-r1-1.5b)
6. Send to GCP Gateway

**State File**: `~/.arca/proton_sync_state.json`

---

### 3. MyCloud Watchdog (`scripts/maintain_mycloud_mount.sh`)

**Purpose**: Maintain persistent SMB connection to MyCloud Home NAS

**Logic**:
```bash
if /Volumes/danexall not mounted:
    mount_smbfs //danexall:password@192.168.0.103/danexall
else:
    touch /Volumes/danexall/.keepalive  # Force network activity
```

**Target**: 192.168.0.103 (MyCloud Home)

---

### 4. Cloudflare Worker (`cloudflare/index.js`)

**Purpose**: Multi-system integration hub for GitHub webhooks, Serena agents, GCP memory, and CoPaw integration

**Triggers**:
- GitHub Webhooks (Issues, PRs, Pushes) → Biomimetic OS database
- Serena Agent Tasks → Life OS Triage & Biomimetic OS databases  
- GCP Memory Insights → Biomimetic OS (task suggestions, context updates)
- CoPaw Requests → Tool approval workflow, skill queuing

**Flow**:
```
GitHub Event → Cloudflare Worker → Notion Database
      │                                    │
      ├→ GCP Memory System (contextual AI) │
      │                                    ▼
      └→ CoPaw Approval System            ◄── Notion Updates
```

**Enhanced Capabilities**:
- **GitHub → Notion**: Issues, PRs, pushes tracked in Biomimetic OS
- **Serena → Notion**: Agent tasks create/update Notion entries
- **Notion → GCP Memory**: Updates forwarded for contextual AI enrichment  
- **GCP Memory → Biomimetic OS**: Insights generate task suggestions/context updates
- **CoPaw Integration**: Tool approval workflow and skill execution queuing

**Deployment**:
```bash
cd ~/biomimetics/cloudflare
npx wrangler deploy
```

**Worker URL**: `https://arca-github-notion-sync.dan-exall.workers.dev`

**Secrets Managed via Azure Key Vault**:
- NOTION_API_KEY / NOTION_TOKEN: Notion integration
- GITHUB_WEBHOOK_SECRET: Webhook validation  
- GCP_SERVICE_ACCOUNT: GCP memory gateway auth
- COPAW_APPROVAL_DB_ID: CoPaw approvals database ID

---

### 4b. Notion MCP Server (`scripts/setup_notion_mcp.sh`)

**Purpose**: Model Context Protocol integration for direct Notion access

**Configuration**:
```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "ntn_..."
      }
    }
  }
}
```

**Integration Points**:
- Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)
- Qwen Code (`~/.qwen/settings.json`)

**Setup**:
```bash
# Run setup script (pulls token from Azure secrets)
./scripts/setup_notion_mcp.sh

# Or manually configure MCP client with above JSON
```

**Capabilities**:
- Read/write Notion pages and databases
- Create and update database entries
- Search and query Notion content
- Bi-directional sync with ARCA project tracking

---

### 5. LaunchAgents

| Agent | Interval | Purpose |
|-------|----------|---------|
| `com.arca.omni-sync.plist` | Continuous | Main sync heartbeat |
| `com.arca.proton-sync.plist` | 3600s (1hr) | Email sync |
| `com.arca.mycloud-watchdog.plist` | 60s | NAS mount keepalive |

**Location**: `~/Library/LaunchAgents/` (active), `launch_agents/` (backup)

---

## Data Flow

### Email Processing Pipeline

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Proton Bridge│     │ backfill_    │     │   Ollama     │
│ localhost:   │────►│ claws.py     │────►│  (local)     │
│    1143      │     │              │     │              │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   GCP        │
                     │   Gateway    │
                     └──────┬───────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   Notion     │
                     │   Database   │
                     └──────────────┘
```

### File Processing Pipeline

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Google Drive │     │ omni_sync.py │     │  Circuit     │
│   API        │────►│  (GDrive)    │────►│  Breaker     │
└──────────────┘     └──────┬───────┘     └──────┬───────┘
                            │                   │
                    ┌───────┴───────┐           │
                    │               │           │
                    ▼               ▼           ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │ Full Content│ │ Metadata    │ │  Skip       │
            │ (< 10MB)    │ │ Only        │ │ (blocked)   │
            └─────────────┘ └─────────────┘ └─────────────┘
```

---

## Configuration Reference

### omni_sync_config.json

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

### Environment Secrets

| Secret | Storage |
|--------|---------|
| Notion API Key | Cloudflare Worker Secret |
| Gmail App Password | config/omni_sync_config.json |
| Proton Bridge Passwords | config/omni_sync_config.json |
| GCP Service Account | ~/.secrets/gcp_credentials.json |

---

## Deployment Guide

### Initial Setup

```bash
# 1. Clone repository
git clone https://github.com/danxalot/biomimetics.git ~/biomimetics
cd ~/biomimetics

# 2. Configure secrets
cp config/omni_sync_config.json.example config/omni_sync_config.json
# Edit with your credentials

# 3. Install dependencies (for omni_sync.py)
pip3 install google-api-python-client google-auth-httplib2 requests

# 4. Load LaunchAgents
for plist in launch_agents/*.plist; do
    launchctl load "$HOME/Library/LaunchAgents/$(basename $plist)"
done

# 5. Deploy Cloudflare Worker
cd cloudflare
npx wrangler deploy
```

### Verify Services

```bash
# Check LaunchAgents
launchctl list | grep com.arca

# View logs
tail -f ~/.arca/omni_sync.log
tail -f ~/.arca/proton_sync.log
tail -f ~/.arca/mycloud_watchdog.log

# Test Proton Bridge connection
nc -zv 127.0.0.1 1143

# Test Ollama
curl http://localhost:11434/api/tags
```

---

## Troubleshooting

### Proton Bridge SSL Error

**Symptom**: `[SSL: WRONG_VERSION_NUMBER] wrong version number`

**Cause**: Proton Mail Bridge not running

**Fix**:
1. Open Proton Mail Bridge application
2. Ensure all 5 accounts are configured
3. Verify port 1143 in Bridge settings

### Google Drive 403 Error

**Symptom**: `Google Drive API 403 - quota exceeded or permission denied`

**Cause**: Service account token expired or insufficient permissions

**Fix**:
1. Check service account has Drive API enabled
2. Re-authenticate: `gcloud auth application-default login`

### Notion 403 Error

**Symptom**: `Notion API returned 403 Forbidden`

**Cause**: Integration not added to target page

**Fix**:
1. Open Notion page (Biomimetic OS)
2. Click `...` → `Connect to`
3. Select your integration

### Cloudflare Worker Not Triggering

**Symptom**: GitHub issues not appearing in Notion

**Fix**:
1. Check webhook URL in GitHub settings
2. Verify Cloudflare secret: `wrangler secret list`
3. Check worker logs: `wrangler tail`

---

## File Structure

```
~/biomimetics/
├── config/
│   └── omni_sync_config.json      # Main configuration
├── scripts/
│   ├── omni_sync.py               # Main sync heartbeat
│   ├── backfill_claws.py          # ProtonMail sync
│   ├── maintain_mycloud_mount.sh  # NAS mount watchdog
│   └── proton_sync_hourly.sh      # Email sync wrapper
├── launch_agents/
│   ├── com.arca.omni-sync.plist
│   ├── com.arca.proton-sync.plist
│   └── com.arca.mycloud-watchdog.plist
├── cloudflare/
│   ├── index.js                   # GitHub→Notion worker
│   └── wrangler.toml              # Worker config
├── docs/
│   └── SYSTEM_ARCHITECTURE.md     # This document
├── notion/                        # Notion templates/schemas
├── secrets/                       # .gitignored secrets
└── skills/                        # Custom automation skills
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-17 | Initial consolidation |

---

## Contact & Support

- **Repository**: https://github.com/danxalot/biomimetics
- **Primary Identity**: Claws <claws@arca-vsa.tech>
- **Project**: ARCA Development Ecosystem
