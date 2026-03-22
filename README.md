# Biomimetics

> **Project Management & Optimization Layer for ARCA Development Ecosystem**

Biomimetics is the infrastructure automation system that provides:
- 🔐 **Secret Management** - Azure Key Vault integration (single source of truth)
- 📧 **Email Synchronization** - 5 ProtonMail accounts + Gmail
- 📁 **File Processing** - Google Drive with intelligent circuit breakers
- 📊 **Project Tracking** - Notion databases + MCP Server integration
- ⚡ **Event Processing** - Cloudflare Workers for GitHub webhooks, Serena agents, GCP memory, CoPaw integration, and Gemma‑3‑27b powered Project‑Manager agent
- 🧠 **Intelligent Memory** - GCP Cloud Function integration for contextual AI
- 🛡️ **Approval Workflows** - CoPaw tool guard for safe AI agent operations
- 🔔 **System Monitoring** - macOS LaunchAgents for continuous operation
- 🎙️ **Live Voice Interface** - Gemini Live API for voice/vision interaction

---

## Quick Start

### Prerequisites

- macOS 12.0+
- Python 3.12+
- Node.js 18+ (for Gemini Live Voice)
- Azure CLI (for secrets)
- Proton Mail Bridge (running)
- Notion API access
- Google Cloud credentials

### Installation

```bash
# Clone repository
git clone https://github.com/danxalot/biomimetics.git ~/biomimetics
cd ~/biomimetics

# Initialize secrets from Azure Key Vault
az login
python3 azure/azure_secrets_init.py --refresh

# Setup Notion MCP Server
./scripts/setup_notion_mcp.sh

# Load LaunchAgents
./scripts/install_agents.sh
```

### Project Structure

```
~/biomimetics/
├── scripts/           # All automation scripts (organized by category)
│   ├── mcp/          # MCP servers
│   ├── copaw/        # CoPaw integration
│   ├── email/        # Email services
│   ├── memory/       # Memory services
│   ├── sync/         # Sync services
│   ├── vision/       # Vision services
│   ├── muninn/       # MuninnDB services
│   ├── deploy/       # Deployment scripts
│   └── setup/        # Setup scripts (phase 2-7)
├── docs/             # Documentation
│   ├── phases/       # Phase workflow docs
│   └── ...
├── gemini-live-voice/ # Voice interface
├── cloudflare/        # Cloudflare Workers
├── config/           # Configuration files
└── notion/           # Notion templates
```

### Gemini Live Voice Interface

```bash
cd ~/biomimetics/gemini-live-voice
npm install
npm run dev  # Opens at http://localhost:3000
```

### Deploy Cloudflare Worker

```bash
cd ~/biomimetics/cloudflare
npx wrangler deploy
```

```bash
cd cloudflare
npx wrangler deploy
# Copy the Worker URL to GitHub webhook settings
```

---

## Components

| Component | Purpose | Schedule |
|-----------|---------|----------|
| `omni_sync.py` | Main sync heartbeat | Continuous |
| `backfill_claws.py` | ProtonMail sync | Hourly |
| `maintain_mycloud_mount.sh` | NAS mount keepalive | 60 seconds |
| Cloudflare Worker | GitHub → Notion bridge | On webhook |

---

## Documentation

### Quick Start
- **[MCP Integration QuickStart](MCP_QUICKSTART.md)** - Get started with MCP integration (5-15 min)
- **[System Architecture](docs/SYSTEM_ARCHITECTURE.md)** - Full technical documentation

### MCP Integration
- **[MCP Integration Status](docs/MCP_INTEGRATION_STATUS.md)** - Current status and configuration
- **[MCP Integration Summary](docs/MCP_INTEGRATION_SUMMARY.md)** - What was done and next steps
- **[ARCA MCP Integration](docs/ARCA_MCP_INTEGRATION.md)** - ARCA project integration guide
- **[General MCP Guide](docs/MCP_INTEGRATION.md)** - MCP server setup for all clients

### System Documentation
- [System Architecture](docs/SYSTEM_ARCHITECTURE.md) - Full technical documentation
- [Azure Secrets](docs/AZURE_SECRETS.md) - Azure Key Vault setup
- [GitHub Webhook Setup](docs/GITHUB_WEBHOOK_SETUP.md) - GitHub webhook configuration
- [Gemini Live Voice](docs/GEMINI_LIVE_VOICE_PROJECT.md) - Voice interface documentation

### Phase Documentation
- [Phase 4: Azure Integration](docs/phases/PHASE4-WORKFLOW.md)
- [Phase 5: Email Sync](docs/phases/PHASE5-WORKFLOW.md)
- [Phase 6: Unified Inbox](docs/phases/PHASE6-WORKFLOW.md)
- [Phase 7: Voice Interface](docs/phases/PHASE7-WORKFLOW.md)

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ ProtonMail  │     │   Gmail     │     │Google Drive │
│  (5 accts)  │     │   IMAP      │     │   API       │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│              omni_sync.py (Heartbeat)                   │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              GCP Gateway (Cloud Functions)              │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │  Notion  │   │  Local   │   │ Cloud    │
   │  DBs     │   │ Storage  │   │ Storage  │
   └──────────┘   └──────────┘   └──────────┘
```

---

## License

Private - ARCA Project

---

## Contact

- **Repository**: https://github.com/danxalot/biomimetics
- **Identity**: Claws <claws@arca-vsa.tech>
