#!/usr/bin/env python3
"""
BiOS Vault to Memory Syncer
Scans the local documentation vault and synchronizes new or modified markdown files 
to the GCP Memory Orchestrator (MuninnDB/MemU).

Architecture:
1. Scan ~/biomimetics/docs/ recursively for .md files.
2. Compute SHA-256 hash of content.
3. Compare against ~/.arca/vault_sync_state.json.
4. On change/new: POST to GCP_GATEWAY_URL with 'memorize' operation.
5. Update state file.
"""

import os
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VAULT_ROOT = Path("/Users/danexall/biomimetics/docs")
STATE_FILE = Path.home() / ".arca" / "vault_sync_state.json"
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"

# Supported extensions
EXTENSIONS = {".md", ".markdown"}

# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

def compute_sha256(content: str) -> str:
    """Compute SHA-256 hash of string content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def extract_tags(content: str) -> list:
    """Extract tags from YAML frontmatter."""
    tags = []
    # Match YAML frontmatter
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if match:
        frontmatter = match.group(1)
        # Look for tags: [tag1, tag2] or tags: \n - tag1 \n - tag2
        tags_match = re.search(r"tags:\s*\[(.*?)\]", frontmatter)
        if tags_match:
            tags = [t.strip() for t in tags_match.group(1).split(",") if t.strip()]
        else:
            # Try list format
            tags_list_match = re.search(r"tags:\s*\n((?:\s*-\s*\S+\n?)+)", frontmatter)
            if tags_list_match:
                tags = [line.strip().lstrip("-").strip() for line in tags_list_match.group(1).strip().split("\n")]
    
    return tags

def load_state() -> dict:
    """Load sync state from disk."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠ Warning: Could not load state file: {e}")
    return {"files": {}}

def save_state(state: dict):
    """Save sync state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def sync_to_gcp(content: str, filepath: str, tags: list) -> bool:
    """POST payload to GCP Gateway."""
    payload = {
        "operation": "memorize",
        "content": content,
        "metadata": {
            "source": filepath,
            "tags": tags,
            "synced_at": datetime.now().isoformat()
        }
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        GCP_GATEWAY_URL,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        # Note: SSL verification is disabled as per previous pipeline stabilization 
        # (local cert issues). If production security is required, remove context.
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return True
    except Exception as e:
        print(f"❌ Failed to sync {filepath}: {e}")
        return False

def main():
    print("="*60)
    print(f"  BiOS Vault-to-Memory Syncer | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    if not VAULT_ROOT.exists():
        print(f"❌ Error: Vault root not found at {VAULT_ROOT}")
        return

    state = load_state()
    synced_count = 0
    skipped_count = 0
    error_count = 0

    # Walk the vault
    for root, dirs, files in os.walk(VAULT_ROOT):
        # Skip hidden, staging, and archive directories to prevent database pollution
        dirs[:] = [d for d in dirs if not (d.startswith('.') or d == 'staging' or d == '.archive')]
        
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() not in EXTENSIONS:
                continue
            
            rel_path = str(file_path.relative_to(VAULT_ROOT))
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                print(f"⚠ Could not read {rel_path}: {e}")
                error_count += 1
                continue
            
            current_hash = compute_sha256(content)
            previous_hash = state["files"].get(rel_path)
            
            if current_hash != previous_hash:
                print(f"🔄 Syncing: {rel_path}...")
                tags = extract_tags(content)
                if sync_to_gcp(content, rel_path, tags):
                    state["files"][rel_path] = current_hash
                    synced_count += 1
                    print(f"   ✅ Done.")
                else:
                    error_count += 1
            else:
                skipped_count += 1

    # Save final state
    save_state(state)
    
    print("-" * 60)
    print(f"Summary: {synced_count} synced, {skipped_count} unchanged, {error_count} errors.")
    print("=" * 60)

if __name__ == "__main__":
    main()
