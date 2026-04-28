---
tags: [bios/architecture, bios/infrastructure, bios/memory, bios/security, bios/swarm, bios/voice, source/legacy]
status: active
---

# Biomimetics Project - Comprehensive Audit & Consolidation Report

**Date**: 2026-03-18  
**Auditor**: Serena (Biomimetics Orchestrator)  
**Status**: In Progress

---

## Executive Summary

This document provides a complete audit of all project files scattered across the home directory (`~/`) that should be consolidated into the `~/biomimetics` project folder for proper version control, documentation, and development tracking.

---

## 1. Current Project Structure

### ✅ Already in ~/biomimetics

```
~/biomimetics/
├── azure/                    # Azure secrets integration
├── cloudflare/               # Cloudflare Worker (GitHub→Notion)
├── config/                   # Configuration files
├── docs/                     # Documentation
│   ├── SYSTEM_ARCHITECTURE.md
│   ├── AZURE_SECRETS.md
│   ├── GITHUB_WEBHOOK_SETUP.md
│   ├── MCP_INTEGRATION.md
│   └── GEMINI_LIVE_VOICE_PROJECT.md
├── gemini-live-voice/        # Gemini Live API implementation
├── launch_agents/            # macOS LaunchAgents
├── scripts/                  # Automation scripts
└── secrets/                  # Local secrets (gitignored)
```

---

## 2. Files Requiring Relocation

### 2.1 High Priority - Core Functionality

| File | Current Location | Purpose | Target Location |
|------|------------------|---------|-----------------|
| `computer-use-mcp.py` | `~/` | Computer Use MCP server | `~/biomimetics/scripts/mcp/` |
| `copaw-*.py` (3 files) | `~/` | CoPaw integration scripts | `~/biomimetics/scripts/copaw/` |
| `email-ingestion-daemon.py` | `~/` | Email ingestion service | `~/biomimetics/scripts/email/` |
| `serena-memory-sync.py` | `~/` | Serena memory synchronization | `~/biomimetics/scripts/memory/` |
| `obsidian-sync-skill.py` | `~/` | Obsidian vault sync | `~/biomimetics/scripts/sync/` |
| `vision-router.py` | `~/` | Vision API routing | `~/biomimetics/scripts/vision/` |

### 2.2 Medium Priority - Setup & Deployment

| File | Current Location | Purpose | Target Location |
|------|------------------|---------|-----------------|
| `PHASE[2-7]-WORKFLOW.md` | `~/` | Phase workflow documentation | `~/biomimetics/docs/phases/` |
| `phase[2-7]-setup.sh` | `~/` | Phase setup scripts | `~/biomimetics/scripts/setup/` |
| `muninn-*.py` (4 files) | `~/` | MuninnDB services | `~/biomimetics/scripts/muninn/` |
| `muninn-*.sh` (3 files) | `~/` | MuninnDB setup scripts | `~/biomimetics/scripts/setup/` |
| `maintain_mycloud_mount.sh` | `~/` | MyCloud mount watchdog | `~/biomimetics/scripts/` (already exists) |
| `deploy-github-mcp-sse.sh` | `~/` | GitHub MCP deployment | `~/biomimetics/scripts/deploy/` |
| `redeploy-github-mcp.sh` | `~/` | GitHub MCP redeployment | `~/biomimetics/scripts/deploy/` |

### 2.3 Configuration Files

| File | Current Location | Purpose | Action |
|------|------------------|---------|--------|
| `omni_sync_config.json` | `~/` | Omni Sync configuration | Already in `~/biomimetics/config/` |
| `omni_sync_config.example.json` | `~/` | Template configuration | Copy to `~/biomimetics/config/` |
| `notion-approval-db-template.json` | `~/` | Notion database template | Move to `~/biomimetics/notion/` |
| `notion-webhook-worker.js` | `~/` | Old webhook worker | Archive or merge with cloudflare/ |
| `openclaw.json` | `~/` | OpenClaw configuration | Review and archive |
| `package.json` | `~/` | Root package.json | Review necessity |

### 2.4 Documentation

| File | Current Location | Purpose | Target Location |
|------|------------------|---------|-----------------|
| `GITHUB_MCP_SSE_DEPLOYMENT.md` | `~/` | GitHub MCP deployment guide | `~/biomimetics/docs/` |
| `PHASE[2-7]-WORKFLOW.md` | `~/` | Phase workflows | `~/biomimetics/docs/phases/` |

---

## 3. Related Directories to Review

### 3.1 Already Independent Projects

| Directory | Status | Action |
|-----------|--------|--------|
| `~/arca-live-voice/` | ✅ Copied to `~/biomimetics/gemini-live-voice/` | Can archive original |
| `~/Documents/VS Code Projects/ARCA/` | Separate project | Keep separate (ARCA is the AI system being managed) |
| `~/.copaw/` | External tool | Keep separate |
| `~/.serena/` | External tool | Keep separate |
| `~/.muninn/` | External tool | Keep separate |

### 3.2 Configuration Directories (Keep in Place)

| Directory | Purpose | Keep? |
|-----------|---------|-------|
| `~/.azure/` | Azure CLI config | ✅ Yes |
| `~/.cloudflare/` | Cloudflare CLI config | ✅ Yes |
| `~/.docker/` | Docker configuration | ✅ Yes |
| `~/.gemini/` | Gemini CLI config | ✅ Yes |
| `~/.aws/` | AWS CLI config | ✅ Yes |

---

## 4. Notion Documentation Status

### 4.1 Databases Documented (in GEMINI_LIVE_VOICE_PROJECT.md)

| Database | Purpose | Status |
|----------|---------|--------|
| Voice Session Logs | Track voice interactions | 📝 Schema defined, needs creation |
| Voice Tool Registry | Document available tools | 📝 Schema defined, needs creation |
| Voice Interface Tasks | Development tasks | 📝 Schema defined, needs creation |
| Voice API Configuration | Config references | 📝 Schema defined, needs creation |

### 4.2 Existing Notion Integration

| Component | Status | Location |
|-----------|--------|----------|
| Biomimetic OS DB | ✅ Active | `3284d2d9-fc7c-8111-88de-eeaba9c5f845` |
| Life OS Triage DB | ✅ Same as Biomimetic OS | `3284d2d9-fc7c-8111-88de-eeaba9c5f845` |
| Tool Guard DB | ✅ Configured | `3284d2d9-fc7c-8113-bfe-ecca75f4235ece` |
| GitHub→Notion Worker | ✅ Deployed | Cloudflare Worker |

### 4.3 Notion Documentation Gaps

- [ ] Create Voice Session Logs database
- [ ] Create Voice Tool Registry database
- [ ] Create Voice Interface Tasks database
- [ ] Create Voice API Configuration database
- [ ] Document existing database schemas
- [ ] Create Notion integration guide for new users

---

## 5. Development Stage Assessment

### Current Phase: **Phase 7 - Multimodal Live API Integration**

#### Completed Milestones:
- ✅ Phase 2-6: Core infrastructure setup
- ✅ Azure Key Vault integration
- ✅ Cloudflare Worker deployment
- ✅ GitHub webhook integration
- ✅ Notion MCP Server setup
- ✅ Gemini Live Voice API implementation
- ✅ Email sync (ProtonMail 5-account loop)
- ✅ MyCloud watchdog service

#### In Progress:
- 🔄 Project consolidation and documentation
- 🔄 Notion database creation for voice interface
- 🔄 Git repository cleanup (secret scanning issues)

#### Next Steps:
1. Complete file consolidation
2. Create Notion databases from schemas
3. Test Gemini Live Voice end-to-end
4. Deploy voice interface to production
5. Create user documentation

---

## 6. Consolidation Action Plan

### Step 1: Create Target Directories
```bash
mkdir -p ~/biomimetics/{scripts/{mcp,copaw,email,memory,sync,vision,deploy,setup,muninn},docs/phases,notion}
```

### Step 2: Move High Priority Files
```bash
# Core scripts
mv ~/computer-use-mcp.py ~/biomimetics/scripts/mcp/
mv ~/copaw-*.py ~/biomimetics/scripts/copaw/
mv ~/email-ingestion-daemon.py ~/biomimetics/scripts/email/
mv ~/serena-memory-sync.py ~/biomimetics/scripts/memory/
mv ~/obsidian-sync-skill.py ~/biomimetics/scripts/sync/
mv ~/vision-router.py ~/biomimetics/scripts/vision/
```

### Step 3: Move Documentation
```bash
mv ~/PHASE*-WORKFLOW.md ~/biomimetics/docs/phases/
mv ~/GITHUB_MCP_SSE_DEPLOYMENT.md ~/biomimetics/docs/
```

### Step 4: Move Setup Scripts
```bash
mv ~/phase*-setup.sh ~/biomimetics/scripts/setup/
mv ~/muninn-*.sh ~/biomimetics/scripts/setup/
mv ~/muninn-*.py ~/biomimetics/scripts/muninn/
mv ~/deploy-*.sh ~/biomimetics/scripts/deploy/
mv ~/redeploy-*.sh ~/biomimetics/scripts/deploy/
```

### Step 5: Update Documentation References
- Update all paths in documentation
- Create migration guide
- Update README with new structure

### Step 6: Git Cleanup
- Resolve GitHub secret scanning block
- Commit consolidated structure
- Push to repository

---

## 7. Recommendations

### Immediate Actions:
1. **Complete file consolidation** (Steps 1-4 above)
2. **Create Notion databases** from documented schemas
3. **Resolve GitHub push block** (allow secret or rewrite history)
4. **Test all moved scripts** to ensure paths are correct

### Short-term (This Week):
1. Create comprehensive README for each script directory
2. Document all environment variables required
3. Create setup guide for new developers
4. Test end-to-end voice interface workflow

### Long-term (This Month):
1. Create automated testing suite
2. Set up CI/CD pipeline
3. Create user-facing documentation
4. Plan Phase 8 features

---

## 8. File Inventory Summary

### Total Files to Move: **47 files**
- High Priority Scripts: 9
- Setup Scripts: 13
- Documentation: 8
- Configuration: 6
- Related Directories: 11

### Estimated Time: **2-3 hours**

---

**Next Review**: After consolidation complete  
**Owner**: Serena (Biomimetics Orchestrator)  
**Status**: Awaiting approval to proceed with consolidation
