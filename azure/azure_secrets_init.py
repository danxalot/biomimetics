#!/usr/bin/env python3
"""
Azure Secrets-Init Integration for Biomimetics

Fetches secrets from Azure Key Vault and injects them into:
- omni_sync_config.json
- Cloudflare Worker environment
- LaunchAgent environment variables
- Notion MCP Server configuration

Usage:
    python azure_secrets_init.py --refresh
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path

# Configuration
BIOMIMETICS_DIR = Path.home() / "biomimetics"
CONFIG_DIR = BIOMIMETICS_DIR / "config"
CLOUDFLARE_DIR = BIOMIMETICS_DIR / "cloudflare"
LAUNCH_AGENTS_DIR = BIOMIMETICS_DIR / "launch_agents"
SECRETS_FILE = BIOMIMETICS_DIR / "secrets" / "azure_secrets.json"

# Azure Key Vault configuration
AZURE_KEY_VAULT_NAME = os.getenv("AZURE_KEY_VAULT_NAME", "arca-mcp-kv-dae")
AZURE_SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID", "")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")

# Secret names mapping (Azure secret name -> local config name)
SECRET_NAMES = {
    "notion-api-key": "NOTION_API_KEY",
    "gmail-app-password": "GMAIL_APP_PASSWORD",
    "proton-bridge-password": "PROTON_BRIDGE_PASSWORD",
    "gcp-credentials-json": "GCP_SERVICE_ACCOUNT",
    "mycloud-password": "MYCLOUD_PASSWORD",
    "gcp-gateway-url": "GCP_GATEWAY_URL",
    "github-webhook-secret": "GITHUB_WEBHOOK_SECRET",
    "copaw-approval-db-id": "COPAW_APPROVAL_DB_ID",
    "gemini-api-key": "GEMINI_API_KEY",
    "github-token": "GITHUB_TOKEN",
}


def authenticate_azure():
    """Authenticate with Azure using environment variables or CLI."""
    try:
        # Try Azure CLI first
        result = subprocess.run(
            ["az", "account", "show"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("✓ Authenticated via Azure CLI")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fall back to service principal
    if all(
        [AZURE_SUBSCRIPTION_ID, AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET]
    ):
        try:
            subprocess.run(
                [
                    "az",
                    "login",
                    "--service-principal",
                    "-u",
                    AZURE_CLIENT_ID,
                    "-p",
                    AZURE_CLIENT_SECRET,
                    "--tenant",
                    AZURE_TENANT_ID,
                ],
                capture_output=True,
                timeout=30,
            )
            print("✓ Authenticated via Service Principal")
            return True
        except Exception as e:
            print(f"✗ Service Principal auth failed: {e}")

    print("✗ Azure authentication failed. Run 'az login' first.")
    return False


def get_secret(secret_name):
    """Fetch a secret from Azure Key Vault."""
    try:
        result = subprocess.run(
            [
                "az",
                "keyvault",
                "secret",
                "show",
                "--vault-name",
                AZURE_KEY_VAULT_NAME,
                "--name",
                secret_name,
                "--query",
                "value",
                "--output",
                "tsv",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"✗ Failed to fetch secret '{secret_name}': {result.stderr}")
            return None
    except Exception as e:
        print(f"✗ Error fetching secret '{secret_name}': {e}")
        return None


def load_secrets():
    """Load all secrets from Azure Key Vault."""
    secrets = {}
    print(f"\nFetching secrets from Azure Key Vault: {AZURE_KEY_VAULT_NAME}")
    print("-" * 50)

    for azure_name, local_name in SECRET_NAMES.items():
        value = get_secret(azure_name)
        if value:
            secrets[local_name] = value
            print(f"✓ {local_name}")
        else:
            print(f"✗ {local_name} (not found)")

    return secrets


def update_omni_sync_config(secrets):
    """Update omni_sync_config.json with secrets from Azure."""
    config_path = CONFIG_DIR / "omni_sync_config.json"
    example_path = CONFIG_DIR / "omni_sync_config.json.example"

    if not example_path.exists():
        print(f"✗ Config template not found: {example_path}")
        return False

    # Load template
    with open(example_path, "r") as f:
        config = json.load(f)

    # Inject secrets
    if "NOTION_API_KEY" in secrets:
        config["NOTION_API_KEY"] = secrets["NOTION_API_KEY"]
    if "GMAIL_APP_PASSWORD" in secrets:
        config["GMAIL_APP_PASSWORD"] = secrets["GMAIL_APP_PASSWORD"]
    if "GCP_GATEWAY_URL" in secrets:
        config["GCP_GATEWAY_URL"] = secrets["GCP_GATEWAY_URL"]
    if "MYCLOUD_PASSWORD" in secrets:
        config["MYCLOUD_PASSWORD"] = [secrets["MYCLOUD_PASSWORD"]]

    # Update Proton passwords
    proton_password = secrets.get("PROTON_BRIDGE_PASSWORD")
    if proton_password:
        for account in config.get("PROTONMAIL_ACCOUNTS", []):
            account["password"] = proton_password

    # Save config
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"✓ Updated: {config_path}")
    return True


def update_cloudflare_env(secrets):
    """Update Cloudflare Worker secrets via wrangler CLI."""
    success = True

    # Update NOTION_API_KEY
    notion_key = secrets.get("NOTION_API_KEY")
    if notion_key:
        try:
            proc = subprocess.Popen(
                ["wrangler", "secret", "put", "NOTION_API_KEY"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=CLOUDFLARE_DIR,
            )
            stdout, stderr = proc.communicate(input=notion_key.encode())

            if proc.returncode == 0:
                print(f"✓ Updated Cloudflare secret: NOTION_API_KEY")
            else:
                print(f"✗ Wrangler error for NOTION_API_KEY: {stderr.decode()}")
                success = False
        except Exception as e:
            print(f"✗ Failed to update Cloudflare secret NOTION_API_KEY: {e}")
            success = False
    else:
        print("✗ Skipping Cloudflare NOTION_API_KEY: not found")
        success = False

    # Update GEMINI_API_KEY
    gemini_key = secrets.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            proc = subprocess.Popen(
                ["wrangler", "secret", "put", "GEMINI_API_KEY"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=CLOUDFLARE_DIR,
            )
            stdout, stderr = proc.communicate(input=gemini_key.encode())

            if proc.returncode == 0:
                print(f"✓ Updated Cloudflare secret: GEMINI_API_KEY")
            else:
                print(f"✗ Wrangler error for GEMINI_API_KEY: {stderr.decode()}")
                success = False
        except Exception as e:
            print(f"✗ Failed to update Cloudflare secret GEMINI_API_KEY: {e}")
            success = False
    else:
        print("✗ Skipping Cloudflare GEMINI_API_KEY: not found")
        success = False

    # Update GITHUB_TOKEN
    github_token = secrets.get("GITHUB_TOKEN")
    if github_token:
        try:
            proc = subprocess.Popen(
                ["wrangler", "secret", "put", "GITHUB_TOKEN"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=CLOUDFLARE_DIR,
            )
            stdout, stderr = proc.communicate(input=github_token.encode())

            if proc.returncode == 0:
                print(f"✓ Updated Cloudflare secret: GITHUB_TOKEN")
            else:
                print(f"✗ Wrangler error for GITHUB_TOKEN: {stderr.decode()}")
                success = False
        except Exception as e:
            print(f"✗ Failed to update Cloudflare secret GITHUB_TOKEN: {e}")
            success = False
    else:
        print("✗ Skipping Cloudflare GITHUB_TOKEN: not found")
        success = False

    return success

    try:
        # Set secret via wrangler
        proc = subprocess.Popen(
            ["wrangler", "secret", "put", "NOTION_API_KEY"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=CLOUDFLARE_DIR,
        )
        stdout, stderr = proc.communicate(input=notion_key.encode())

        if proc.returncode == 0:
            print(f"✓ Updated Cloudflare secret: NOTION_API_KEY")
            return True
        else:
            print(f"✗ Wrangler error: {stderr.decode()}")
            return False
    except Exception as e:
        print(f"✗ Failed to update Cloudflare secret: {e}")
        return False


def update_notion_mcp_config(secrets):
    """Create/update Notion MCP Server configuration."""
    notion_token = secrets.get("NOTION_API_KEY")
    if not notion_token:
        print("✗ Skipping Notion MCP: NOTION_TOKEN not found")
        return False

    mcp_config = {
        "mcpServers": {
            "notion": {
                "command": "/usr/local/bin/npx",
                "args": ["-y", "@notionhq/notion-mcp-server"],
                "env": {"NOTION_TOKEN": notion_token},
            }
        }
    }

    # Save to secrets directory
    mcp_config_path = BIOMIMETICS_DIR / "secrets" / "notion_mcp_config.json"
    os.makedirs(mcp_config_path.parent, exist_ok=True)
    with open(mcp_config_path, "w") as f:
        json.dump(mcp_config, f, indent=2)

    print(f"✓ Created Notion MCP config: {mcp_config_path}")

    # Also update Claude Desktop config if it exists
    claude_config_paths = [
        Path.home()
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude_desktop_config.json",
        Path.home() / ".claude.json",
    ]

    for config_path in claude_config_paths:
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    claude_config = json.load(f)

                claude_config["mcpServers"] = claude_config.get("mcpServers", {})
                claude_config["mcpServers"]["notion"] = mcp_config["mcpServers"][
                    "notion"
                ]

                with open(config_path, "w") as f:
                    json.dump(claude_config, f, indent=2)

                print(f"✓ Updated Claude Desktop config: {config_path}")
            except Exception as e:
                print(f"✗ Failed to update Claude config: {e}")

    return True


def save_local_backup(secrets):
    """Save secrets locally (encrypted in production)."""
    os.makedirs(SECRETS_FILE.parent, exist_ok=True)
    with open(SECRETS_FILE, "w") as f:
        json.dump(secrets, f, indent=2)
    os.chmod(SECRETS_FILE, 0o600)  # Restrict permissions
    print(f"✓ Saved local backup: {SECRETS_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Azure Secrets-Init for Biomimetics")
    parser.add_argument(
        "--refresh", action="store_true", help="Force refresh all secrets"
    )
    parser.add_argument("--vault", type=str, help="Azure Key Vault name")
    args = parser.parse_args()

    print("=" * 60)
    print("Biomimetics Azure Secrets-Init")
    print("=" * 60)

    # Override vault name if provided
    if args.vault:
        global AZURE_KEY_VAULT_NAME
        AZURE_KEY_VAULT_NAME = args.vault

    # Authenticate
    if not authenticate_azure():
        sys.exit(1)

    # Load secrets
    secrets = load_secrets()

    if not secrets:
        print("\n✗ No secrets retrieved. Check Azure Key Vault configuration.")
        sys.exit(1)

    print(f"\nRetrieved {len(secrets)} secrets")
    print("-" * 50)

    # Update configurations
    update_omni_sync_config(secrets)
    update_cloudflare_env(secrets)
    update_notion_mcp_config(secrets)
    save_local_backup(secrets)

    print("\n" + "=" * 60)
    print("✓ Secrets initialization complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Reload LaunchAgents: ./scripts/install_agents.sh")
    print("  2. Deploy Cloudflare: cd cloudflare && npx wrangler deploy")
    print("  3. Restart Claude Desktop to load Notion MCP")


if __name__ == "__main__":
    main()
