# ARCA Email Extraction System - Gemini Review Brief

**Generated**: 2026-03-23  
**System**: ARCA Biomimetic OS  
**Domain**: arca-vsa.tech  
**Gemini Relay**: `wss://gemini-relay.arca-vsa.tech/` ✅ **LIVE**  

---

## Executive Summary

The ARCA Email Extraction System is an autonomous email ingestion daemon that polls ProtonMail accounts via Proton Bridge, filters emails using a local LLM (Qwen3.5-2b), and forwards significant communications to the GCP Memory Gateway for Notion triage.

### Current Status
- **3 emails processed** (dan.exall@pm.me IDs: 27863, 27861, 27862)
- **Proton Bridge SSL errors** - Bridge not running on port 1143
- **LLM filter active** - Local Qwen3.5-2b classifies email significance
- **GCP Gateway configured** - Routes to Notion Triage Database

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ARCA EMAIL INGESTION SYSTEM                                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │  ProtonMail     │    │  Gmail (GCP)    │    │  Credentials    │     │
│  │  (Bridge:1143)  │    │  (IMAP:993)     │    │  Server (:8089) │     │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘     │
│           │                      │                      │               │
│           └──────────────────────┼──────────────────────┘               │
│                                  │                                      │
│                          ┌───────▼────────┐                             │
│                          │  Email Daemon  │                             │
│                          │  (Python 3.x)  │                             │
│                          └───────┬────────┘                             │
│                                  │                                      │
│                    ┌─────────────┼─────────────┐                        │
│                    │             │             │                        │
│           ┌────────▼────┐ ┌──────▼──────┐ ┌───▼────────┐               │
│           │  LLM Filter │ │  Body       │ │  State     │               │
│           │  Qwen3.5-2b │ │  Extractor  │ │  Tracker   │               │
│           └────────┬────┘ └─────────────┘ └────────────┘               │
│                    │                                                    │
│           ┌────────▼────────┐                                           │
│           │  GCP Gateway    │                                           │
│           │  memory-        │                                           │
│           │  orchestrator   │                                           │
│           └────────┬────────┘                                           │
│                    │                                                    │
│           ┌────────▼────────┐                                           │
│           │  Notion Triage  │                                           │
│           │  Database       │                                           │
│           └─────────────────┘                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Configured Accounts

| # | Email Address | Protocol | Status |
|---|---------------|----------|--------|
| 1 | dan.exall@pm.me | Proton Bridge (127.0.0.1:1143) | ⚠️ SSL Error |
| 2 | dan@arca-vsa.tech | Proton Bridge | ⚠️ SSL Error |
| 3 | claws@arca-vsa.tech | Proton Bridge | ⚠️ SSL Error |
| 4 | arca@arca-vsa.tech | Proton Bridge | ⚠️ SSL Error |
| 5 | info@arca-vsa.tech | Proton Bridge | ⚠️ SSL Error |

**Note**: All accounts share the same Proton Bridge password (stored in `~/biomimetics/secrets/proton_bridge_password`)

---

## Email Processing Pipeline

### 1. Connection Layer
```python
# Dual-protocol IMAP connection
if protocol == "gmail":
    host = "imap.gmail.com"
    port = 993  # IMAP4_SSL
    mail = imaplib.IMAP4_SSL(host, port)
else:  # Proton
    host = "127.0.0.1"
    port = 1143  # Proton Bridge STARTTLS
    mail = imaplib.IMAP4(host, port)
    mail.starttls(ssl_context=SSL_CONTEXT)
```

### 2. LLM Significance Filter
**Model**: `qwen3.5-2b-instruct`  
**Endpoint**: `http://localhost:11435/v1`

**Prompt**:
```
Is this email a human communication, an actionable task, or an important alert?
Subject: {subject}
Sender: {sender}
Body: {body[:500]}
Reply exactly with YES or NO.
```

**Classification Criteria**:
- ✅ **YES**: Human communication, actionable tasks, important alerts
- ❌ **NO**: Newsletters, automated notifications, spam

### 3. GCP Gateway Payload
```json
{
  "database_id": "3254d2d9fc7c81228daefc564e912546",
  "properties": {
    "Title": {"title": [{"text": {"content": "Email Subject"}}]},
    "Status": {"select": {"name": "Triage"}}
  },
  "children": [{
    "object": "block",
    "type": "paragraph",
    "paragraph": {
      "rich_text": [{
        "type": "text",
        "text": {
          "content": "From: sender@email.com\n\n{body[:500]}\n\n[Obsidian Note](obsidian://open?vault=Obsidian%20Vault&file=Email_Triage/{subject_slug})"
        }
      }]
    }
  }]
}
```

**Gateway URL**: `https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator`

---

## Processing Statistics

### Email State (`~/.arca/email_state.json`)
```json
{
  "processed_ids": [
    "dan.exall@pm.me:27863",
    "dan.exall@pm.me:27861",
    "dan.exall@pm.me:27862"
  ]
}
```

### Recent Sync Logs
```
[2026-03-23 21:36:35] Account dan.exall@pm.me: 0 processed, 0 skipped
[2026-03-23 21:36:35] ERROR: [SSL: WRONG_VERSION_NUMBER] wrong version number
```

**Issue**: Proton Bridge is not running or not listening on port 1143 with STARTTLS.

---

## File Locations

| Component | Path | Purpose |
|-----------|------|---------|
| **Main Daemon** | `scripts/email/email-ingestion-daemon.py` | Email polling & LLM filtering |
| **Setup Script** | `scripts/email/setup_email_daemon.sh` | LaunchAgent configuration |
| **State File** | `~/.arca/email_state.json` | Processed email ID tracking |
| **Logs** | `~/.arca/proton_sync.log` | Sync operation logs |
| **Password** | `~/biomimetics/secrets/proton_bridge_password` | Bridge credentials |
| **LaunchAgent** | `~/Library/LaunchAgents/com.arca.email-ingest.plist` | macOS service |

---

## Known Issues

### 1. Proton Bridge SSL Error
```
[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1028)
```

**Root Cause**: Proton Bridge is either:
- Not running
- Running on a different port
- Not configured for STARTTLS

**Resolution Required**:
1. Open Proton Mail Desktop app
2. Go to Settings → Advanced → Proton Bridge
3. Ensure Bridge is running
4. Verify port is 1143 with STARTTLS

### 2. Credentials Server Integration
The daemon references `CREDENTIALS_URL` and `CREDENTIALS_API_KEY` environment variables but currently loads passwords from local files.

**Migration Needed**:
- Move `proton_bridge_password` to Azure Key Vault
- Update daemon to fetch from Credentials Server at runtime

---

## Gemini Review Questions

### Architecture Review
1. **LLM Filter Efficiency**: Is Qwen3.5-2b appropriate for email classification, or should we use a smaller/faster model?
2. **GCP Gateway Pattern**: Should emails be batched before sending to reduce API calls?
3. **Error Handling**: What's the optimal retry strategy for transient Proton Bridge failures?

### Security Review
4. **Credential Storage**: Are there security concerns with the current password file approach?
5. **Email Content**: Should email bodies be encrypted before transmission to GCP?
6. **Rate Limiting**: What rate limits should be enforced to avoid Gmail/Proton throttling?

### Scalability Review
7. **Volume Handling**: How would this system scale to 1000+ emails/day?
8. **Multi-tenant**: Could this support multiple users with separate Notion databases?
9. **Observability**: What metrics should be exposed for monitoring email processing health?

---

## Next Steps

### Immediate (P0)
- [ ] Fix Proton Bridge connection (verify Bridge is running)
- [ ] Test end-to-end email → Notion flow
- [ ] Verify LLM filter accuracy on sample emails

### Short-term (P1)
- [ ] Migrate credentials to Azure Key Vault
- [ ] Add Gmail account support
- [ ] Implement email attachment handling

### Long-term (P2)
- [ ] Add email reply capability via Notion
- [ ] Implement email threading/conversation tracking
- [ ] Add webhook for real-time email notifications

---

## Contact

**System Owner**: BiOS Team  
**Domain**: arca-vsa.tech  
**Infrastructure**: Vultr VPS + Cloudflare Tunnel + GCP Cloud Functions

---

## Appendix A: Permanent Cloudflare Tunnel

**Tunnel ID**: `61344a83-006c-4df9-a338-16a12570bb36`  
**Account ID**: `aa0a386d0cbd07685723b242e9157e67`  
**Hostname**: `gemini-relay.arca-vsa.tech`  
**Target**: `http://localhost:8765` (Gemini Relay WebSocket)

### DNS Configuration

**Status**: ✅ **Configured**

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | gemini-relay | 61344a83-006c-4df9-a338-16a12570bb36.cfargotunnel.com | Yes |

**DNS Resolution**:
```
gemini-relay.arca-vsa.tech → 172.67.169.221 / 104.21.95.77 (Cloudflare)
```

### VPS Service Status

```bash
# Check tunnel status
ssh root@149.248.32.53 "systemctl status cloudflared-tunnel"

# View logs
ssh root@149.248.32.53 "journalctl -u cloudflared-tunnel -f"
```

---

*This brief was auto-generated for Gemini review. For questions, reference the source files in `/Users/danexall/biomimetics/scripts/email/`*
