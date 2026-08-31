#!/usr/bin/env python3
"""
BiOS Vault Condenser (Tier 2 Assimilator)
Autonomously compresses raw staging artifacts into Master reference documents
using Gemini 3.5 Flash Lite via the shared credentials client.
"""

import os
import sys
import glob
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib.gemini import MODEL_SYNTH, fetch_api_key, invoke  # noqa: E402
from lib.vault_io import land_architecture_note  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STAGING_DIR = "/Users/danexall/biomimetics/docs/obsidian_staging"
ARCHIVE_DIR = os.path.join(STAGING_DIR, ".archive")
DOCS_DIR = "/Users/danexall/biomimetics/docs"

MODEL_ID = MODEL_SYNTH

PILLARS = [
    {
        "name": "Health",
        "tags": ["bios/health", "context/life"],
        "master_file": os.path.join(DOCS_DIR, "MASTER_HEALTH_RECORD.md"),
        "instruction": "Integrate medical timelines, conditions, disabilities, and administrative health notes."
    },
    {
        "name": "Legal",
        "tags": ["context/legal"],
        "master_file": os.path.join(DOCS_DIR, "ACTIVE_LEGAL_CASES.md"),
        "instruction": "Integrate active legal cases, dispute resolutions, and formal administrative complaints/history."
    },
    {
        "name": "Architecture",
        "tags": ["bios/architecture", "bios/infrastructure"],
        "master_file": os.path.join(DOCS_DIR, "ARCHITECTURE_DECISION_LOG.md"),
        "instruction": "Integrate architectural decisions, infrastructure choices, design motives, and rejected alternatives. Extract the 'Why?' behind changes."
    },
    {
        "name": "Swarm",
        "tags": ["bios/swarm", "bios/memory"],
        "master_file": os.path.join(DOCS_DIR, "SWARM_LEDGER.md"),
        "instruction": "Integrate agent workflows, prompt strategies, state changes, and swarm-level execution observations."
    }
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def invoke_gemini(_api_key, system_instruction, user_content):
    try:
        return invoke(
            user_content,
            system=system_instruction,
            model=MODEL_SYNTH,
            temperature=0.2,
        )
    except Exception as e:
        print(f"  ⚠ Gemini API call failed: {e}")
        return None

def archive_files(filepaths, archive_name_prefix):
    """Zip up processed files and move them to the .archive directory."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    zip_filename = f"{archive_name_prefix}_{timestamp}.zip"
    zip_path = os.path.join(ARCHIVE_DIR, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in filepaths:
            zf.write(fp, os.path.basename(fp))
            
    # Delete original files after successful zipping
    for fp in filepaths:
        os.remove(fp)
        
    return zip_path

# ---------------------------------------------------------------------------
# Core Logic
# ---------------------------------------------------------------------------

def main():
    print(f"\n{'='*60}")
    print(f"  BiOS Vault Condenser — ACTIVE")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}\n")
    
    if not os.path.exists(STAGING_DIR):
        print("  ✅ Staging directory does not exist. Nothing to process.")
        return

    staged_files = glob.glob(os.path.join(STAGING_DIR, "*.md"))
    if not staged_files:
        print("  ✅ No `.md` files found in staging. Vault is clean.")
        return
        
    try:
        api_key = fetch_api_key()
    except Exception as e:
        print(f"  ❌ Cannot proceed without Gemini API Key: {e}")
        return
    if not api_key:
        print("  ❌ Cannot proceed without Gemini API Key.")
        raise SystemExit(1)

    # Categorize files by Pillar
    processed_any = False
    
    for pillar in PILLARS:
        matched_files = []
        for fp in staged_files:
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                # Simple check: does the file content contain any of the pillar tags?
                # (Tags are in the frontmatter)
                if any(tag in content for tag in pillar["tags"]):
                    matched_files.append((fp, content))
            except Exception as e:
                print(f"  ⚠ Error reading {fp}: {e}")
                
        if not matched_files:
            continue
            
        print(f"🔧 Processing {len(matched_files)} files for Pillar: {pillar['name']}")
        
        # Load Current Master
        master_path = pillar["master_file"]
        if os.path.exists(master_path):
            with open(master_path, 'r', encoding='utf-8') as f:
                master_content = f.read()
        else:
            print(f"  ⚠ Master file {master_path} missing. Skipping.")
            continue
            
        # Construct Prompt Payload
        system_instruction = (
            "You are the BiOS Vault Condenser, a precision knowledge integration agent. "
            "Your ONLY job is to take an existing 'MASTER DOC' and update it intelligently "
            "using new raw 'STAGED FACTS'. You must eliminate bloat, discard redundant "
            "boilerplate from staged files, and retain all existing critical historical facts and dates.\n"
            f"Focus Directive: {pillar['instruction']}\n"
            "Return ONLY the raw markdown of the updated Master Document. Do not wrap it in markdown code blocks like ```markdown."
        )
        
        staged_facts_str = "\n\n".join([f"--- RAW STAGED FILE: {os.path.basename(fp)} ---\n{content}" for fp, content in matched_files])
        
        user_content = (
            f"=== EXISTING MASTER DOC ===\n{master_content}\n\n"
            f"=== NEW STAGED FACTS ===\n{staged_facts_str}\n\n"
            "Rewrite the master doc by incorporating the new facts into the appropriate sections. Do not lose any existing information from the master doc."
        )
        
        # Execute Summarization
        print(f"  🧠 Calling {MODEL_ID}...")
        updated_master = invoke_gemini(api_key, system_instruction, user_content)
        
        if updated_master:
            # Clean up potential markdown formatting block if the model outputs it anyway
            if updated_master.startswith("```markdown\n"):
                updated_master = updated_master[12:]
            elif updated_master.startswith("```md\n"):
                updated_master = updated_master[6:]
            if updated_master.endswith("```"):
                updated_master = updated_master[:-3]
            if updated_master.endswith("```\n"):
                updated_master = updated_master[:-4]
                
            # Write updated master
            with open(master_path, 'w', encoding='utf-8') as f:
                f.write(updated_master.strip() + "\n")
            print(f"  ✅ Updated '{os.path.basename(master_path)}'.")
            
            for fp, content in matched_files:
                try:
                    land_architecture_note(os.path.basename(fp), content)
                except Exception as e:
                    print(f"  ⚠ Vault land failed for {os.path.basename(fp)}: {e}")

            # Archive files
            archived = archive_files([fp for fp, _ in matched_files], f"archive_{pillar['name'].lower()}")
            print(f"  📦 Zipped raw files to {os.path.basename(archived)}")
            
            # Remove from staged_files list so they don't get double processed if they have multiple tags
            staged_files = [sf for sf in staged_files if sf not in [fp for fp, _ in matched_files]]
            processed_any = True
            
            # Anti-spam delay to prevent Google GenAI rate limit/503 burst rejections (free tier limits)
            import time
            print("  ⏳ Waiting 10 seconds before next pillar to respect API burst limits...")
            time.sleep(10)
        else:
            print(f"  ❌ Failed to generate condensation for {pillar['name']}.")

    if processed_any:
        print(f"\n  ✅ Vault Condensation Sweep Complete")
    else:
        print(f"\n  ✅ No condensation required for defined pillars.")

if __name__ == "__main__":
    main()
