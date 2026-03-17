# Biomimetics

> **Project Management & Optimization Layer for ARCA Development Ecosystem**

Biomimetics is the infrastructure automation system that provides:
- 📧 **Email Synchronization** - 5 ProtonMail accounts + Gmail
- 📁 **File Processing** - Google Drive with intelligent circuit breakers
- 📊 **Project Tracking** - Notion databases for issues and tasks
- ⚡ **Event Processing** - Cloudflare Workers for GitHub webhooks
- 🔔 **System Monitoring** - macOS LaunchAgents for continuous operation

---

## Quick Start

### Prerequisites

- macOS 12.0+
- Python 3.12+
- Proton Mail Bridge (running)
- Notion API access
- Google Cloud credentials

### Installation

```bash
# Clone repository
git clone https://github.com/danxalot/biomimetics.git ~/biomimetics
cd ~/biomimetics

# Install Python dependencies
pip3 install google-api-python-client google-auth-httplib2 requests python-dateutil

# Configure secrets
cp config/omni_sync_config.json.example config/omni_sync_config.json
# Edit config/omni_sync_config.json with your credentials

# Load LaunchAgents
./scripts/install_agents.sh
```

### Deploy Cloudflare Worker

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

- [System Architecture](docs/SYSTEM_ARCHITECTURE.md) - Full technical documentation
- [Configuration Guide](docs/CONFIGURATION.md) - Setup and secrets
- [Troubleshooting](docs/SYSTEM_ARCHITECTURE.md#troubleshooting) - Common issues

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
