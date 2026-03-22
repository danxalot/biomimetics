#!/usr/bin/env python3
"""
Copaw Skill: Serena Memory Sync
Monitors ~/.serena/memories/ directory for generated code specs
and syncs them to MemU via Cloud Function Gateway.
Uses OpenCode (Nemotron/MiniMax) for heavy reasoning on memory content.
"""

import os
import sys
import json
import time
import hashlib
import httpx
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# OpenCode integration
from openai import OpenAI

OPENCODE_TOKEN_PATH = "/Users/danexall/biomimetics/secrets/opencode_api"
OPENCODE_BASE_URL = "https://opencode.ai/zen/v1"
OPENCODE_MODELS = {
    "nemotron": "nemotron-3-super-free",
    "minimax": "minimax-m2.5-free",
}

# Configuration
SERENA_MEMORIES_DIR = Path.home() / ".serena" / "memories"
GCP_GATEWAY_URL = os.environ.get(
    "GCP_GATEWAY_URL",
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
)
STATE_FILE = Path.home() / ".arca" / "serena_sync_state.json"
SYNC_INTERVAL = int(os.environ.get("SERENA_SYNC_INTERVAL", "300"))  # 5 minutes
ARCA_MEMORIES_DIR = Path(
    "/Users/danexall/Documents/VS Code Projects/ARCA/.serena/memories"
)


def process_with_opencode(content: str, filename: str) -> Optional[str]:
    """Route memory content through OpenCode for enrichment/summarization."""
    try:
        with open(OPENCODE_TOKEN_PATH, "r") as f:
            api_key = f.read().strip()
    except FileNotFoundError:
        print(f"⚠️  OpenCode token not found, skipping enrichment")
        return None

    client = OpenAI(base_url=OPENCODE_BASE_URL, api_key=api_key)

    system_prompt = (
        "You are a memory enrichment engine. Given a raw code specification or memory entry, "
        "produce a concise structured summary with: 1) Key concepts, 2) Actionable items, "
        "3) Connections to other systems. Keep it under 200 words. Output plain text, no markdown."
    )

    try:
        response = client.chat.completions.create(
            model=OPENCODE_MODELS["nemotron"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"File: {filename}\n\n{content}"},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"⚠️  OpenCode enrichment failed: {e}")
        return None


class SerenaSyncState:
    """Track synced file hashes"""

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


def compute_file_hash(filepath: Path) -> str:
    """Compute MD5 hash of file contents"""
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return ""


def send_to_gateway(content: str, metadata: dict) -> dict:
    """Send content to GCP Cloud Function Gateway"""
    try:
        payload = {"operation": "memorize", "content": content, "metadata": metadata}

        response = httpx.post(
            GCP_GATEWAY_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def scan_serena_memories() -> List[Path]:
    """Scan Serena memories directories (global + ARCA project) for markdown files"""
    md_files = []
    for directory in [SERENA_MEMORIES_DIR, ARCA_MEMORIES_DIR]:
        if directory.exists():
            for filepath in directory.rglob("*.md"):
                md_files.append(filepath)
        else:
            print(f"⚠️  Memories directory does not exist: {directory}")
    return md_files


def sync_file(filepath: Path, state: SerenaSyncState) -> Optional[dict]:
    """Sync a single Serena memory file if modified"""
    current_hash = compute_file_hash(filepath)

    if not current_hash:
        return None

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
    try:
        relative_path = filepath.relative_to(SERENA_MEMORIES_DIR)
    except ValueError:
        relative_path = filepath.name

    # Prepare metadata
    metadata = {
        "source": "serena",
        "filename": filepath.name,
        "path": str(relative_path),
        "full_path": str(filepath),
        "size": len(content),
        "hash": current_hash,
        "synced_at": datetime.now().isoformat(),
        "type": "code_spec",
    }

    # Format content for memory storage
    memory_content = (
        f"# Serena Code Specification\n\nFile: {relative_path}\n\n{content}"
    )

    # Enrich via OpenCode before sending to gateway
    enrichment = process_with_opencode(content, filepath.name)
    if enrichment:
        memory_content += f"\n\n## OpenCode Analysis\n\n{enrichment}"
        metadata["opencode_enriched"] = True
    else:
        metadata["opencode_enriched"] = False

    # Send to gateway
    result = send_to_gateway(memory_content, metadata)

    # Update state
    state.set_hash(str(filepath), current_hash)

    return {
        "file": str(relative_path),
        "size": len(content),
        "hash": current_hash,
        "result": result,
    }


def main():
    """Main sync loop"""
    print("=" * 60)
    print("🔄 Serena Memory Sync")
    print("=" * 60)
    print(f"Memories Dir: {SERENA_MEMORIES_DIR}")
    print(f"Gateway: {GCP_GATEWAY_URL}")
    print(f"Sync Interval: {SYNC_INTERVAL}s")
    print("=" * 60)

    # Initialize state
    state = SerenaSyncState(STATE_FILE)
    print(f"Tracking {len(state.file_hashes)} files")

    # Create memories directory if not exists
    SERENA_MEMORIES_DIR.mkdir(parents=True, exist_ok=True)

    # Main loop
    iteration = 0
    while True:
        iteration += 1
        print(f"\n--- Sync iteration {iteration} at {datetime.now().isoformat()} ---")

        # Scan for files
        md_files = scan_serena_memories()
        print(f"Found {len(md_files)} memory files")

        # Sync modified files
        synced = []
        for filepath in md_files:
            try:
                result = sync_file(filepath, state)
                if result:
                    synced.append(result)
                    print(f"✅ Synced: {result['file']} ({result['size']} bytes)")
            except Exception as e:
                print(f"❌ Error syncing {filepath}: {e}")

        print(f"Synced {len(synced)} files")

        # Wait for next sync
        print(f"Sleeping for {SYNC_INTERVAL}s...")
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Serena Memory Sync for Copaw")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--interval", type=int, default=SYNC_INTERVAL, help="Sync interval in seconds"
    )

    args = parser.parse_args()

    if args.once:
        # Run once
        state = SerenaSyncState(STATE_FILE)
        md_files = scan_serena_memories()
        synced = []
        for filepath in md_files:
            result = sync_file(filepath, state)
            if result:
                synced.append(result)
        print(f"Synced {len(synced)} files")
    else:
        SYNC_INTERVAL = args.interval
        main()
