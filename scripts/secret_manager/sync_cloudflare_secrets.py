#!/usr/bin/env python3
"""
Cloudflare Secrets Sync
Pushes secrets from Azure Key Vault to Cloudflare Workers via wrangler.

Usage:
    python3 sync_cloudflare_secrets.py --dry-run
    python3 sync_cloudflare_secrets.py --secrets github-token,notion-api-key
    python3 sync_cloudflare_secrets.py --all

Environment Variables:
    CREDENTIALS_API_KEY     - API key for credentials server
    CREDENTIALS_SERVER_URL  - Credentials server URL (default: http://127.0.0.1:8089)
"""

import os
import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from azure_secrets_provider import SecretsProvider

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("cf_sync")

CLOUDFLARE_DIR = Path.home() / "biomimetics/cloudflare"
SECRET_NAMES = {
    "github-token": "GITHUB_TOKEN",
    "notion-api-key": "NOTION_API_KEY",
    "gemini-api-key": "GEMINI_API_KEY",
    "gmail-app-password": "GMAIL_APP_PASSWORD",
    "cloudflare-api-key": "CF_API_KEY",
    "cloudflare-account-id": "CF_ACCOUNT_ID",
}


def sync_secret(secret_name: str, env_var: str, dry_run: bool = True) -> bool:
    """Sync a single secret to Cloudflare."""
    provider = SecretsProvider()

    try:
        value = provider.get(secret_name)
        if not value:
            log.error(f"✗ Secret '{secret_name}' not found in Azure Key Vault")
            return False

        if dry_run:
            log.info(f"  [DRY RUN] Would set {env_var}")
            return True

        import subprocess

        result = subprocess.run(
            ["wrangler", "secret", "put", env_var],
            input=value.encode(),
            capture_output=True,
            text=True,
            cwd=CLOUDFLARE_DIR,
        )

        if result.returncode == 0:
            log.info(f"✓ Set {env_var}")
            return True
        else:
            log.error(f"✗ Failed to set {env_var}: {result.stderr}")
            return False

    except Exception as e:
        log.error(f"✗ Error syncing {secret_name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Sync Azure Key Vault secrets to Cloudflare"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be synced"
    )
    parser.add_argument(
        "--secrets", help="Comma-separated list of secret names to sync"
    )
    parser.add_argument("--all", action="store_true", help="Sync all known secrets")
    parser.add_argument("--list", action="store_true", help="List available secrets")
    args = parser.parse_args()

    if args.list:
        print("Available secrets to sync:")
        for name, env in SECRET_NAMES.items():
            print(f"  {name} -> {env}")
        return

    secrets_to_sync = []

    if args.secrets:
        for name in args.secrets.split(","):
            name = name.strip()
            if name in SECRET_NAMES:
                secrets_to_sync.append((name, SECRET_NAMES[name]))
            else:
                log.warning(f"Unknown secret: {name}")

    elif args.all:
        secrets_to_sync = list(SECRET_NAMES.items())

    else:
        log.error("Specify --secrets <names> or --all")
        log.info("Available secrets:")
        for name in SECRET_NAMES:
            log.info(f"  {name}")
        return

    if not secrets_to_sync:
        log.error("No secrets to sync")
        return

    log.info(
        f"{'[DRY RUN] ' if args.dry_run else ''}Syncing {len(secrets_to_sync)} secrets to Cloudflare..."
    )

    success = 0
    failed = 0
    for name, env_var in secrets_to_sync:
        if sync_secret(name, env_var, args.dry_run):
            success += 1
        else:
            failed += 1

    log.info(f"\nResults: {success} synced, {failed} failed")

    if args.dry_run:
        log.info("\nRe-run without --dry-run to actually sync.")


if __name__ == "__main__":
    main()
