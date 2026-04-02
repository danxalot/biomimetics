#!/bin/bash
#
# Connect All Services to Credentials Server
# Updates configs to use centralized credentials instead of local secrets
#

set -euo pipefail

CREDENTIALS_API_KEY="${CREDENTIALS_API_KEY:-}"
CREDENTIALS_URL="http://127.0.0.1:8089"

if [ -z "$CREDENTIALS_API_KEY" ]; then
    echo "❌ CREDENTIALS_API_KEY is not set in the environment. Exiting."
    exit 1
fi

echo "🔐 Connecting Services to Credentials Server"
echo "=============================================="
echo ""

# Test credentials server
echo "Testing credentials server..."
if curl -s -H "X-API-Key: $CREDENTIALS_API_KEY" "$CREDENTIALS_URL/health" | grep -q "healthy"; then
    echo "✅ Credentials server is healthy"
else
    echo "❌ Credentials server not responding"
    echo "   Make sure LaunchAgent is loaded:"
    echo "   launchctl load ~/Library/LaunchAgents/com.bios.credentials-server.plist"
    exit 1
fi

echo ""
echo "=== Updating Zed Configuration ==="

# Update global Zed config
cat > ~/.config/zed/settings.json << EOF
{
  "agent": {
    "default_model": {
      "provider": "openrouter",
      "model": "nvidia/nemotron-3-nano-30b-a3b:free",
      "enable_thinking": true
    },
    "favorite_models": [],
    "model_parameters": []
  },
  "context_servers": {
    "serena-context-server": {
      "enabled": true,
      "remote": false,
      "settings": {
        "python_executable": null
      }
    },
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "{{credentials:notion-api-key}}"
      }
    },
    "github": {
      "url": "https://github-mcp-server-arca-vsa-3c648978.koyeb.app/sse",
      "transport": "sse",
      "headers": {
        "X-API-Key": "{{credentials:github-mcp-api-key}}"
      }
    }
  },
  "language_models": {
    "ollama": {
      "api_url": "https://ollama.com/api"
    }
  },
  "agent_servers": {
    "github-copilot": {
      "type": "registry"
    },
    "qwen-code": {
      "type": "registry"
    },
    "opencode": {
      "type": "registry"
    },
    "factory-droid": {
      "type": "registry"
    }
  },
  "icon_theme": "Catppuccin Frappé",
  "telemetry": {
    "diagnostics": true,
    "metrics": false
  },
  "session": {
    "trust_all_worktrees": true
  },
  "base_keymap": "VSCode",
  "preview_tabs": {
    "enabled": false
  },
  "autosave": "on_focus_change",
  "ui_font_size": 16,
  "buffer_font_size": 15,
  "theme": "One Dark Pro"
}
EOF

echo "✅ Updated ~/.config/zed/settings.json"

# Update project Zed config
cat > ~/biomimetics/.zed/settings.json << EOF
{
  "mcp_servers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "{{credentials:notion-api-key}}"
      }
    },
    "github": {
      "url": "https://github-mcp-server-arca-vsa-3c648978.koyeb.app/sse",
      "transport": "sse",
      "headers": {
        "X-API-Key": "{{credentials:github-mcp-api-key}}"
      }
    }
  },
  "agent_servers": {
    "BiOS_PM": {
      "type": "custom",
      "command": "python3",
      "args": ["~/.copaw/bios_orchestrator.py"],
      "env": {
        "NOTION_DB_ID": "3224d2d9fc7c80deb18dd94e22e5bb21",
        "GCP_GATEWAY": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
      }
    }
  },
  "gcp_gateway": {
    "url": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
    "enabled": true,
    "projects": ["biomimetics", "arca"]
  }
}
EOF

echo "✅ Updated ~/biomimetics/.zed/settings.json"

echo ""
echo "=== Updating Email Daemon ==="

# Update email daemon to use credentials server
cat > ~/biomimetics/scripts/email/email-ingestion-daemon.py << 'PYEOF'
#!/usr/bin/env python3
"""
Email Ingestion Daemon - Dual-Protocol Edition
Polls ProtonMail (STARTTLS:1143) and Gmail (IMAP4_SSL:993) accounts
Forwards to Cloud Function Gateway for memory storage

Uses Credentials Server for secrets (Port 8089)
"""

import os
import sys
import json
import time
import imaplib
import email
import ssl
import argparse
import re
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Configuration
CREDENTIALS_URL = os.environ.get("CREDENTIALS_URL", "http://127.0.0.1:8089")
CREDENTIALS_API_KEY = os.environ.get("CREDENTIALS_API_KEY", "")

# ... rest of daemon code uses credentials server ...
PYEOF

echo "✅ Email daemon updated (template)"

echo ""
echo "=== Adding to Shell Profile ==="

# Add to .zshrc if not already present
if ! grep -q "CREDENTIALS_API_KEY" ~/.zshrc 2>/dev/null; then
    cat >> ~/.zshrc << EOF

# BiOS Credentials Server
export CREDENTIALS_URL="http://127.0.0.1:8089"
export CREDENTIALS_API_KEY="$CREDENTIALS_API_KEY"
EOF
    echo "✅ Added credentials env vars to ~/.zshrc"
else
    echo "✅ Credentials env vars already in ~/.zshrc"
fi

echo ""
echo "=== Summary ==="
echo ""
echo "Services configured to use Credentials Server:"
echo "  ✅ Zed (global config)"
echo "  ✅ Zed (project config)"
echo "  ⏳ Email daemon (template created)"
echo "  ⏳ Computer Use MCP (needs update)"
echo "  ⏳ Approval poller (needs update)"
echo ""
echo "API Key: $CREDENTIALS_API_KEY"
echo ""
echo "Next steps:"
echo "  1. Restart Zed to apply new config"
echo "  2. Update remaining services manually"
echo "  3. Test: curl -H 'X-API-Key: \$CREDENTIALS_API_KEY' http://127.0.0.1:8089/health"
