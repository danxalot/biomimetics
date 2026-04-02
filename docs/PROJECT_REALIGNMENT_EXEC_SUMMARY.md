# Project Realignment - Executive Summary

**Date**: 2026-03-19  
**Status**: Discovery Complete ✅ | Awaiting User Input ⏳

---

## What Was Done

### Phase 1: Environment & Secrets Discovery ✅

**1. Notion Database IDs**
- ✅ Biomimetics OS databases identified (4 databases)
- ❌ ARCA databases NOT found - **NEED YOUR INPUT**

**2. Secrets Architecture**
- ✅ Location: `/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/`
- ✅ 140+ secret files identified
- ✅ Loading mechanism: Direct file read (shell `cat` commands)
- ✅ Key secrets found:
  - `notion_api_key` → `[NOTION_TOKEN_REDACTED]`
  - `github_token` → `[GITHUB_TOKEN_REDACTED]`
  - `google_api_studio` → `[REDACTED]`

**3. Directory Bridging**
- ✅ 3 files with hardcoded paths identified:
  - `scripts/deploy/redeploy-github-mcp.sh`
  - `scripts/deploy/deploy-github-mcp-sse.sh`
  - `scripts/memory/migrate_claws_data.py`
- ✅ Fix: Use `$ARCA_SECRETS_DIR` environment variable

---

### Phase 2: Security & State Cleanup ✅

**4. Git Blockade Resolution**
- ✅ URL: https://github.com/danxalot/biomimetics/security/secret-scanning/unblock-secret/3B4PG0GOqurXoHeMQm8L2SAS1Sr
- ✅ Procedure documented (2-minute allow vs 30-min history rewrite)

**5. Azure Teardown Strategy**
- ✅ Resources identified:
  - `arca-consolidated` RG: ACR + stopped container
  - `arca-rg` RG: 2 Key Vaults (still used by Biomimetics)
- ✅ Teardown steps documented
- ✅ Savings: $5/month ($60/year)

---

### Phase 3: Migration Preparation ✅

**6. GitHub MCP Dockerfile Analysis**
- ✅ Location: `/Users/danexall/github-mcp-super-gateway/Dockerfile`
- ✅ Base: Node 20 Alpine
- ✅ Packages: `@modelcontextprotocol/server-github` + `supergateway`
- ✅ Resource usage: ~50-100MB RAM, <0.1 CPU (idle)
- ✅ Koyeb Compatibility: **FULLY COMPATIBLE** ✅

**7. Free Tier Deployment Plan**
- ✅ Koyeb: 0.1 vCPU / 512MB / Always-on / FREE
- ✅ Deployment script created: `scripts/migrate/deploy-to-koyeb.sh`
- ✅ Environment variables: `GITHUB_PERSONAL_ACCESS_TOKEN` only
- ✅ Alternative: Vultr ($2.50/month)

---

## What I Need From You

### 1. ARCA Notion Database IDs (5 minutes)

Open Notion and provide these database IDs:

```
ARCA_PROJECTS_DB_ID = ________________________
ARCA_TASKS_DB_ID    = ________________________
ARCA_MEMORY_DB_ID   = ________________________
```

**How to find**:
1. Open Notion → ARCA database
2. Click `•••` → `Copy link`
3. Extract 32-character hex ID from URL

---

### 2. Git Secret Decision (1 minute)

**Option A** (Recommended): Allow the secret
```
Visit: https://github.com/danxalot/biomimetics/security/secret-scanning/unblock-secret/3B4PG0GOqurXoHeMQm8L2SAS1Sr
Click: "Allow this secret"
Time: 2 minutes
```

**Option B**: Rotate secret + rewrite history
```
Time: 30+ minutes
Only if secret is still sensitive
```

---

### 3. Migration Decision (1 minute)

**Koyeb** (Recommended): Free, managed, always-on
```
Cost: $0/month
Setup: 15 minutes
Command: ./scripts/migrate/deploy-to-koyeb.sh
```

**Vultr**: Paid, full VM control
```
Cost: $2.50/month
Setup: 30 minutes
```

---

## Files Created

| File | Purpose |
|------|---------|
| `docs/PROJECT_REALIGNMENT.md` | Full discovery report (40 pages) |
| `docs/PROJECT_REALIGNMENT_EXEC_SUMMARY.md` | This document |
| `scripts/migrate/deploy-to-koyeb.sh` | Koyeb migration script |

---

## Next Steps

### Immediate (Today)

1. **Provide ARCA Database IDs** (5 min)
2. **Resolve Git Block** (2 min)
3. **Decision**: Koyeb or Vultr? (1 min)

### This Week

4. **Run Migration** (15 min)
   ```bash
   cd ~/biomimetics
   ./scripts/migrate/deploy-to-koyeb.sh
   ```

5. **Update Clients** (5 min)
   - Zed Editor
   - Antigravity
   - CoPaw

6. **Azure Teardown** (5 min)
   ```bash
   az container delete -g arca-consolidated -n github-mcp-server --yes
   ```

---

## Architecture After Migration

```
┌─────────────────────────────────────────────────────────┐
│                    CLIENTS                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │   Zed    │  │Antigravity│  │  CoPaw   │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │             │             │                     │
│       └─────────────┴─────────────┘                     │
│                     │                                   │
│                     ▼                                   │
│       ┌───────────────────────────────┐                │
│       │  KOYEB (Free Tier)            │                │
│       │  github-mcp-server            │                │
│       │  0.1 vCPU / 512MB / Always-on │                │
│       └───────────────────────────────┘                │
│                     │                                   │
│                     ▼                                   │
│       ┌───────────────────────────────┐                │
│       │  GitHub API                   │                │
│       └───────────────────────────────┘                │
│                                                         │
│  SECRETS: /Users/danexall/Documents/VS Code Projects/ARCA/.secrets/
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Cost Comparison

| Service | Before | After | Savings |
|---------|--------|-------|---------|
| Azure ACR | $5.00 | $0.00 | $5.00/month |
| Azure ACI | $0.00 (stopped) | $0.00 | $0.00 |
| Koyeb | $0.00 | $0.00 | $0.00 |
| **Total** | **$5.00** | **$0.00** | **$60/year** |

---

## Contact

**Full Report**: `docs/PROJECT_REALIGNMENT.md`  
**Migration Script**: `scripts/migrate/deploy-to-koyeb.sh`  
**Questions**: Provide ARCA database IDs and migration preference

---

**Status**: ⏳ Awaiting your input to proceed
