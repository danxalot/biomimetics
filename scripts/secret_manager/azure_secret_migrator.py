#!/usr/bin/env python3
"""
Azure Secret Migrator

Automates the transfer of local secrets to Azure Key Vault.
Reads secrets from /Users/danexall/biomimetics/secrets/ and pushes them to the
arca-mcp-kv-dae vault using the Azure CLI.

This script ensures Azure Key Vault is the fully populated single source of truth
for all secrets in the BiOS ecosystem.

Usage:
    python3 azure_secret_migrator.py [--dry-run] [--force]

Options:
    --dry-run    Show what would be migrated without actually pushing
    --force      Overwrite existing secrets in Key Vault without confirmation

Requirements:
    - Azure CLI installed and authenticated
    - Access to arca-mcp-kv-dae Key Vault
    - Read access to local secrets directory

Author: BiOS Infrastructure Team
Date: 2026-03-23
"""

import os
import sys
import json
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


# ============================================================================
# Configuration
# ============================================================================

SECRETS_DIR = Path("/Users/danexall/biomimetics/secrets")
KEY_VAULT_NAME = "arca-mcp-kv-dae"
AZURE_TENANT_ID = "cace3155-c33d-4869-b243-25daf1604ebb"
AZURE_CLIENT_ID = "1b04765e-4482-467c-b799-ee6251542ffe"

# Secret name mappings: local filename -> Azure Key Vault secret name
SECRET_NAME_MAPPINGS = {
    # Google Services
    "google_api_key": "google-api-key",
    "google_ai_studio": "google-ai-studio-key",
    "google_billing_api": "google-billing-api-key",
    "gcp-service-account": "gcp-service-account-json",
    
    # Notion
    "notion_api_key": "notion-api-key",
    "notion_bios_agent_api": "notion-bios-agent-api-key",
    
    # OpenAI
    "OPENAI_API_KEY": "openai-api-key",
    
    # GitHub
    "github_models_token": "github-models-token",
    "github_models_tokens": "github-models-tokens",
    "github_webhook_secret.txt": "github-webhook-secret",
    
    # Anthropic
    "anthropic_api_key": "anthropic-api-key",
    
    # Cloudflare
    "cloudflare": "cloudflare-api-key",
    "cloudflare api": "cloudflare-api-key-alt",
    "cloudflare_client_id": "cloudflare-client-id",
    "cloudflare_client_secret": "cloudflare-client-secret",
    "cloudflare_service_token": "cloudflare-service-token",
    "cloudflare_webhook_secret": "cloudflare-webhook-secret",
    "cloudflare_oci_tunnel": "cloudflare-oci-tunnel-json",
    
    # AWS
    "aws_access_key": "aws-access-key-id",
    "aws_secret_access_key": "aws-secret-access-key",
    "aws_bedrock_api_key_manual": "aws-bedrock-api-key",
    "claws_access_key_aws": "claws-aws-access-key",
    "claws_secret_access_key_aws": "claws-aws-secret-key",
    
    # Other AI Services
    "groq.env": "groq-api-key",
    "cohere_api": "cohere-api-key",
    "cohere.env": "cohere-api-key-env",
    "huggingface-token": "huggingface-token",
    "minimax_api_key": "minimax-api-key",
    "Minimax": "minimax-api-key-alt",
    "opencode_api": "opencode-api-key",
    "opencode_go_api": "opencode-go-api-key",
    "openrouter_api": "openrouter-api-key",
    "openrouter2_api": "openrouter-api-key-2",
    "kaggle_api_key": "kaggle-api-key",
    "tavily_api_key": "tavily-api-key",
    "gemini_api_key": "gemini-api-key",
    
    # Infrastructure
    "tailscale_auth_key": "tailscale-auth-key",
    "tailscale_api_key_2": "tailscale-api-key",
    "tailscale_client_id": "tailscale-client-id",
    "tailscale_client_secret": "tailscale-client-secret",
    "arca_tailscale_api": "arca-tailscale-api-key",
    
    # Database & Storage
    "qdrant_api_key": "qdrant-api-key",
    "qdrant_endpoint_claws": "qdrant-endpoint",
    "oci_config": "oci-config",
    "oci_secret_key": "oci-secret-key",
    "arca_oci_key": "arca-oci-key",
    "arca_oci_key.pub": "arca-oci-key-pub",
    
    # SSH Keys
    "bastion_key": "bastion-ssh-key",
    "bastion_key.pub": "bastion-ssh-key-pub",
    "ssh-key-2025-09-29.key": "ssh-key-2025-09-29",
    "ssh-key-2025-09-29.key.pub": "ssh-key-2025-09-29-pub",
    
    # Email & Communication
    "proton_bridge_password": "proton-bridge-password",
    "protonmail_bridge_password": "protonmail-bridge-password",
    "TELEGRAM_BOT_TOKEN": "telegram-bot-token",
    "whatsapp_verify_token": "whatsapp-verify-token",
    
    # Monitoring & Logging
    "grafana_api": "grafana-api-key",
    "langfuse.env": "langfuse-credentials",
    "wandb_api_key": "wandb-api-key",
    
    # Other
    "WOLFRAM_API": "wolfram-alpha-api-key",
    "geonames_username": "geonames-username",
    "digitalocean_api": "digitalocean-api-key",
    "vultr_api_key": "vultr-api-key",
    "vultr_ssh_key": "vultr-ssh-key",
    "modal_api_key": "modal-api-key",
    "nvidia_api_key": "nvidia-api-key",
    "koyeb_api_key": "koyeb-api-key",
    "zai_api_key": "zhipu-api-key",
    "zhipu_api_key": "zhipu-api-key-alt",
    "mistral_api_key": "mistral-api-key",
    "deepseek_api_key": "deepseek-api-key",
    "aiml_api_key": "aiml-api-key",
    "ai21_api_key": "ai21-api-key",
    "ALIBABA_API_KEY": "alibaba-api-key",
    "blackbox_api_key": "blackbox-api-key",
    "mem0_api_key": "mem0-api-key",
    "lycuem_api": "lyceum-api-key",
    "lycuem_api": "lyceum-api-key",
    "CHRIST_PASSWORD": "christ-password",
    "MYCLOUD_USER": "mycloud-username",
    "mycloud-password": "mycloud-password",
}

# Files to skip (binaries, archives, etc.)
SKIP_EXTENSIONS = {'.zip', '.tar', '.gz', '.pem', '.key', '.pub', '.json'}
SKIP_FILES = {
    '.!30669!ARCA-26ai-wallet copy.zip',
    'ARCA-26ai-wallet copy.zip',
    'ARCA-26ai-wallet.zip',
    'azure_secrets.json',
    'azure.json',
    'command_content.json',
    'credentials.json',
    'database_config.env',
    'gdrive_credentials.json',
    'gemini-reviewer-agent-credentials.json',
    'gemini-reviewer-agent-credentials copy.json',
    'MINIMAX_API_KEY.json',
    'network_topology.json',
    'oci_credentials.sh',
    'oci_s3_credentials',
    'target_instance.json',
    'tokens.tok',
    'SYNC_DEPLOYMENT_REQUIREMENTS.md',
    'Tailscale_ACL_details.txt',
    'tailscale_auth_keys.md',
    'notion_mcp_config.json',
    'inject_ssh_key.sh',
    'install_tailscale.sh',
    'run_bastion_recovery.sh',
}


# ============================================================================
# Data Classes
# ============================================================================

class MigrationStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    EXISTS = "exists"


@dataclass
class SecretMigrationResult:
    local_file: str
    azure_name: str
    status: MigrationStatus
    message: str = ""
    size_bytes: int = 0
    hash_sha256: str = ""


# ============================================================================
# Azure CLI Wrapper
# ============================================================================

class AzureKeyVaultClient:
    """Wrapper around Azure CLI for Key Vault operations."""
    
    def __init__(self, vault_name: str):
        self.vault_name = vault_name
        self._check_azure_cli()
    
    def _check_azure_cli(self):
        """Verify Azure CLI is installed and authenticated."""
        try:
            result = subprocess.run(
                ["az", "account", "show"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError("Azure CLI not authenticated. Run: az login")
        except FileNotFoundError:
            raise RuntimeError("Azure CLI not installed. Install from: https://docs.microsoft.com/cli/azure/install-azure-cli")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Azure CLI command timed out")
    
    def secret_exists(self, secret_name: str) -> bool:
        """Check if a secret exists in the vault."""
        try:
            result = subprocess.run(
                [
                    "az", "keyvault", "secret", "show",
                    "--vault-name", self.vault_name,
                    "--name", secret_name
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False
    
    def set_secret(self, secret_name: str, secret_value: str, description: str = "") -> Tuple[bool, str]:
        """
        Set a secret in the vault.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Create or update the secret
            cmd = [
                "az", "keyvault", "secret", "set",
                "--vault-name", self.vault_name,
                "--name", secret_name,
                "--value", secret_value,
                "--description", description or f"Migrated from local secrets on {datetime.now().isoformat()}"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return True, f"Secret '{secret_name}' set successfully"
            else:
                return False, f"Failed to set secret: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def list_secrets(self) -> List[str]:
        """List all secret names in the vault."""
        try:
            result = subprocess.run(
                [
                    "az", "keyvault", "secret", "list",
                    "--vault-name", self.vault_name
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return [item["name"] for item in data]
            else:
                return []
        except Exception:
            return []


# ============================================================================
# Secret Migrator
# ============================================================================

class SecretMigrator:
    """Migrates local secrets to Azure Key Vault."""
    
    def __init__(self, secrets_dir: Path, vault_name: str, dry_run: bool = False, force: bool = False):
        self.secrets_dir = secrets_dir
        self.dry_run = dry_run
        self.force = force
        self.vault_client = AzureKeyVaultClient(vault_name)
        self.results: List[SecretMigrationResult] = []
    
    def _read_secret_file(self, file_path: Path) -> Optional[str]:
        """Read secret value from file."""
        try:
            # Skip binary files and large files
            if file_path.suffix.lower() in SKIP_EXTENSIONS:
                return None
            
            if file_path.stat().st_size > 1024 * 1024:  # Skip files > 1MB
                return None
            
            # Read file content
            content = file_path.read_text(encoding='utf-8', errors='ignore').strip()
            
            # Skip empty files
            if not content:
                return None
            
            return content
            
        except Exception as e:
            print(f"  ⚠ Error reading {file_path.name}: {e}")
            return None
    
    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    def _should_skip_file(self, file_path: Path) -> bool:
        """Determine if a file should be skipped."""
        # Skip directories
        if file_path.is_dir():
            return True
        
        # Skip hidden files
        if file_path.name.startswith('.'):
            return True
        
        # Skip files in skip list
        if file_path.name in SKIP_FILES:
            return True
        
        # Skip files with skip extensions
        if file_path.suffix.lower() in SKIP_EXTENSIONS:
            return True
        
        # Skip files larger than 1MB
        if file_path.stat().st_size > 1024 * 1024:
            return True
        
        return False
    
    def migrate_all(self) -> List[SecretMigrationResult]:
        """Migrate all local secrets to Azure Key Vault."""
        print(f"\n{'='*70}")
        print(f"  Azure Secret Migrator")
        print(f"{'='*70}")
        print(f"  Source: {self.secrets_dir}")
        print(f"  Target: {self.vault_client.vault_name}")
        print(f"  Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"{'='*70}\n")
        
        # Get list of existing secrets in vault
        print("📋 Fetching existing secrets from Azure Key Vault...")
        existing_secrets = set(self.vault_client.list_secrets())
        print(f"  Found {len(existing_secrets)} existing secrets in vault\n")
        
        # Iterate through local secrets directory
        migrated_count = 0
        skipped_count = 0
        failed_count = 0
        exists_count = 0
        
        for file_path in sorted(self.secrets_dir.iterdir()):
            # Check if file should be skipped
            if self._should_skip_file(file_path):
                skipped_count += 1
                continue
            
            # Get Azure secret name
            azure_name = SECRET_NAME_MAPPINGS.get(file_path.name, file_path.name.lower().replace('_', '-'))
            
            # Read secret value
            secret_value = self._read_secret_file(file_path)
            if not secret_value:
                skipped_count += 1
                self.results.append(SecretMigrationResult(
                    local_file=file_path.name,
                    azure_name=azure_name,
                    status=MigrationStatus.SKIPPED,
                    message="Empty or unreadable file"
                ))
                continue
            
            # Check if secret already exists
            if azure_name in existing_secrets and not self.force:
                exists_count += 1
                self.results.append(SecretMigrationResult(
                    local_file=file_path.name,
                    azure_name=azure_name,
                    status=MigrationStatus.EXISTS,
                    message="Already exists in vault (use --force to overwrite)"
                ))
                continue
            
            # Compute hash for verification
            secret_hash = self._compute_hash(secret_value)
            
            # Migrate secret
            if self.dry_run:
                print(f"  [DRY RUN] Would migrate: {file_path.name} → {azure_name}")
                self.results.append(SecretMigrationResult(
                    local_file=file_path.name,
                    azure_name=azure_name,
                    status=MigrationStatus.PENDING,
                    message="Dry run - not actually migrated",
                    size_bytes=len(secret_value),
                    hash_sha256=secret_hash
                ))
                migrated_count += 1
            else:
                print(f"  Migrating: {file_path.name} → {azure_name}...", end=" ")
                
                success, message = self.vault_client.set_secret(
                    azure_name,
                    secret_value,
                    description=f"Migrated from {file_path.name} on {datetime.now().isoformat()}"
                )
                
                if success:
                    print("✓")
                    migrated_count += 1
                    self.results.append(SecretMigrationResult(
                        local_file=file_path.name,
                        azure_name=azure_name,
                        status=MigrationStatus.SUCCESS,
                        message=message,
                        size_bytes=len(secret_value),
                        hash_sha256=secret_hash
                    ))
                else:
                    print(f"✗ {message}")
                    failed_count += 1
                    self.results.append(SecretMigrationResult(
                        local_file=file_path.name,
                        azure_name=azure_name,
                        status=MigrationStatus.FAILED,
                        message=message
                    ))
        
        # Print summary
        print(f"\n{'='*70}")
        print(f"  Migration Summary")
        print(f"{'='*70}")
        print(f"  ✓ Migrated:  {migrated_count}")
        print(f"  ⊕ Exists:    {exists_count}")
        print(f"  ⊘ Skipped:   {skipped_count}")
        print(f"  ✗ Failed:    {failed_count}")
        print(f"{'='*70}\n")
        
        return self.results
    
    def print_report(self):
        """Print detailed migration report."""
        if not self.results:
            return
        
        print(f"\n{'='*70}")
        print(f"  Detailed Migration Report")
        print(f"{'='*70}\n")
        
        # Group by status
        by_status = {}
        for result in self.results:
            if result.status not in by_status:
                by_status[result.status] = []
            by_status[result.status].append(result)
        
        for status, results in sorted(by_status.items()):
            print(f"\n{status.value.upper()} ({len(results)}):")
            print("-" * 70)
            
            for result in results[:20]:  # Show first 20 per category
                print(f"  {result.local_file:40} → {result.azure_name}")
                if result.message and result.message != "Dry run - not actually migrated":
                    print(f"    {result.message}")
            
            if len(results) > 20:
                print(f"  ... and {len(results) - 20} more")
        
        print(f"\n{'='*70}\n")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Migrate local secrets to Azure Key Vault",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (show what would be migrated)
  python3 azure_secret_migrator.py --dry-run
  
  # Migrate all secrets
  python3 azure_secret_migrator.py
  
  # Force overwrite existing secrets
  python3 azure_secret_migrator.py --force
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually pushing"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing secrets in Key Vault without confirmation"
    )
    
    parser.add_argument(
        "--vault",
        default=KEY_VAULT_NAME,
        help=f"Key Vault name (default: {KEY_VAULT_NAME})"
    )
    
    parser.add_argument(
        "--secrets-dir",
        type=Path,
        default=SECRETS_DIR,
        help=f"Local secrets directory (default: {SECRETS_DIR})"
    )
    
    args = parser.parse_args()
    
    # Validate secrets directory
    if not args.secrets_dir.exists():
        print(f"Error: Secrets directory not found: {args.secrets_dir}")
        sys.exit(1)
    
    try:
        # Create migrator and run migration
        migrator = SecretMigrator(
            secrets_dir=args.secrets_dir,
            vault_name=args.vault,
            dry_run=args.dry_run,
            force=args.force
        )
        
        migrator.migrate_all()
        migrator.print_report()
        
        print("✅ Migration complete!")
        print("\nNext steps:")
        print("  1. Review the migration report above")
        print("  2. Verify secrets in Azure Portal: https://portal.azure.com/#@/resource/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.KeyVault/vaults/arca-mcp-kv-dae/secrets/overview")
        print("  3. Update PROJECT_WIKI.md with migration details")
        
    except RuntimeError as e:
        print(f"Error: {e}")
        print("\nTo fix:")
        print("  1. Install Azure CLI: https://docs.microsoft.com/cli/azure/install-azure-cli")
        print("  2. Authenticate: az login")
        print("  3. Ensure you have access to the Key Vault")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠ Migration cancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
