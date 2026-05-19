#!/usr/bin/env python3
"""
BiOS Tagged-to-Memory Syncer
Specifically targets documents that have been processed by the semantic tagger
(containing the <!-- LLM_TAGGED --> marker) and synchronizes them to MuninnDB.
"""

import os
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.error
import ssl

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VAULT_ROOT = Path("/Users/danexall/Google Drive/My Drive/Obsidian-life/Personal/Emails/Vault")
STATE_FILE = Path.home() / ".arca" / "tagged_sync_state.json"
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
TAG_MARKER = "<!-- LLM_TAGGED -->"

# Supported extensions
EXTENSIONS = {".md", ".markdown"}

# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def extract_tags(content: str) -> list:
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
    
    # Also find inline hashtags if not in frontmatter
    inline_tags = re.findall(r"(?<!\S)#([a-zA-Z0-9_/]+)", content)
    tags.extend(inline_tags)
    
    return list(set(tags))

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"files": {}}

def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def sync_to_gcp(content: str, filepath: str, tags: list) -> bool:
    payload = {
        "operation": "memorize",
        "content": content,
        "metadata": {
            "source": filepath,
            "tags": tags,
            "synced_at": datetime.now().isoformat(),
            "tagged": True
        }
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        GCP_GATEWAY_URL,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
            return True
    except Exception as e:
        print(f"❌ Failed to sync {filepath}: {e}")
        return False

def main():
    print("="*60)
    print(f"  BiOS Tagged Memory Syncer | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    if not VAULT_ROOT.exists():
        print(f"❌ Error: Vault root not found at {VAULT_ROOT}")
        return

    state = load_state()
    synced_count = 0
    skipped_count = 0
    error_count = 0
    untagged_count = 0

    # Walk the vault recursively
    for root, dirs, files in os.walk(VAULT_ROOT):
        # We allow staging here IF the files are tagged
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
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
            
            # CRITICAL CHECK: Only sync if it has the LLM_TAGGED marker
            if TAG_MARKER not in content:
                untagged_count += 1
                continue
            
            current_hash = compute_sha256(content)
            previous_hash = state["files"].get(rel_path)
            
            if current_hash != previous_hash:
                print(f"🔄 Syncing Tagged: {rel_path}...")
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
    print(f"Summary: {synced_count} synced, {skipped_count} unchanged, {untagged_count} untagged (skipped), {error_count} errors.")
    print("=" * 60)

if __name__ == "__main__":
    main()
