---
tags: [bios/architecture, bios/infrastructure, bios/memory, bios/security, bios/swarm, bios/voice, context/life, source/legacy]
status: active
---

# System Configuration & Voice Routing Audit

**Generated:** 2026-03-20  
**Scope:** `~/biomimetics` and `/Users/danexall/Documents/VS Code Projects/`  
**Purpose:** Deep state discovery of operational components, connection endpoints, and LLM assignments

---

## Executive Summary

This audit reveals a **partially integrated system** with functional local execution but **critical disconnections** in the voice→approval→execution pipeline. The Computer Use agent runs unrestricted, CoPaw voice is disabled, and approval decisions are logged but never actioned.

---

## 1. Project Management Layer (Cloudflare/GitHub)

### PM Agent (Gemma-3-27b)

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ Configured in Cloudflare Worker |
| **Location** | `cloudflare/index.js:routePMAgent()` |
| **LLM** | **Gemma-3-27b** via Google AI Studio v1beta |
| **Trigger** | Cron: `0 */6 * * *` (every 6hrs) OR POST with `X-Arca-Source: PM-Agent` |
| **API Key** | `GEMINI_API_KEY` in `cloudflare/wrangler.toml` |

**Execution Flow:**
```
Cron/Manual Trigger
    ↓
routePMAgent()
    ↓
gatherGitHubContext() → GitHub API (issues, PRs, commits)
    ↓
buildPMAPrompt() → Construct prompt with repo state
    ↓
callGemma(gemma-3-27b) → Google AI Studio
    ↓
parsePMResponse() → Extract JSON actions
    ↓
executePMActions() → GitHub API OR forward to Serena
    ↓
Return summary
```

### GitHub Repository Planner

| Attribute | Value |
|-----------|-------|
| **Status** | ⚠️ Partial - Webhooks configured |
| **Worker Routes** | `issues`, `pull_request`, `push` events |
| **Endpoint** | `https://arca-github-notion-sync.dan-exall.workers.dev` |
| **Databases** | Biomimetic OS: `3284d2d9fc7c811188deeeaba9c5f845` |

**⚠️ DISCONNECTED BRIDGE:** No GitHub workflows found in `~/.github/workflows/`. The PM Agent relies solely on Cloudflare cron triggers, not native GitHub Actions integration.

---

## 2. Voice & Ubiquity Layer (Gemini/CoPaw)

### Gemini Live API Client

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ Client implemented |
| **Location** | `gemini-live-voice/src/App.tsx` |
| **Model** | `gemini-2.5-flash` |
| **API Key** | User-provided (stored in localStorage) |
| **Tools** | `query_memory`, `trigger_notion_action` |

**Tool Endpoints:**
- `query_memory` → `https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator`
- `trigger_notion_action` → Cloudflare Worker (`CLOUDFLARE_WORKER_URL`)

### CoPaw Configuration

| Attribute | Value |
|-----------|-------|
| **Config File** | `~/.copaw/config.json` |
| **Status** | ⚠️ Console-only (voice disabled) |
| **Local MCP** | `127.0.0.1:8088` |
| **Voice Channel** | `enabled: false` |
| **LLM Routing** | `enabled: false` (mode: `local_first`) |
| **Active Tools** | 9 builtin tools enabled |

**Enabled Tools:**
1. `execute_shell_command`
2. `read_file`
3. `write_file`
4. `edit_file`
5. `browser_use`
6. `desktop_screenshot`
7. `send_file_to_user`
8. `get_current_time`
9. `get_token_usage`

**Disabled Channels:**
- `imessage`: ❌
- `discord`: ❌
- `telegram`: ❌
- `voice` (Twilio): ❌
- `matrix`: ❌
- `mqtt`: ❌

### CoPaw Tool Guard

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ Active |
| **Location** | `scripts/copaw/copaw-tool-guard.py` |
| **Approval DB** | `3284d2d9fc7c8113bfecca75f4235ece` (CoPaw Approval) |
| **High-Risk Patterns** | `git push`, `git commit`, `rm -rf`, `sudo`, `curl|sh`, `serena.execute_shell_command` |

**⚠️ CRITICAL DISCONNECTS:**

1. **CoPaw voice channel is DISABLED** - No Gemini Live API integration
2. **CoPaw LLM routing is OFF** - `agents.llm_routing.enabled: false`
3. **Gemini API key not shared** - CoPaw config has no reference to Gemini credentials
4. **Twilio voice config empty** - No phone integration configured

---

## 3. Local Execution Layer (Computer Use & Serena)

### Computer Use MCP

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ Running (LaunchAgent active) |
| **LaunchAgent** | `com.arca.computer-use-mcp.plist` |
| **Script** | `/Users/danexall/computer-use-mcp.py` |
| **Permissions** | Full screen/mouse/keyboard via `pyautogui` |
| **Transport** | `stdio_server` - MCP protocol |
| **Local Model** | Qwen-VL (for screen analysis) |

**Security Configuration:**
```python
pyautogui.FAILSAFE = True   # Move mouse to corner to abort
pyautogui.PAUSE = 0.5       # 500ms pause between actions
```

**Available Tools:**
- `take_screenshot` - Capture screen (base64)
- `move_mouse` - Move cursor to (x, y)
- `click` - Mouse click
- `type_text` - Keyboard input
- `get_screen_info` - Screen metadata

### Serena Memory Sync

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ Running (LaunchAgent active) |
| **LaunchAgent** | `com.arca.serena-sync.plist` |
| **Script** | `/Users/danexall/serena-memory-sync.py` |
| **Interval** | 300 seconds (5 minutes) |
| **Source Dir** | `~/.serena/memories/*.md` |
| **Gateway** | `https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator` |

**Sync Flow:**
```
Scan ~/.serena/memories/
    ↓
Compute MD5 hash for each .md file
    ↓
Compare with stored hashes
    ↓
If modified → Read content + metadata
    ↓
POST to GCP Gateway (memorize operation)
    ↓
Update state file (~/.arca/serena_sync_state.json)
```

**⚠️ DISCONNECT:** Computer Use agent has **no approval gateway** - all actions execute immediately without Tool Guard interception.

---

## 4. Approval & Routing Bridge

### Current State

| Bridge | Status | Mechanism | Gap |
|--------|--------|-----------|-----|
| **Notion Approval → Computer Use** | ❌ **NOT IMPLEMENTED** | Tool Guard creates approval records in Notion, but Computer Use MCP bypasses Tool Guard | No polling/webhook bridges approval decisions to local execution |
| **Gemini Live → Notion Approval** | ⚠️ **PARTIAL** | `trigger_notion_action` tool can POST to Cloudflare Worker | Worker's `handleApprovalResponse()` is stub-only (logs but doesn't update Notion) |
| **Cloudflare → Local Execution** | ❌ **NO BRIDGE** | Worker can't reach localhost Computer Use | No reverse tunnel (ngrok/cloudflared) configured |

### Intended Approval Flow (Not Working)

```
User Voice (Gemini Live)
    ↓
trigger_notion_action tool
    ↓
Cloudflare Worker POST
    ↓
CoPaw Approval Database (3274d2d9...)
    ↓
[MISSING: Poller/Webhook Listener]
    ↓
Computer Use MCP
    ↓
Execute Approved Action
```

### Current Reality

- ✅ Approvals are **logged** to Notion
- ❌ Approvals are **never actioned** (no listener)
- ❌ Computer Use runs **unrestricted** (no guard intercept)
- ⚠️ Gemini Live can **create tasks** but cannot **trigger execution**

---

## 5. Active LaunchAgents Summary

| Label | PID | Status | Interval | Target Script |
|-------|-----|--------|----------|---------------|
| `com.arca.computer-use-mcp` | 2 | ✅ Running | KeepAlive | `/Users/danexall/computer-use-mcp.py` |
| `com.arca.serena-sync` | 2 | ✅ Running | KeepAlive | `/Users/danexall/serena-memory-sync.py` |
| `com.arca.omni-sync` | 10683 | ✅ Running | 300s | `/Users/danexall/biomimetics/scripts/omni_sync.py` |
| `com.arca.proton-sync` | 0 | ⏸️ Idle | 3600s | `/Users/danexall/biomimetics/scripts/proton_sync_hourly.sh` |
| `com.arca.mycloud-watchdog` | 0 | ⏸️ Idle | 60s | `/Users/danexall/biomimetics/scripts/maintain_mycloud_mount.sh` |

**Notes:**
- PID 0 = Agent loaded but not currently executing
- `proton-sync` idle may indicate email ingestion is broken
- `mycloud-watchdog` idle suggests mount is stable

---

## 6. Secret & Endpoint Inventory

### Cloudflare Worker Secrets (`cloudflare/wrangler.toml`)

| Secret | Value | Purpose |
|--------|-------|---------|
| `GEMINI_API_KEY` | `AIzaSyDfnNa-IJpPZGB0Jfc4QqvVK_jIJXNWtpY` | Google AI Studio access (PM Agent) |
| `GITHUB_TOKEN` | `[GITHUB_TOKEN_REDACTED]` | GitHub API access |
| `NOTION_DB_ID` | `3284d2d9fc7c811188deeeaba9c5f845` | Biomimetic OS database |
| `BIOMIMETIC_DB_ID` | `3284d2d9fc7c811188deeeaba9c5f845` | Alias for NOTION_DB_ID |
| `LIFE_OS_TRIAGE_DB_ID` | `3284d2d9fc7c81bd9a91e865511e642f` | Life OS Triage database |
| `TOOL_GUARD_DB_ID` | `3284d2d9fc7c8113bfecca75f4235ece` | Tool Guard database |
| `COPAW_APPROVAL_DB_ID` | `3284d2d9fc7c8113bfecca75f4235ece` | CoPaw approvals database |
| `GCP_GATEWAY` | `https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator` | Memory gateway URL |

### Koyeb Deployment

| Secret | Value | Purpose |
|--------|-------|---------|
| `KOYEB_TOKEN` | `ov7hvgjlgi7m3yqil12aufkgoeejj2gqbtnkq8q7voz29m011nphncevyuqbva4g` | Koyeb API authentication |

### Deployed Endpoints

| Service | URL | Status |
|---------|-----|--------|
| GitHub MCP (Koyeb) | `https://github-mcp-server-arca-vsa-3c648978.koyeb.app/sse` | ✅ HEALTHY |
| Cloudflare Worker | `https://arca-github-notion-sync.dan-exall.workers.dev` | ✅ Active |
| GCP Memory Gateway | `https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator` | ✅ Active |

---

## 7. Critical Gaps & Recommendations

### Priority Matrix

| Priority | Gap | Risk | Recommendation |
|----------|-----|------|----------------|
| **P0** | CoPaw voice disabled, no Gemini Live integration | Voice layer non-functional | Enable `voice` channel in `~/.copaw/config.json` and integrate Gemini Live API key |
| **P0** | Computer Use bypasses Tool Guard | Unrestricted local execution | Route all Computer Use tool calls through `copaw-tool-guard.py` |
| **P1** | Approval→Execution bridge missing | Approvals logged but never actioned | Implement polling service or webhook listener for approval DB changes |
| **P1** | Cloudflare Worker can't reach localhost | No remote→local command routing | Configure cloudflared tunnel for reverse proxy to localhost:8088 |
| **P2** | PM Agent uses hardcoded repo (`danxalot/ARCA`) | Won't work for `biomimetics` repo | Update `gatherGitHubContext()` to use configurable owner/repo |
| **P2** | Proton-sync idle (PID 0) | Email ingestion may be broken | Check logs at `~/.arca/proton_sync.err` and restart agent |

### Immediate Actions Required

1. **Enable CoPaw Voice Channel**
   ```json
   // ~/.copaw/config.json
   "voice": {
     "enabled": true,
     "tts_provider": "google",
     "stt_provider": "deepgram",
     "gemini_api_key": "AIzaSyDfnNa-IJpPZGB0Jfc4QqvVK_jIJXNWtpY"
   }
   ```

2. **Route Computer Use Through Tool Guard**
   - Modify `computer-use-mcp.py` to import and use `ToolGuard` class
   - Add approval check before executing high-risk operations

3. **Implement Approval Poller**
   ```python
   # New script: scripts/copaw/approval-poller.py
   # Polls CoPaw Approval DB every 30s
   # Triggers local execution on status change
   ```

4. **Configure Reverse Tunnel**
   ```bash
   # Install cloudflared
   brew install cloudflared
   # Tunnel to CoPaw MCP
   cloudflared tunnel --url http://localhost:8088
   ```

---

## 8. Architecture Diagram (Current State)

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLOUD LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Gemini     │    │   Cloudflare │    │     GCP      │      │
│  │  Live Voice  │    │    Worker    │    │   Gateway    │      │
│  │              │    │              │    │              │      │
│  │ gemini-2.5-  │    │ arca-github- │    │ memory-      │      │
│  │ flash        │    │ notion-sync  │    │ orchestrator │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         │ trigger_notion    │ webhook           │ memorize      │
│         │ action            │ POST              │ query         │
│         ▼                   ▼                   ▼               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Notion Databases                           │   │
│  │  • Biomimetic OS (3224d2d9...)                          │   │
│  │  • Life OS Triage (3254d2d9...)                         │   │
│  │  • Tool Guard (3254d2d9...)                             │   │
│  │  • CoPaw Approval (3274d2d9...) ← APPROVALS LOGGED HERE │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                            ⚠️ NO BRIDGE
                            (No tunnel/webhook)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LOCAL LAYER                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │    CoPaw     │    │  Computer    │    │   Serena     │      │
│  │              │    │    Use MCP   │    │    Sync      │      │
│  │ console: ✅  │    │              │    │              │      │
│  │ voice: ❌    │    │ pyautogui    │    │ ~/.serena/   │      │
│  │ LLM: ❌      │    │ unrestricted │    │ memories/    │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         │ MCP               │ stdio             │ poll 300s     │
│         │ localhost:8088    │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Local Filesystem                           │   │
│  │  • ~/.copaw/media/                                      │   │
│  │  • Screen capture & control                             │   │
│  │  • Shell execution                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix A: File Locations

| Component | Path |
|-----------|------|
| Cloudflare Worker | `~/biomimetics/cloudflare/index.js` |
| CoPaw Config | `~/.copaw/config.json` |
| Computer Use MCP | `~/biomimetics/scripts/mcp/computer-use-mcp.py` |
| Serena Sync | `~/biomimetics/scripts/memory/serena-memory-sync.py` |
| Tool Guard | `~/biomimetics/scripts/copaw/copaw-tool-guard.py` |
| Gemini Live Voice | `~/biomimetics/gemini-live-voice/src/App.tsx` |
| LaunchAgents | `~/Library/LaunchAgents/com.arca.*.plist` |

---

## Appendix B: Verification Commands

```bash
# Check LaunchAgent status
launchctl list | grep arca

# View Computer Use logs
tail -f ~/.arca/computer-use-mcp.log

# View Serena Sync logs
tail -f ~/.arca/serena-sync.log

# Test CoPaw MCP endpoint
curl http://localhost:8088/health

# Check Cloudflare Worker
curl https://arca-github-notion-sync.dan-exall.workers.dev/ping

# Test GCP Gateway
curl -X POST https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator \
  -H "Content-Type: application/json" \
  -d '{"operation": "ping"}'
```

---

**Document Version:** 1.0  
**Generated By:** Qwen Code (System Discovery)  
**Date:** 2026-03-20T00:00:00Z
