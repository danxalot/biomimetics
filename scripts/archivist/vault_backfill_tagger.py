#!/usr/bin/env python3
"""
BiOS Vault Backfill Tagger
Executes a one-off sweep over the legacy Obsidian vault to intelligently
inject YAML frontmatter tags based on semantic content logic.
"""

import os
import glob
import re
from pathlib import Path

DOCS_DIR = "/Users/danexall/biomimetics/docs"

TAG_RULES = {
    "voice": "bios/voice",
    "jarvis": "bios/voice",
    "gemini_relay": "bios/voice",
    "gemini_live": "bios/voice",
    "vultr": "bios/infrastructure",
    "cloudflare": "bios/infrastructure",
    "email": "bios/infrastructure",
    "proton": "bios/infrastructure",
    "mcp": "bios/architecture",
    "notion": "bios/architecture",
    "workflow": "bios/architecture",
    "archivist": "bios/architecture",
    "serena": "bios/swarm",
    "swarm": "bios/swarm",
    "copaw": "bios/swarm",
    "autonomous": "bios/swarm",
    "secret": "bios/security",
    "credential": "bios/security",
    "azure": "bios/security",
    "key_vault": "bios/security",
    "pythia": "bios/memory",
    "muninn": "bios/memory",
    "memory": "bios/memory",
    "embedding": "bios/memory",
    "legal": "context/legal",
    "nhs": "context/legal",
    "complaint": "context/legal",
    "medical": "context/life",
    "disability": "context/life",
    "health": "context/life",
}

def derive_tags(filepath, content):
    tags = set(["source/legacy"]) # Base tag
    check_text = (filepath + "\n" + content).lower()
    for keyword, tag in TAG_RULES.items():
        if keyword in check_text:
            tags.add(tag)
    return sorted(tags)

def inject_frontmatter(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"⚠ Could not read {filepath}: {e}")
        return False

    derived_tags = derive_tags(filepath, content)
    
    # Check if frontmatter exists
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)
        body = frontmatter_match.group(2)
        
        # Check if tags already exist
        if "\ntags:" in f"\n{frontmatter}":
            # Very simplistic tag merge: skip if already has tags block to prevent corrupting complex YAML
            return False
            
        new_frontmatter = f"{frontmatter}\ntags: [{', '.join(derived_tags)}]"
        new_content = f"---\n{new_frontmatter}\n---\n{body}"
    else:
        # No frontmatter, create it
        new_content = f"---\ntags: [{', '.join(derived_tags)}]\nstatus: active\n---\n\n{content}"

    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"✅ Tagged: {os.path.basename(filepath)} with {derived_tags}")
        return True
    return False

def main():
    print("="*60)
    print("  BiOS Vault Backfill Tagger")
    print("="*60)
    
    search_pattern = os.path.join(DOCS_DIR, "**", "*.md")
    files = glob.glob(search_pattern, recursive=True)
    
    tagged_count = 0
    for fpath in files:
        # Ignore staging and known auto-generated directories
        if "obsidian_staging" in fpath or ".archive" in fpath:
            continue
            
        # Ignore MOCs and Master files as they are safely curated manually/by Condenser
        filename = os.path.basename(fpath)
        if "MOC" in filename or filename.startswith("MASTER_") or filename == "SWARM_LEDGER.md" or filename == "ACTIVE_LEGAL_CASES.md" or filename == "ARCHITECTURE_DECISION_LOG.md":
            continue
            
        if inject_frontmatter(fpath):
            tagged_count += 1
            
    print("- "*30)
    print(f"Done. Successfully injected tags into {tagged_count} legacy files.")

if __name__ == "__main__":
    main()
