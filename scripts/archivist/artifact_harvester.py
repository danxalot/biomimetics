#!/usr/bin/env python3
"""
BiOS Artifact Harvester
Silently scrapes logs and artifacts from development tools and staging them for long-term memory ingestion.
"""

import os
import shutil
import glob
from pathlib import Path
from datetime import datetime

# Paths to Scrape
SCRAPE_TARGETS = [
    {"name": "claude", "path": Path.home() / ".claude" / "sessions" / "*.json"},
    {"name": "zed", "path": Path.home() / "Library" / "Application Support" / "Zed" / "conversations" / "*.json"},
    {"name": "bios_artifacts", "path": Path.home() / "biomimetics" / "docs" / "projects" / "bios" / "artifacts" / "*"}
]

STAGING_ROOT = Path.home() / "biomimetics" / ".staging" / "raw_dev_artifacts"

def harvest():
    print("=" * 60)
    print(f"🚜 BiOS Artifact Harvester - {datetime.now().isoformat()}")
    print("=" * 60)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    for target in SCRAPE_TARGETS:
        name = target["name"]
        pattern = str(target["path"])
        
        # Create tool-specific staging directory
        staging_dir = STAGING_ROOT / name / today
        staging_dir.mkdir(parents=True, exist_ok=True)
        
        files = glob.glob(pattern)
        if not files:
            print(f"  Empty: {name}")
            continue
            
        print(f"  Harvesting {len(files)} items from {name}...")
        
        for file_path in files:
            p = Path(file_path)
            if p.is_dir(): continue
            
            dest = staging_dir / p.name
            try:
                shutil.copy2(p, dest)
            except Exception as e:
                print(f"    ⚠️  Failed to copy {p.name}: {e}")

    print("-" * 60)
    print(f"✅ Harvest complete. Artifacts staged in {STAGING_ROOT}")
    print("=" * 60)

if __name__ == "__main__":
    harvest()
