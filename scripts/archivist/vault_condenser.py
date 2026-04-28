#!/usr/bin/env python3
"""
BiOS Vault Condenser (Tier 2 Assimilator)
Autonomously compresses raw staging artifacts into Master reference documents
using Gemini 3.1 Flash Lite via direct REST calls.
"""

import os
import glob
import json
import zipfile
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STAGING_DIR = "/Users/danexall/biomimetics/docs/obsidian_staging"
ARCHIVE_DIR = os.path.join(STAGING_DIR, ".archive")
DOCS_DIR = "/Users/danexall/biomimetics/docs"

CREDENTIALS_SERVER = "http://localhost:8089"
CREDENTIALS_API_KEY_PATH = "/Users/danexall/biomimetics/secrets/credentials_api_key"

MODEL_ID = "gemini-3.1-flash-lite-preview"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent"

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

def fetch_gemini_key():
    """Fetch Gemini API key from Credentials Server."""
    try:
        with open(CREDENTIALS_API_KEY_PATH, 'r') as f:
            master_key = f.read().strip()
        req = urllib.request.Request(
            f"{CREDENTIALS_SERVER}/secrets/gemini_api_key",
            headers={"X-API-Key": master_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("value")
    except Exception as e:
        print(f"  ⚠ Credentials Server unavailable ({e}), trying local fallback")
        local_fallback = "/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/google_ai_studio"
        if os.path.exists(local_fallback):
            with open(local_fallback, 'r') as f:
                return f.read().strip()
        print(f"  ⚠ Local fallback not found at {local_fallback}")
        return None

def invoke_gemini(api_key, system_instruction, user_content):
    """Invoke Gemini REST API synchronously."""
    payload = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_content}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2, # Low temperature for accurate summarization
            "topP": 0.95
        }
    }
    
    import ssl
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        f"{GEMINI_URL}?key={api_key}",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8")
    )
    
    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))
            return response_data["candidates"][0]["content"]["parts"][0]["text"]
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
        
    api_key = fetch_gemini_key()
    if not api_key:
        print("  ❌ Cannot proceed without Gemini API Key.")
        return

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
