---
tags: [bios/architecture, bios/security, bios/swarm, source/legacy]
status: active
---

# MCP Integration Guide

This guide covers Model Context Protocol (MCP) integrations across all supported editors and tools.

---

## Quick Start

```bash
# Ensure secrets are initialized
cd ~/biomimetics
python3 azure/azure_secrets_init.py --refresh

# Setup Notion MCP (configures Claude, Qwen automatically)
./scripts/setup_notion_mcp.sh
```

---

## VS Code (GitHub Copilot)

**Config File**: `~/Library/Application Support/Code/User/settings.json`

**Configuration**:
```json
{
  "github.copilot.mcp.servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "ntn_...",
        "NOTION_BIOMIMETIC_OS_DB_ID": "3244d2d9fc7c808b97c3ce78648d77a1",
        "NOTION_LIFE_OS_TRIAGE_DB_ID": "auto-detect",
        "NOTION_TOOL_GUARD_DB_ID": "auto-detect"
      }
    }
  }
}
```

**Database IDs Available**:
| Database | ID |
|----------|-----|
| Biomimetic OS | `3244d2d9fc7c808b97c3ce78648d77a1` |
| Life OS Triage | Auto-detected |
| Tool Guard | Auto-detected |

**Usage in Copilot Chat**:
- "Search my Notion for [topic]"
- "Query the Biomimetic OS database"
- "Create a page in Life OS Triage"

---

## Zed Editor

**Config File**: `~/.config/zed/settings.json`

**Configuration**:
```json
{
  "context_servers": {
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

**Usage**:
- Open Command Palette (`Cmd+Shift+P`)
- Search for "Notion" tools
- Or use in Agent chat: "Search Notion for..."

---

## Claude Desktop

**Config File**: `~/Library/Application Support/Claude/claude_desktop_config.json`

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

**Usage**:
- Restart Claude Desktop
- Ask: "Search my Notion databases"
- Available tools: `search_notion`, `get_page`, `create_page`, `update_page`, `query_database`

---

## Qwen Code

**Config File**: `~/.qwen/settings.json`

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

---

## CoPaw

**Config File**: `~/biomimetics/config/omni_sync_config.json`

**Configuration**:
```json
{
  "MCP_REGISTRY": {
    "notion": {
      "name": "Notion MCP Server",
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "capabilities": [
        "read_pages", "write_pages",
        "read_databases", "write_databases", "search"
      ],
      "databases": {
        "biomimetic_os": "3244d2d9fc7c808b97c3ce78648d77a1",
        "life_os_triage": "auto-detect",
        "tool_guard": "auto-detect"
      }
    }
  }
}
```

---

## Antigravity

**Config File**: `~/biomimetics/.antigravity/settings.json`

**Configuration**:
```json
{
  "mcp_servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "tools": [
        "search_notion", "get_page", "create_page",
        "update_page", "query_database"
      ]
    }
  }
}
```

---

## Troubleshooting

### MCP Server Not Appearing

1. **Restart the application** (VS Code, Zed, Claude, etc.)
2. **Check npx installation**:
   ```bash
   npx -y @notionhq/notion-mcp-server --version
   ```
3. **Verify token**:
   ```bash
   cat ~/biomimetics/secrets/azure_secrets.json | jq '.NOTION_API_KEY'
   ```

### Database Not Found

- Ensure database IDs are correct in config
- Check Notion integration has access to databases
- In Notion: Open database → `...` → `Connect to` → Select integration

### Permission Errors

```bash
# Re-authenticate Azure and refresh secrets
az login
python3 ~/biomimetics/azure/azure_secrets_init.py --refresh

# Re-run MCP setup
./scripts/setup_notion_mcp.sh
```

---

## Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_notion` | Search all Notion content | `query` (string) |
| `get_page` | Retrieve page by ID | `page_id` (string) |
| `create_page` | Create new page | `database_id`, `properties` |
| `update_page` | Modify existing page | `page_id`, `properties` |
| `query_database` | Query database with filters | `database_id`, `filter` |

---

## Security Notes

- All secrets stored in `~/biomimetics/secrets/azure_secrets.json` (mode 600)
- Editor configs with secrets are gitignored
- Use Azure Key Vault for centralized secret management
- Rotate tokens regularly via `az keyvault secret set`
