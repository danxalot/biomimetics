#!/usr/bin/env python3
"""
BiOS Dev Artifact Condenser
Processes harvested raw JSON logs from Claude and Zed, summarizing them
into structured markdown documents in the Obsidian staging area.
"""

import os
import sys
import glob
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib.gemini import MODEL_SYNTH, fetch_api_key, invoke  # noqa: E402
from lib.origin import origin_from_path, stamp_origin  # noqa: E402
from lib.vault_io import land_architecture_note  # noqa: E402

# Configuration
STAGING_ROOT = "/Users/danexall/biomimetics/.staging/raw_dev_artifacts"
OBSIDIAN_STAGING_DIR = "/Users/danexall/biomimetics/docs/obsidian_staging"
ARCHIVE_DIR = os.path.join(STAGING_ROOT, ".archive")
MODEL_ID = MODEL_SYNTH


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

def process_logs():
    print(f"🧹 Starting Dev Artifact Condenser - {datetime.now().isoformat()}")
    
    # 1. Gather staged JSON / JSONL (Grok sessions are jsonl)
    json_files = glob.glob(os.path.join(STAGING_ROOT, "**/*.json"), recursive=True)
    json_files += glob.glob(os.path.join(STAGING_ROOT, "**/*.jsonl"), recursive=True)
    json_files = [f for f in json_files if ".archive" not in f]
    
    if not json_files:
        print("  ✅ No staged dev logs found.")
        return
        
    try:
        api_key = fetch_api_key()
    except Exception as e:
        print(f"  ❌ Cannot proceed without Gemini API Key: {e}")
        return
    if not api_key:
        print("  ❌ Cannot proceed without Gemini API Key.")
        raise SystemExit(1)

    os.makedirs(OBSIDIAN_STAGING_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    print(f"  Found {len(json_files)} dev log files to process.")

    # Group files by day to generate daily summaries
    for fp in json_files:
        filename = os.path.basename(fp)
        print(f"  Processing file: {filename}")
        
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                raw_data = f.read()
                
            # Truncate content if exceptionally large to avoid context overload
            if len(raw_data) > 300000:
                raw_data = raw_data[:300000] + "\n... [TRUNCATED] ..."

            origin = origin_from_path(fp) or "manual"
            origin_tag = f"source/{origin}"
            system_instruction = (
                "You are the BiOS Dev Log Condenser. "
                "Read raw JSON conversation/session records from development IDEs "
                "(Claude, Grok, Zed, Antigravity) and write a concise markdown note of "
                "architectural decisions, refactorings, and rationales.\n"
                "Preserve provenance. You MUST include this YAML frontmatter:\n"
                "---\n"
                f"source_tool: {origin}\n"
                "tags:\n"
                f"  - {origin_tag}\n"
                "  - bios/architecture\n"
                "---\n"
                "Do not wrap the output in markdown fences."
            )
            
            user_content = (
                "Extract the technical essence of this development log. Output it in clean markdown:\n\n"
                f"=== RAW DEV LOG ===\n{raw_data}"
            )
            
            summary = invoke_gemini(api_key, system_instruction, user_content)
            
            if summary:
                # Remove code blocks wrapper if generated
                if summary.startswith("```markdown\n"):
                    summary = summary[12:]
                elif summary.startswith("```md\n"):
                    summary = summary[6:]
                if summary.endswith("```"):
                    summary = summary[:-3]
                if summary.endswith("```\n"):
                    summary = summary[:-4]

                # Save markdown file to Obsidian staging
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_filename = f"dev_log_{timestamp}_{Path(filename).stem}.md"
                out_path = os.path.join(OBSIDIAN_STAGING_DIR, out_filename)
                
                summary = stamp_origin(summary.strip(), origin, fp)
                with open(out_path, "w", encoding="utf-8") as out_f:
                    out_f.write(summary)
                print(f"  ✅ Generated staging document: {out_filename} (origin={origin})")
                try:
                    vault_path = land_architecture_note(out_filename, summary)
                    print(f"  ✅ Landed vault shadow: {vault_path}")
                except Exception as e:
                    print(f"  ⚠ Vault land failed for {out_filename}: {e}")
                
                # Move original file to archive
                dest = os.path.join(ARCHIVE_DIR, filename)
                import shutil
                shutil.move(fp, dest)
            else:
                print(f"  ❌ Failed to condense: {filename}")
        except Exception as e:
            print(f"  ❌ Error processing {filename}: {e}")

    print("✅ Dev logs condensation complete.")

if __name__ == "__main__":
    process_logs()
