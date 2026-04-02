#!/usr/bin/env python3
"""
Update Zed settings to use Koyeb-hosted GitHub MCP server with SSE.
"""

import json
from pathlib import Path

ZED_SETTINGS_PATH = Path.home() / ".zed" / "settings.json"

# Get GitHub token from local secrets
SECRETS_DIR = Path("/Users/danexall/biomimetics/secrets")
GITHUB_TOKEN_FILE = SECRETS_DIR / "github_models_token"

if GITHUB_TOKEN_FILE.exists():
    GITHUB_TOKEN = GITHUB_TOKEN_FILE.read_text().strip()
    print(f"✅ Loaded GitHub token from local secrets")
else:
    print("❌ GitHub token not found")
    GITHUB_TOKEN = ""

# Zed configuration for Koyeb remote server
zed_config = {
    "mcp": {
        "servers": {
            "notion": {
                "command": "/Users/danexall/.bios/mcp/notion-mcp-wrapper.sh",
                "args": [],
                "env": {}
            },
            "github": {
                "url": "https://github-mcp-server-arca-vsa-3c648978.koyeb.app/sse",
                "type": "sse",
                "headers": {
                    "X-API-Key": GITHUB_TOKEN
                }
            }
        }
    }
}

# Write to Zed settings
ZED_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

with open(ZED_SETTINGS_PATH, "w") as f:
    json.dump(zed_config, f, indent=2)

print(f"✅ Updated Zed settings: {ZED_SETTINGS_PATH}")
print("\nConfiguration:")
print(json.dumps(zed_config, indent=2))
print("\n🔄 Restart Zed to apply changes")
