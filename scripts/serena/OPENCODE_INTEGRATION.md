# Serena Code Agent - OpenCode Integration

## Overview

Serena is the Noetic Code Agent - a semantic code analyzer and repair orchestrator that now integrates with OpenCode's free LLM endpoints for task execution.

## Architecture

```
Notion "Ready for Dev" Tasks
       ↓ (poll every 30s)
Serena Notion Poller
       ↓ (claim task)
OpenCode LLM (Minimax/Kimi)
       ↓ (execution plan)
Code Execution (MCP tools)
       ↓ (git commit)
Update Notion to "Review"
       ↓
WhatsApp Notification
```

## OpenCode Model Routing Hierarchy

### Primary Models (Free Tier)

| Model | Provider | Use Case | Context | Cost |
|-------|----------|----------|---------|------|
| `minimax-m2.5-free` | MiniMax | Code generation, planning | 256K tokens | Free |
| `kimi-k2.5-free` | Moonshot | Long context analysis | 256K tokens | Free |
| `nemotron-3-super-free` | NVIDIA | Reasoning, verification | 131K tokens | Free |

### Fallback Chain

```
1. minimax-m2.5-free (primary for code tasks)
   ↓ (if unavailable)
2. kimi-k2.5-free (long context fallback)
   ↓ (if unavailable)
3. nemotron-3-super-free (reasoning fallback)
   ↓ (if all fail)
4. Local Qwen (via Ollama)
```

## Configuration

### Environment Variables

```bash
# Notion Configuration
export NOTION_API_KEY="ntn_xxx"
export NOTION_BIOMIMETIC_DB_ID="3224d2d9fc7c80deb18dd94e22e5bb21"

# OpenCode Configuration
export OPENCODE_API_KEY="your_opencode_key"
export OPENCODE_MODEL="minimax-m2.5-free"  # Primary model
export OPENCODE_BASE_URL="https://opencode.ai/zen/v1"

# WhatsApp Notification (optional)
export CLOUDFLARE_WORKER_URL="https://your-worker.workers.dev"

# Polling Configuration
export SERENA_POLL_INTERVAL="30"  # seconds
export SERENA_TASK_TIMEOUT="30"   # minutes
```

### Model Routing Configuration

Add to `serena_config.py`:

```python
@dataclass
class OpenCodeModelConfig:
    """OpenCode model routing configuration."""
    
    primary_model: str = "minimax-m2.5-free"
    fallback_1: str = "kimi-k2.5-free"
    fallback_2: str = "nemotron-3-super-free"
    base_url: str = "https://opencode.ai/zen/v1"
    api_key: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096
    
    def get_model_chain(self) -> List[str]:
        """Get ordered list of models to try."""
        return [self.primary_model, self.fallback_1, self.fallback_2]
```

## Notion Polling Behavior

### Polling Loop

1. **Query Notion** every 30 seconds for tasks with status "Ready for Dev"
2. **Sort by Priority** (descending) then Timestamp (ascending)
3. **Claim Task** by updating status to "In Progress"
4. **Execute** with OpenCode LLM
5. **Complete** by updating status to "Review"
6. **Notify** via WhatsApp

### Task States

```
Ready for Dev → In Progress → Review → Done
     ↑              ↑           ↑
     │              │           │
  Notion        Serena      Manual
  Created       Claims      Approval
```

### Claim Timeout

- Tasks claimed but not completed within 30 minutes are released
- Status reverts to "Ready for Dev"
- Task ID removed from processed set

## Usage

### Start Serena Poller

```bash
cd /Users/danexall/biomimetics/scripts/serena
python3 serena_notion_poller.py
```

### As LaunchAgent (macOS)

```xml
<!-- ~/Library/LaunchAgents/com.bios.serena-poller.plist -->
<dict>
    <key>Label</key>
    <string>com.bios.serena-poller</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/Users/danexall/biomimetics/scripts/serena/serena_notion_poller.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>NOTION_API_KEY</key>
        <string>ntn_xxx</string>
        <key>OPENCODE_API_KEY</key>
        <string>xxx</string>
    </dict>
</dict>
```

## Project Directories Indexed

Serena has access to:

| Directory | Purpose |
|-----------|---------|
| `~/Documents/VS Code Projects/ARCA` | Main ARCA codebase |
| `~/biomimetics` | BiOS infrastructure |
| `~/.copaw` | CoPaw agent configuration |

### Cloud Infrastructure Access

Serena can interact with:

| Provider | Integration |
|----------|-------------|
| **Vultr** | VM management, GPU instances |
| **Cloudflare** | Workers, Tunnels, DNS |
| **GCP** | Cloud Functions, Memory Gateway |
| **OCI** | Container instances, Key Vault |

## Example Task Flow

### 1. GitHub Issue Created

```markdown
## Add user authentication

Need OAuth2 Google login for the app.

### Requirements
- Google OAuth provider
- Secure token storage
- Logout functionality
```

### 2. Gemini Parses (Cloudflare Worker)

```json
{
  "summary": "Implement OAuth2 Google authentication",
  "technical_requirements": [
    "Add Google OAuth provider",
    "Store tokens in keychain",
    "Implement logout"
  ],
  "priority": "High",
  "complexity": "Medium"
}
```

### 3. Notion Task Created

- **Title**: ✨ [Ready for Dev] Add user authentication
- **Status**: Ready for Dev
- **Priority**: High
- **Complexity**: Medium

### 4. Serena Polls & Claims

```
📋 Processing task: Add user authentication
✅ Claimed task: abc123...
```

### 5. OpenCode Execution Plan

```json
{
  "analysis": "Need to implement OAuth2 flow...",
  "files": [
    {"path": "src/auth/google.py", "action": "create"},
    {"path": "src/auth/oauth.py", "action": "modify"}
  ],
  "steps": ["Install authlib", "Configure Google OAuth", "..."],
  "commit_message": "feat: Add Google OAuth2 authentication"
}
```

### 6. Task Completed

- Notion status → "Review"
- WhatsApp notification sent
- Awaiting manual review

## Cost

| Component | Free Tier | Monthly Cost |
|-----------|-----------|--------------|
| OpenCode (Minimax/Kimi) | Unlimited (free tier) | $0 |
| Notion API | 100K requests/month | $0 |
| Cloudflare Worker | 100K requests/day | $0 |
| **Total** | | **$0** |

## Troubleshooting

### Tasks Not Being Picked Up

1. Check Notion database ID is correct
2. Verify task status is exactly "Ready for Dev"
3. Check poller logs: `tail -f ~/.serena/notion_poller.log`

### OpenCode API Errors

1. Verify API key: `echo $OPENCODE_API_KEY`
2. Test endpoint: `curl -H "Authorization: Bearer $OPENCODE_API_KEY" https://opencode.ai/zen/v1/models`
3. Check model availability in OpenCode dashboard

### WhatsApp Notifications Not Sending

1. Verify Cloudflare Worker URL
2. Check Worker logs: `wrangler tail`
3. Ensure GEMINI_API_KEY is set in Worker secrets

## Related Documentation

- [PROJECT_WIKI.md](../PROJECT_WIKI.md) - Full system documentation
- [GITHUB_GEMINI_NOTION.md](../cloudflare/GITHUB_GEMINI_NOTION.md) - GitHub → Notion flow
- [OpenCode Docs](https://opencode.ai/docs)
