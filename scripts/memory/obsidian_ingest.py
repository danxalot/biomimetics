#!/usr/bin/env python3
"""
Obsidian to MuninnDB Ingestion Pipeline
Parses Obsidian Vault markdown files and pushes contextual memory to GCP MuninnDB.

Strict Invariants:
- Obsidian Vault: ~/Obsidian Vault/
- GCP Gateway: https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator
- Service Account: /Users/danexall/biomimetics/secrets/gcp-service-account
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.error
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# =============================================================================
# Strict Invariants (DO NOT MODIFY)
# =============================================================================

OBSIDIAN_VAULT_PATH = Path("/Volumes/danexall/Obsidian-life")
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
SERVICE_ACCOUNT_PATH = "/Users/danexall/biomimetics/secrets/gcp-service-account"
CREDENTIALS_SERVER_URL = "http://localhost:8089"

# =============================================================================
# Configuration
# =============================================================================

# High-value folders to target for ingestion (based on actual vault structure)
TARGET_FOLDERS = [
    "Medical",
    "Personal",
    "Disability",
    "Health",
    "Context",
    "Memory",
    "Bio",
    "Complaints",
    "Legal",
    "Evidence_Pack",
    "Living",
    "People",
    "Projects",
    "Resources",
]

# File extensions to process
SUPPORTED_EXTENSIONS = [".md", ".markdown"]

# Maximum file size to process (1MB)
MAX_FILE_SIZE = 1024 * 1024

# =============================================================================
# Credential Loading
# =============================================================================


def get_credentials_api_key() -> Optional[str]:
    """Load Credentials API key from secure file."""
    key_file = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
    if not key_file.exists():
        return None
    return key_file.read_text().strip()


def fetch_secret(secret_name: str) -> Optional[str]:
    """Fetch a secret from the Credentials Server."""
    api_key = get_credentials_api_key()
    if not api_key:
        print(f"⚠️  No credentials API key found")
        return None

    req = urllib.request.Request(f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}")
    req.add_header("X-API-Key", api_key)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get("value")
    except Exception as e:
        print(f"⚠️  Failed to fetch {secret_name}: {e}")
        return None


def get_gcp_service_account() -> Optional[Dict]:
    """
    Fetch and decode GCP Service Account key.
    Returns decoded JSON key dict for authentication.
    """
    # Try fetching from Credentials Server first
    secret_value = fetch_secret("gcp-service-account")
    
    if secret_value:
        try:
            # Service account may be stored as base64-encoded JSON
            if secret_value.startswith("ey"):
                # Already JSON string
                return json.loads(secret_value)
            else:
                # Try base64 decode
                decoded = base64.b64decode(secret_value).decode('utf-8')
                return json.loads(decoded)
        except Exception as e:
            print(f"⚠️  Failed to decode service account: {e}")
            return None
    
    # Fallback: Try reading from local file
    sa_path = Path(SERVICE_ACCOUNT_PATH)
    if sa_path.exists():
        try:
            content = sa_path.read_text().strip()
            # Try direct JSON parse first
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Try base64 decode
                decoded = base64.b64decode(content).decode('utf-8')
                return json.loads(decoded)
        except Exception as e:
            print(f"⚠️  Failed to read service account file: {e}")
            return None
    
    print(f"⚠️  GCP Service Account not found")
    return None


# =============================================================================
# Obsidian Vault Parsing
# =============================================================================


def find_target_files(vault_path: Path, target_folders: List[str]) -> List[Path]:
    """
    Find all markdown files in target folders within the vault.
    
    Args:
        vault_path: Path to Obsidian Vault
        target_folders: List of folder names to target
    
    Returns:
        List of Path objects for matching .md files
    """
    target_files = []
    
    if not vault_path.exists():
        print(f"⚠️  Obsidian Vault not found at: {vault_path}")
        return target_files
    
    # Search for target folders
    for folder_name in target_folders:
        folder_path = vault_path / folder_name
        
        if not folder_path.exists():
            print(f"ℹ️  Folder not found: {folder_name}")
            continue
        
        # Walk through folder and subfolders
        for root, dirs, files in os.walk(folder_path):
            # Skip hidden folders and attachments
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                file_path = Path(root) / file
                
                # Check extension
                if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                
                # Check file size
                try:
                    if file_path.stat().st_size > MAX_FILE_SIZE:
                        print(f"⚠️  Skipping large file: {file_path.name} ({file_path.stat().st_size} bytes)")
                        continue
                except Exception:
                    continue
                
                target_files.append(file_path)
    
    return sorted(target_files)


def parse_markdown_file(file_path: Path) -> Dict:
    """
    Parse a markdown file, preserving structure.
    
    Args:
        file_path: Path to .md file
    
    Returns:
        Dict with parsed content and metadata
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"⚠️  Failed to read {file_path.name}: {e}")
        return None
    
    # Extract metadata from frontmatter if present
    metadata = {
        "title": file_path.stem,
        "path": str(file_path.relative_to(OBSIDIAN_VAULT_PATH)),
        "size": len(content),
        "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
        "created": datetime.fromtimestamp(file_path.stat().st_ctime).isoformat(),
    }
    
    # Parse frontmatter (YAML between --- markers)
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            content = parts[2].strip()
            metadata["frontmatter"] = frontmatter
    
    # Extract headers for structure
    headers = []
    for line in content.split('\n'):
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            title = line.strip('#').strip()
            headers.append({"level": level, "title": title})
    
    metadata["headers"] = headers
    metadata["word_count"] = len(content.split())
    
    # Generate content hash for deduplication
    metadata["content_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    # Preserve full markdown content
    metadata["content"] = content
    
    return metadata


def determine_namespace(file_path: Path, target_folders: List[str]) -> str:
    """
    Determine the namespace/category for a file based on its path.
    
    Args:
        file_path: Path to the file
        target_folders: List of target folder names
    
    Returns:
        Namespace string (e.g., "medical", "personal", "disability")
    """
    try:
        relative_path = file_path.relative_to(OBSIDIAN_VAULT_PATH)
        path_parts = [p.lower() for p in relative_path.parts]
        
        # Match against target folders
        for folder in target_folders:
            if folder.lower() in path_parts:
                return folder.lower()
        
        # Default to "personal" for unmatched files
        return "personal"
        
    except Exception:
        return "personal"


# =============================================================================
# GCP MuninnDB Integration
# =============================================================================


def build_payload(file_data: Dict, namespace: str, action: str = "store") -> Dict:
    """
    Build payload for GCP Memory Orchestrator.
    
    Args:
        file_data: Parsed markdown file data
        namespace: Category namespace (medical, personal, etc.)
        action: Action type (store, update, delete)
    
    Returns:
        Dict formatted for memory-orchestrator Cloud Function
    """
    return {
        "action": action,
        "namespace": namespace,
        "source": "obsidian_vault",
        "content": {
            "title": file_data["title"],
            "path": file_data["path"],
            "content": file_data["content"],
            "headers": file_data.get("headers", []),
            "word_count": file_data.get("word_count", 0),
            "content_hash": file_data.get("content_hash", ""),
        },
        "metadata": {
            "modified": file_data.get("modified"),
            "created": file_data.get("created"),
            "frontmatter": file_data.get("frontmatter", ""),
        },
        "context": {
            "disability_context": namespace in ["medical", "disability", "health"],
            "medical_context": namespace in ["medical", "health"],
            "personal_context": namespace in ["personal", "bio"],
        },
    }


def send_to_gcp(payload: Dict, service_account: Dict, dry_run: bool = True) -> Tuple[bool, str]:
    """
    Send payload to GCP Memory Orchestrator.
    
    Args:
        payload: Formatted payload dict
        service_account: GCP service account credentials
        dry_run: If True, don't actually send
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    if dry_run:
        return True, "Dry run - not sent"
    
    if not service_account:
        return False, "No service account credentials"
    
    try:
        # Prepare request with service account authentication
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            GCP_GATEWAY_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                # Add service account token if needed
                # "Authorization": f"Bearer {access_token}"
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            return True, f"Success: {result}"
            
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code}: {e.read().decode()}"
    except Exception as e:
        return False, f"Error: {e}"


# =============================================================================
# Main Ingestion Pipeline
# =============================================================================


def run_ingestion(dry_run: bool = True, verbose: bool = True):
    """
    Run the Obsidian to MuninnDB ingestion pipeline.
    
    Args:
        dry_run: If True, print payloads instead of sending
        verbose: If True, print detailed output
    """
    print("=" * 70)
    print("  Obsidian to MuninnDB Ingestion Pipeline")
    print("=" * 70)
    print()
    
    # Configuration summary
    print(f"📁 Obsidian Vault: {OBSIDIAN_VAULT_PATH}")
    print(f"🌐 GCP Gateway: {GCP_GATEWAY_URL}")
    print(f"🔑 Service Account: {SERVICE_ACCOUNT_PATH}")
    print(f"📂 Target Folders: {', '.join(TARGET_FOLDERS)}")
    print(f"🧪 Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()
    
    # Verify vault exists
    if not OBSIDIAN_VAULT_PATH.exists():
        print(f"❌ Obsidian Vault not found at: {OBSIDIAN_VAULT_PATH}")
        return False
    
    # Get service account credentials
    print("🔑 Fetching GCP Service Account credentials...")
    service_account = get_gcp_service_account()
    if service_account:
        print(f"   ✅ Service account loaded: {service_account.get('client_email', 'unknown')}")
    else:
        print(f"   ⚠️  Service account not available (will skip live send)")
    print()
    
    # Find target files
    print(f"🔍 Scanning vault for target files...")
    target_files = find_target_files(OBSIDIAN_VAULT_PATH, TARGET_FOLDERS)
    print(f"   📄 Found {len(target_files)} markdown files")
    print()
    
    if not target_files:
        print("ℹ️  No files to process")
        return True
    
    # Process files
    stats = {
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "sent": 0,
    }
    
    print("=" * 70)
    print("  Processing Files")
    print("=" * 70)
    print()
    
    for file_path in target_files:
        stats["processed"] += 1
        
        # Parse file
        file_data = parse_markdown_file(file_path)
        if not file_data:
            stats["errors"] += 1
            continue
        
        # Determine namespace
        namespace = determine_namespace(file_path, TARGET_FOLDERS)
        
        # Build payload
        payload = build_payload(file_data, namespace)
        
        # Print file info
        print(f"📄 [{stats['processed']}] {file_data['title']}")
        print(f"   Path: {file_data['path']}")
        print(f"   Namespace: {namespace}")
        print(f"   Words: {file_data['word_count']}")
        print(f"   Headers: {len(file_data['headers'])}")
        print(f"   Hash: {file_data['content_hash']}")
        
        if verbose:
            print()
            print("   📋 Payload Preview:")
            print(f"   {json.dumps(payload, indent=2)[:500]}...")
            print()
        
        # Send to GCP
        success, message = send_to_gcp(payload, service_account, dry_run)
        
        if success:
            if dry_run:
                print(f"   ✅ [DRY RUN] Would send to MuninnDB")
            else:
                print(f"   ✅ Sent to MuninnDB")
                stats["sent"] += 1
        else:
            print(f"   ❌ Failed: {message}")
            stats["errors"] += 1
        
        print()
    
    # Summary
    print("=" * 70)
    print("  Ingestion Summary")
    print("=" * 70)
    print()
    print(f"   Files Processed: {stats['processed']}")
    print(f"   Files Sent: {stats['sent']}")
    print(f"   Errors: {stats['errors']}")
    print()
    
    if dry_run:
        print("⚠️  DRY RUN MODE - No data was sent to GCP")
        print("   Run with --live to send data to MuninnDB")
    else:
        print("✅ Live ingestion complete")
    
    print()
    
    return True


# =============================================================================
# CLI Entry Point
# =============================================================================


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Obsidian to MuninnDB Ingestion Pipeline"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Send data to GCP (default: dry run)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity"
    )
    parser.add_argument(
        "--folders",
        nargs="+",
        help="Override target folders (space-separated)"
    )
    
    args = parser.parse_args()
    
    # Override target folders if specified
    if args.folders:
        TARGET_FOLDERS[:] = args.folders
    
    # Run ingestion
    success = run_ingestion(
        dry_run=not args.live,
        verbose=not args.quiet
    )
    
    sys.exit(0 if success else 1)
