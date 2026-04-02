#!/usr/bin/env python3
"""
IDE MCP Configuration Synchronizer
===================================

Programmatically configures VS Code, Zed, and Antigravity to use Notion and GitHub MCP servers,
dynamically pulling API keys from the local Credentials Server (port 8089).

Instead of hardcoding tokens, this script generates wrapper scripts that fetch secrets
from the Credentials Server at runtime.

Usage:
    python3 sync_ide_mcp.py

Credentials Server Endpoints:
    GET http://localhost:8089/secrets/notion-api-key
    GET http://localhost:8089/secrets/github-token

Output Files:
    - ~/.bios/mcp/notion-mcp-wrapper.sh
    - ~/.bios/mcp/github-mcp-wrapper.sh
    - ~/.vscode/mcp.json
    - ~/.zed/settings.json
    - ~/.antigravity/mcp_config.json
"""

import os
import sys
import json
import shutil
import httpx
from pathlib import Path
from typing import Optional, Dict

# Configuration
CREDENTIALS_SERVER_URL = os.getenv("CREDENTIALS_SERVER_URL", "http://localhost:8089")
CREDENTIALS_API_KEY = os.getenv("CREDENTIALS_API_KEY", "4Kib2uPPgTmBmlXoYi9tDmgJH-t-1nZBIXgBMPf7ljQ")

# Output directories
BIOS_MCP_DIR = Path.home() / ".bios" / "mcp"
VS_CODE_DIR = Path.home() / ".vscode"
ZED_DIR = Path.home() / ".zed"
ANTIGRAVITY_DIR = Path.home() / ".antigravity"

# MCP Server configurations
MCP_SERVERS = {
    "notion": {
        "name": "Notion MCP Server",
        "package": "@notionhq/notion-mcp-server",
        "secret_name": "notion-api-key",
        "env_var": "NOTION_TOKEN"
    },
    "github": {
        "name": "GitHub MCP Server",
        "package": "@modelcontextprotocol/server-github",
        "secret_name": "github-token",
        "env_var": "GITHUB_TOKEN"
    }
}


def fetch_secret(secret_name: str) -> Optional[str]:
    """Fetch a secret from the Credentials Server."""
    try:
        response = httpx.get(
            f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}",
            headers={"X-API-Key": CREDENTIALS_API_KEY},
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()["value"].strip()
        else:
            print(f"⚠️  Failed to fetch {secret_name}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"⚠️  Error fetching {secret_name}: {e}")
        return None


def create_wrapper_script(server_name: str, server_config: Dict) -> Path:
    """
    Create a bash wrapper script that fetches secrets from Credentials Server at runtime.
    
    The wrapper:
    1. Fetches the secret from Credentials Server
    2. Sets the environment variable
    3. Executes the MCP server via npx
    """
    wrapper_path = BIOS_MCP_DIR / f"{server_name}-mcp-wrapper.sh"
    
    secret_name = server_config["secret_name"]
    env_var = server_config["env_var"]
    package = server_config["package"]
    
    wrapper_content = f'''#!/bin/bash
#
# MCP Server Wrapper: {server_config["name"]}
# 
# This wrapper fetches the API key from the Credentials Server at runtime
# and injects it as an environment variable before starting the MCP server.
#
# Credentials Server: {CREDENTIALS_SERVER_URL}
# Secret: {secret_name}
# Environment Variable: {env_var}
#

set -euo pipefail

# Configuration
CREDENTIALS_SERVER_URL="{CREDENTIALS_SERVER_URL}"
CREDENTIALS_API_KEY="{CREDENTIALS_API_KEY}"
SECRET_NAME="{secret_name}"
ENV_VAR="{env_var}"
MCP_PACKAGE="{package}"

# Fetch secret from Credentials Server
fetch_secret() {{
    local response
    response=$(curl -s -w "\\n%{{http_code}}" -X GET "$CREDENTIALS_SERVER_URL/secrets/$SECRET_NAME" \\
        -H "X-API-Key: $CREDENTIALS_API_KEY")
    
    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('value', '').strip())"
    else
        echo "ERROR: Failed to fetch secret (HTTP $http_code)" >&2
        exit 1
    fi
}}

# Check if curl is available
if ! command -v curl &> /dev/null; then
    echo "ERROR: curl is required but not installed" >&2
    exit 1
fi

# Fetch the API key
export $ENV_VAR=$(fetch_secret)

if [ -z "${{!ENV_VAR}}" ]; then
    echo "ERROR: Could not fetch API key from Credentials Server" >&2
    exit 1
fi

# Start MCP server
exec npx -y "$MCP_PACKAGE" "$@"
'''
    
    # Write wrapper script
    wrapper_path.write_text(wrapper_content)
    wrapper_path.chmod(0o755)
    
    return wrapper_path


def generate_vscode_config(wrapper_paths: Dict[str, Path]) -> Path:
    """Generate VS Code mcp.json configuration."""
    config_path = VS_CODE_DIR / "mcp.json"
    
    config = {
        "servers": {}
    }
    
    for server_name, wrapper_path in wrapper_paths.items():
        config["servers"][server_name] = {
            "type": "stdio",
            "command": str(wrapper_path),
            "args": []
        }
    
    # Ensure directory exists
    VS_CODE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write configuration
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    return config_path


def generate_zed_config(wrapper_paths: Dict[str, Path]) -> Path:
    """Generate Zed settings.json configuration."""
    config_path = ZED_DIR / "settings.json"
    
    # Load existing config or create new
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        config = {}
    
    # Configure MCP servers
    if "mcp" not in config:
        config["mcp"] = {"servers": {}}
    
    for server_name, wrapper_path in wrapper_paths.items():
        config["mcp"]["servers"][server_name] = {
            "command": str(wrapper_path),
            "args": [],
            "env": {}
        }
    
    # Ensure directory exists
    ZED_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write configuration
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    return config_path


def generate_antigravity_config(wrapper_paths: Dict[str, Path]) -> Path:
    """Generate Antigravity mcp_config.json configuration."""
    config_path = ANTIGRAVITY_DIR / "mcp_config.json"
    
    config = {
        "mcpServers": {}
    }
    
    for server_name, wrapper_path in wrapper_paths.items():
        config["mcpServers"][server_name] = {
            "command": str(wrapper_path),
            "args": [],
            "env": {}
        }
    
    # Ensure directory exists
    ANTIGRAVITY_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write configuration
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    return config_path


def check_credentials_server() -> bool:
    """Check if Credentials Server is running and accessible."""
    try:
        response = httpx.get(f"{CREDENTIALS_SERVER_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ Credentials Server is running: {CREDENTIALS_SERVER_URL}")
            return True
        else:
            print(f"⚠️  Credentials Server returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Credentials Server not accessible: {e}")
        print(f"   Expected at: {CREDENTIALS_SERVER_URL}")
        print(f"   Start with: python3 -m scripts.secret_manager.credentials_server")
        return False


def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("  IDE MCP Configuration Synchronizer")
    print("  Credentials Server Integration")
    print("=" * 70 + "\n")
    
    # Step 1: Check Credentials Server
    print("📋 Step 1: Checking Credentials Server...")
    if not check_credentials_server():
        print("\n❌ Credentials Server is not running. Please start it first:")
        print("   python3 -m scripts.secret_manager.credentials_server")
        sys.exit(1)
    
    # Step 2: Create wrapper scripts directory
    print("\n📋 Step 2: Creating wrapper scripts directory...")
    BIOS_MCP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"   Created: {BIOS_MCP_DIR}")
    
    # Step 3: Create wrapper scripts
    print("\n📋 Step 3: Creating MCP wrapper scripts...")
    wrapper_paths = {}
    
    for server_name, server_config in MCP_SERVERS.items():
        print(f"   Creating {server_name} wrapper...")
        wrapper_path = create_wrapper_script(server_name, server_config)
        wrapper_paths[server_name] = wrapper_path
        print(f"   ✅ {wrapper_path}")
    
    # Step 4: Generate IDE configurations
    print("\n📋 Step 4: Generating IDE configurations...")
    
    # VS Code
    vscode_path = generate_vscode_config(wrapper_paths)
    print(f"   ✅ VS Code: {vscode_path}")
    
    # Zed
    zed_path = generate_zed_config(wrapper_paths)
    print(f"   ✅ Zed: {zed_path}")
    
    # Antigravity
    antigravity_path = generate_antigravity_config(wrapper_paths)
    print(f"   ✅ Antigravity: {antigravity_path}")
    
    # Step 5: Verify secrets are available
    print("\n📋 Step 5: Verifying secrets availability...")
    
    for server_name, server_config in MCP_SERVERS.items():
        secret = fetch_secret(server_config["secret_name"])
        if secret:
            masked = secret[:4] + "..." + secret[-4:] if len(secret) > 8 else "***"
            print(f"   ✅ {server_config['secret_name']}: {masked}")
        else:
            print(f"   ⚠️  {server_config['secret_name']}: NOT FOUND")
            print(f"      Add to Azure Key Vault: az keyvault secret set --vault-name arca-mcp-kv-dae --name {server_config['secret_name']} --value <value>")
    
    # Summary
    print("\n" + "=" * 70)
    print("  ✅ IDE Configuration Complete!")
    print("=" * 70)
    print("\n📝 Summary:")
    print(f"   Wrapper scripts: {BIOS_MCP_DIR}")
    print(f"   VS Code config: {vscode_path}")
    print(f"   Zed config: {zed_path}")
    print(f"   Antigravity config: {antigravity_path}")
    
    print("\n🔄 Next Steps:")
    print("   1. Restart VS Code / Zed / Antigravity to load new MCP configurations")
    print("   2. Verify MCP servers appear in your IDE's MCP server list")
    print("   3. Test Notion/GitHub MCP commands")
    
    print("\n🔧 Manual Configuration (if needed):")
    print("   VS Code: Copy ~/.vscode/mcp.json to your workspace .vscode/ folder")
    print("   Zed: Settings are in ~/.zed/settings.json")
    print("   Antigravity: Config is in ~/.antigravity/mcp_config.json")
    
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
