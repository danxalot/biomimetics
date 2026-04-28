---
tags: [bios/architecture, bios/infrastructure, bios/memory, bios/security, bios/swarm, bios/voice, source/legacy]
status: active
---

# Gemini Live Voice API - Project Knowledge Graph

## 🎯 Project Overview

**Name**: ARCA Live Voice Interface (Gemini Live API Implementation)
**Location**: `~/biomimetics/gemini-live-voice`
**Status**: ✅ Operational - Ready for deployment
**Version**: 1.0.0

---

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GEMINI LIVE VOICE INTERFACE                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐ │
│  │   React UI   │────────▶│  Gemini Live │────────▶│   Audio/Vision│ │
│  │  (Frontend)  │◀────────│     API      │◀────────│   Input/Output│ │
│  └──────────────┘         └──────────────┘         └──────────────┘ │
│         │                        │                                     │
│         │                        │                                     │
│         ▼                        ▼                                     │
│  ┌──────────────┐         ┌──────────────┐                           │
│  │ Tool Calling │         │  Real-time   │                           │
│  │  Framework   │         │   Session    │                           │
│  └──────────────┘         └──────────────┘                           │
│         │                                                            │
│         ├─────────────────┬──────────────────┐                       │
│         │                 │                  │                       │
│         ▼                 ▼                  ▼                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ query_memory │  │trigger_notion│  │  Future Tools│              │
│  │   (GCP)      │  │  (Cloudflare)│  │              │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│         │                 │                                          │
│         ▼                 ▼                                          │
│  ┌──────────────┐  ┌──────────────┐                                 │
│  │ GCP Memory   │  │ Cloudflare   │                                 │
│  │  Gateway     │  │   Worker     │                                 │
│  └──────────────┘  └──────────────┘                                 │
│         │                 │                                          │
│         ▼                 ▼                                          │
│  ┌──────────────┐  ┌──────────────┐                                 │
│  │ MuninnDB +   │  │   Notion     │                                 │
│  │   MemU       │  │  Databases   │                                 │
│  └──────────────┘  └──────────────┘                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Notion Database Schema

### Database 1: **Voice Session Logs**
**Purpose**: Track all voice interactions with Gemini Live API

| Property | Type | Description |
|----------|------|-------------|
| `Session ID` | Title | Unique session identifier |
| `Timestamp` | Date | When the session occurred |
| `User` | Select | User identifier (default: "voice_user") |
| `Duration` | Number | Session length in seconds |
| `Tool Calls` | Multi-select | Tools invoked during session |
| `Memory Queries` | Rich text | Summary of memory queries made |
| `Notion Actions` | Rich text | Notion actions triggered |
| `Transcript` | Rich text | Full conversation transcript |
| `Status` | Select | Success / Error / Incomplete |
| `API Cost` | Number | Token usage/cost for session |

**Database ID**: `[To be created]`

---

### Database 2: **Voice Tool Registry**
**Purpose**: Document all available tools for Gemini Live API

| Property | Type | Description |
|----------|------|-------------|
| `Tool Name` | Title | Name of the tool (e.g., "query_memory") |
| `Description` | Rich text | What the tool does |
| `Endpoint` | URL | API endpoint URL |
| `Parameters` | Rich text | JSON schema for parameters |
| `Status` | Select | Active / Deprecated / In Development |
| `Last Used` | Date | Last time tool was invoked |
| `Success Rate` | Percent | Historical success rate |
| `Avg Response Time` | Number | Average response time in ms |
| `Owner` | Select | Team member responsible |

**Database ID**: `[To be created]`

---

### Database 3: **Voice Interface Tasks**
**Purpose**: Track development and maintenance tasks

| Property | Type | Description |
|----------|------|-------------|
| `Task Name` | Title | Name of the task |
| `Status` | Status | Not Started / In Progress / Done |
| `Priority` | Select | P0 / P1 / P2 / P3 |
| `Assigned To` | Person | Team member assigned |
| `Due Date` | Date | Task deadline |
| `Related Tool` | Relation | Link to Tool Registry |
| `Session Link` | Relation | Link to Session Logs |
| `Github Issue` | URL | Link to GitHub issue |
| `Description` | Rich text | Task details |
| `Tags` | Multi-select | Feature / Bug / Enhancement / Docs |

**Database ID**: `[To be created]`

---

### Database 4: **Voice API Configuration**
**Purpose**: Store configuration and secrets references

| Property | Type | Description |
|----------|------|-------------|
| `Config Name` | Title | Configuration name |
| `Environment` | Select | Development / Staging / Production |
| `API Key Ref` | Rich text | Reference to secret (not the secret itself) |
| `Model` | Select | gemini-2.5-flash / gemini-2.0-flash-live |
| `GCP Gateway URL` | URL | Memory orchestrator endpoint |
| `Cloudflare Worker URL` | URL | Notion webhook router |
| `Last Updated` | Date | When config was last modified |
| `Updated By` | Person | Who made the last update |
| `Status` | Select | Active / Deprecated |

**Database ID**: `[To be created]`

---

## 🔧 Technical Components

### 1. **Frontend (React + TypeScript)**
**Location**: `gemini-live-voice/src/`

| File | Purpose |
|------|---------|
| `App.tsx` | Main application component with Live API integration |
| `index.css` | Styling |
| `main.tsx` | React entry point |
| `vite-env.d.ts` | Vite type definitions |

**Key Features**:
- Real-time voice input/output
- Camera support for vision input
- Tool calling visualization
- Session management
- PWA support (offline capable)

---

### 2. **Tool Implementations**

#### **query_memory**
```typescript
{
  name: 'query_memory',
  description: 'Query the unified memory system (MuninnDB + MemU)',
  parameters: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Search query' },
      user_id: { type: 'string', default: 'voice_user' }
    },
    required: ['query']
  }
}
```

**Endpoint**: `https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator`

**Response Format**:
```json
{
  "status": "success",
  "results": [
    {
      "content": "Memory content...",
      "source": "muninn" | "memu",
      "confidence": 0.95
    }
  ],
  "token_usage": { "total": 1024 }
}
```

---

#### **trigger_notion_action**
```typescript
{
  name: 'trigger_notion_action',
  description: 'Trigger Notion action or workflow',
  parameters: {
    type: 'object',
    properties: {
      action: {
        type: 'string',
        enum: ['create_task', 'update_page', 'plan_feature', 
               'review_code', 'summarize_meeting', 'create_github_issue']
      },
      data: { type: 'object', description: 'Action payload' }
    },
    required: ['action', 'data']
  }
}
```

**Endpoint**: Cloudflare Worker URL (configured via environment)

**Response Format**:
```json
{
  "status": "success",
  "action": "create_task",
  "result": { "notion_page_id": "..." }
}
```

---

### 3. **Build & Deployment**

**Package Manager**: npm
**Build Tool**: Vite + TypeScript
**Deployment**: Cloudflare Pages

```bash
# Development
npm run dev

# Build for production
npm run build

# Deploy to Cloudflare Pages
npm run deploy

# Lint
npm run lint
```

---

## 🔐 Secrets & Configuration

### Required Secrets

| Secret | Storage | Usage |
|--------|---------|-------|
| `GEMINI_API_KEY` | User input (localStorage) | Gemini Live API authentication |
| `CLOUDFLARE_WORKER_URL` | Environment variable | Notion webhook router |
| `GCP_GATEWAY_URL` | wrangler.toml (public) | Memory orchestrator endpoint |

### Environment Variables

```toml
# wrangler.toml
[vars]
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
```

---

## 📈 Deployment Status

| Environment | URL | Status |
|-------------|-----|--------|
| **Development** | `http://localhost:3000` | ✅ Local |
| **Cloudflare Pages** | `https://arca-live-voice.<subdomain>.pages.dev` | ⏳ Ready to deploy |
| **Production** | `https://voice.biomimetics.arca-vsa.tech` | ⏳ Pending domain setup |

---

## 🎯 Integration Points

### 1. **GCP Memory Gateway**
- **Service**: Cloud Functions (memory-orchestrator)
- **Purpose**: Unified query interface for MuninnDB + MemU
- **Status**: ✅ Operational

### 2. **Cloudflare Worker (Notion Webhook Router)**
- **Service**: Cloudflare Workers
- **Purpose**: Route voice commands to Notion API
- **Worker URL**: `https://arca-github-notion-sync.dan-exall.workers.dev`
- **Status**: ✅ Operational (needs voice action handlers)

### 3. **Notion Databases**
- **Biomimetic OS**: `3284d2d9-fc7c-8111-88de-eeaba9c5f845`
- **Life OS Triage**: `3284d2d9-fc7c-8111-88de-eeaba9c5f845`
- **Tool Guard**: `3284d2d9-fc7c-8113-bfe-ecca75f4235ece`
- **Status**: ⏳ Voice Session Logs DB needs creation

---

## 🚀 Quick Start Guide

### 1. Clone & Install
```bash
cd ~/biomimetics/gemini-live-voice
npm install
```

### 2. Configure Environment
```bash
# Edit wrangler.toml if needed
cp wrangler.toml wrangler.toml.local
```

### 3. Run Development Server
```bash
npm run dev
# Opens at http://localhost:3000
```

### 4. Deploy to Cloudflare
```bash
# Set secrets
wrangler secret put GEMINI_API_KEY  # Optional - users input in UI
wrangler secret put CLOUDFLARE_WORKER_URL

# Deploy
npm run deploy
```

---

## 🐛 Known Issues & TODOs

### High Priority
- [ ] Create Notion "Voice Session Logs" database
- [ ] Add error handling for offline scenarios
- [ ] Implement session persistence across page reloads
- [ ] Add user authentication (Firebase Auth)

### Medium Priority
- [ ] Add screen sharing capability
- [ ] Implement voice activity detection (VAD)
- [ ] Add conversation history in UI
- [ ] Implement cost tracking dashboard

### Low Priority
- [ ] Add custom wake word detection
- [ ] Implement multi-user support
- [ ] Add voice customization (pitch, speed)
- [ ] Create mobile app wrapper (React Native)

---

## 📚 Related Documentation

| Document | Location |
|----------|----------|
| System Architecture | `~/biomimetics/docs/SYSTEM_ARCHITECTURE.md` |
| MCP Integration | `~/biomimetics/docs/MCP_INTEGRATION.md` |
| Azure Secrets | `~/biomimetics/docs/AZURE_SECRETS.md` |
| GitHub Webhook | `~/biomimetics/docs/GITHUB_WEBHOOK_SETUP.md` |

---

## 👥 Team & Responsibilities

| Role | Person | Responsibilities |
|------|--------|------------------|
| **Project Lead** | Dan | Architecture, deployment |
| **Frontend Dev** | [TBD] | UI/UX, React components |
| **Backend Dev** | [TBD] | Tool implementations, API integration |
| **DevOps** | [TBD] | Cloudflare deployment, monitoring |

---

## 📊 Metrics & KPIs

| Metric | Target | Current |
|--------|--------|---------|
| Session Success Rate | >95% | TBD |
| Avg Response Time | <2s | TBD |
| Tool Call Accuracy | >90% | TBD |
| Monthly Active Users | 100+ | TBD |
| API Cost per Session | <$0.01 | TBD |

---

**Last Updated**: 2026-03-18
**Document Owner**: Serena (Biomimetics Orchestrator)
**Next Review**: 2026-03-25
