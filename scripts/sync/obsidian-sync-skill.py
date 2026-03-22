#!/usr/bin/env python3
"""
Copaw Skill: Obsidian SMB Sync
Scans SMB-mounted MyCloud Home Obsidian directory for modified .md files
Pushes changes to Cloud Function Gateway for MemU synchronization

Usage: Add to Copaw skills directory or run via cron hourly
"""

import os
import sys
import json
import hashlib
import httpx
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# Configuration
GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
)

# SMB Mount Configuration
OBSIDIAN_VAULT_PATH = os.environ.get(
    "OBSIDIAN_VAULT_PATH",
    "/Volumes/danexall/Obsidian"  # Default SMB mount point (matches mycloud-watchdog mount)
)

# State file for tracking file hashes
STATE_FILE = Path.home() / ".arca" / "obsidian_sync_state.json"

# File patterns to include/exclude
INCLUDE_PATTERNS = ["*.md"]
EXCLUDE_PATTERNS = [
    ".obsidian/*",
    ".git/*",
    "node_modules/*",
    "__pycache__/*",
    "*.md.bak",
    ".DS_Store"
]


class ObsidianSyncState:
    """Track file hashes to detect modifications"""
    
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.file_hashes: Dict[str, str] = {}
        self.load()
    
    def load(self):
        try:
            with open(self.state_file) as f:
                data = json.load(f)
                self.file_hashes = data.get("file_hashes", {})
        except:
            self.file_hashes = {}
    
    def save(self):
        with open(self.state_file, "w") as f:
            json.dump({"file_hashes": self.file_hashes}, f, indent=2)
    
    def get_hash(self, filepath: str) -> str:
        return self.file_hashes.get(filepath, "")
    
    def set_hash(self, filepath: str, hash_value: str):
        self.file_hashes[filepath] = hash_value
        self.save()
    
    def remove_hash(self, filepath: str):
        if filepath in self.file_hashes:
            del self.file_hashes[filepath]
            self.save()


def compute_file_hash(filepath: Path) -> str:
    """Compute MD5 hash of file contents"""
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return ""


def should_include_file(filepath: Path) -> bool:
    """Check if file should be included based on patterns"""
    filepath_str = str(filepath)
    
    # Check exclude patterns
    for pattern in EXCLUDE_PATTERNS:
        if pattern.endswith("/*"):
            # Directory pattern
            dir_pattern = pattern[:-2]
            if dir_pattern in filepath_str:
                return False
        elif pattern.startswith("*."):
            # Extension pattern
            if filepath.suffix == pattern[1:]:
                if pattern == "*.md.bak":
                    return False
        else:
            # Exact pattern
            if pattern in filepath_str:
                return False
    
    # Check include patterns
    for pattern in INCLUDE_PATTERNS:
        if pattern == "*.md" and filepath.suffix == ".md":
            return True
    
    return False


def scan_vault(vault_path: Path) -> List[Path]:
    """Scan Obsidian vault for markdown files"""
    if not vault_path.exists():
        print(f"⚠️  Vault path does not exist: {vault_path}")
        return []
    
    md_files = []
    
    for filepath in vault_path.rglob("*.md"):
        if should_include_file(filepath):
            md_files.append(filepath)
    
    return md_files


def send_to_gateway(content: str, metadata: dict) -> dict:
    """Send markdown content to GCP Cloud Function Gateway"""
    try:
        payload = {
            "operation": "memorize",
            "content": content,
            "metadata": metadata
        }
        
        response = httpx.post(
            GCP_GATEWAY_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60.0  # Longer timeout for large files
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def sync_file(filepath: Path, state: ObsidianSyncState) -> Optional[dict]:
    """Sync a single file if modified"""
    # Compute current hash
    current_hash = compute_file_hash(filepath)
    
    if not current_hash:
        print(f"⚠️  Could not read file: {filepath}")
        return None
    
    # Check if modified
    stored_hash = state.get_hash(str(filepath))
    
    if stored_hash == current_hash:
        return None  # No changes
    
    # Read file content
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"⚠️  Error reading {filepath}: {e}")
        return None
    
    # Calculate relative path
    vault_path = Path(OBSIDIAN_VAULT_PATH)
    try:
        relative_path = filepath.relative_to(vault_path)
    except ValueError:
        relative_path = filepath.name
    
    # Prepare metadata
    metadata = {
        "source": "obsidian",
        "filename": filepath.name,
        "path": str(relative_path),
        "full_path": str(filepath),
        "size": len(content),
        "hash": current_hash,
        "synced_at": datetime.now().isoformat()
    }
    
    # Send to gateway
    result = send_to_gateway(content, metadata)
    
    # Update state
    state.set_hash(str(filepath), current_hash)
    
    return {
        "file": str(relative_path),
        "size": len(content),
        "hash": current_hash,
        "result": result
    }


def cleanup_deleted_files(vault_path: Path, state: ObsidianSyncState):
    """Remove hashes for files that no longer exist"""
    deleted = []
    
    for filepath_str in list(state.file_hashes.keys()):
        if not Path(filepath_str).exists():
            state.remove_hash(filepath_str)
            deleted.append(filepath_str)
    
    if deleted:
        print(f"🗑️  Cleaned up {len(deleted)} deleted file hashes")
    
    return deleted


def main():
    """Main sync function"""
    print("=" * 60)
    print("📝 Obsidian SMB Sync")
    print("=" * 60)
    print(f"Vault Path: {OBSIDIAN_VAULT_PATH}")
    print(f"Gateway: {GCP_GATEWAY_URL}")
    print(f"State File: {STATE_FILE}")
    print("=" * 60)
    
    # Initialize state
    state = ObsidianSyncState(STATE_FILE)
    print(f"Tracking {len(state.file_hashes)} files")
    
    # Check vault exists
    vault_path = Path(OBSIDIAN_VAULT_PATH)
    if not vault_path.exists():
        print(f"❌ Vault not found at {vault_path}")
        print("   Make sure the SMB share is mounted:")
        print(f"   mount_smbfs //user@mycloud/Obsidian {vault_path}")
        return {"error": "Vault not mounted"}
    
    # Scan vault
    print(f"\n🔍 Scanning vault...")
    md_files = scan_vault(vault_path)
    print(f"Found {len(md_files)} markdown files")
    
    # Sync modified files
    print(f"\n🔄 Checking for modifications...")
    synced = []
    errors = []
    
    for filepath in md_files:
        try:
            result = sync_file(filepath, state)
            if result:
                synced.append(result)
                print(f"✅ Synced: {result['file']} ({result['size']} bytes)")
        except Exception as e:
            errors.append({"file": str(filepath), "error": str(e)})
            print(f"❌ Error syncing {filepath}: {e}")
    
    # Cleanup deleted files
    cleanup_deleted_files(vault_path, state)
    
    # Summary
    print(f"\n{'=' * 60}")
    print(f"Sync Complete")
    print(f"{'=' * 60}")
    print(f"Files scanned: {len(md_files)}")
    print(f"Files synced: {len(synced)}")
    print(f"Errors: {len(errors)}")
    print(f"Total tracked: {len(state.file_hashes)}")
    
    return {
        "scanned": len(md_files),
        "synced": len(synced),
        "errors": len(errors),
        "tracked": len(state.file_hashes),
        "synced_files": [s["file"] for s in synced],
        "error_files": [e["file"] for e in errors]
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Obsidian SMB Sync for Copaw")
    parser.add_argument(
        "--vault",
        type=str,
        default=OBSIDIAN_VAULT_PATH,
        help="Path to Obsidian vault"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    
    args = parser.parse_args()
    
    # Override vault path if specified
    if args.vault:
        OBSIDIAN_VAULT_PATH = args.vault
        os.environ["OBSIDIAN_VAULT_PATH"] = args.vault
    
    # Run sync
    result = main()
    
    # Output
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nResult: {json.dumps(result, indent=2)}")
