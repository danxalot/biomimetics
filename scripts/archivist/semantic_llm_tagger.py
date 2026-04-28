#!/usr/bin/env python3
"""
BiOS LLM Semantic Block Tagger - Gemma-3-1b-it Integration

Reads Markdown documents from the Obsidian vault, meticulously parsing them into
safe text blocks versus protected exclusion blocks (code/headers).
Sends plain text paragraphs individually to Google AI Studio (gemma-3-1b-it) to
obtain precise inline tags, injecting them back into the native Markdown.

Execution:
    python3 scripts/archivist/semantic_llm_tagger.py
"""

import os
import glob
import re
import json
import time
import urllib.request
import ssl
from pathlib import Path

# --- Configuration ---
DOCS_DIR = "/Users/danexall/biomimetics/docs"
MODEL_ID = "gemma-3-1b-it"
CREDENTIALS_SERVER = "http://localhost:8089"
RATE_LIMIT_DELAY = 2.5  # Seconds between Gemma calls to respect burst envelopes

TAXONOMY_PROMPT = """You are a precise semantic document tagger. Read the provided paragraph extremely carefully.
Check if the core meaning or keywords of the paragraph match any of the following taxonomy domains. 
Do not guess broadly; only tag if there is a concrete semantic link.

Taxonomy Domains:
#bios/architecture - System design, integration, component pipelines, structural code logic
#bios/infrastructure - Cloud deployments, networking, Vultr instances, Cloudflare, email servers
#bios/security - Secrets, credentials, Azure Key Vault, authentication protocols
#bios/voice - Gemini Live, Jarvis daemon, voice relay, PTT audio loops
#bios/memory - MuninnDB, MemU databases, Pythia, structural embeddings
#bios/swarm - Serena, autonomous worker agents, CoPaw workflow, Notion polling
#context/projects - General ARCA, BiOS, or CoPaw project management strategy
#context/life - Personal life events, medical logging, disability tracking
#context/legal - NHS issues, legal complaints, formal proceedings

Instructions:
1. Return ONLY a single line of space-separated tags (e.g. "#bios/architecture #bios/swarm").
2. Your tags must identically match the taxonomy list above.
3. If no tags apply semantically, return EXACTLY the string "NONE" and nothing else.
4. Do not output conversational text or markdown formatting.

Paragraph to Tag:
"""

def fetch_api_key():
    """Fetch the Gemini API key from Credentials Server with local fallback."""
    local_secret = "/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/google_ai_studio"
    try:
        req = urllib.request.Request(f"{CREDENTIALS_SERVER}/secrets/gemini-api-key")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("value")
    except Exception as e:
        print(f"  ⚠ Credentials Server unavailable ({e}), trying local fallback")
        if os.path.exists(local_secret):
            with open(local_secret, "r") as f:
                return f.read().strip()
        return None

def invoke_gemma_1b(api_key, paragraph_text):
    """Sends a single paragraph to Gemma 3 1B to derive tags."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    payload = {
        "contents": [{"parts": [{"text": TAXONOMY_PROMPT + paragraph_text}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 30}
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={api_key}"
    req = urllib.request.Request(url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload).encode())

    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            resp_data = json.loads(r.read().decode())
            if "candidates" in resp_data and resp_data["candidates"]:
                text = resp_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text
            return "NONE"
    except urllib.error.HTTPError as e:
        # If we hit 429/503 limits, back off gracefully
        if e.code in [429, 503]:
            print(f"    ⚠ API Hit limit ({e.code}), backing off 10s...")
            time.sleep(10)
            return "RETRY"
        print(f"    ❌ API Error {e.code}: {e.read().decode()}")
        return "NONE"
    except Exception as e:
        print(f"    ❌ Network Error: {e}")
        return "NONE"

def process_markdown_ast(filepath, api_key):
    """
    Parses a markdown document into protected exclusion blocks (YAML, Codeblocks) 
    and plain text paragraphs. Hits the LLM for plain text and reassembles safely.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Early exit if too short to be worth it
    if len(content.strip()) < 20:
        return False

    # Regex heuristic to split blocks: split by double newlines but protect codeblocks via lookarounds
    # Better approach: sequential line reading state machine
    lines = content.split('\n')
    blocks = []
    
    current_block = []
    in_code_block = False
    in_yaml_frontmatter = False

    for i, line in enumerate(lines):
        # Initial YAML check
        if i == 0 and line.strip() == "---":
            in_yaml_frontmatter = True
            current_block.append(line)
            continue
            
        if in_yaml_frontmatter:
            current_block.append(line)
            if line.strip() == "---":
                in_yaml_frontmatter = False
                blocks.append({"type": "protected", "text": "\n".join(current_block)})
                current_block = []
            continue

        # Codeblock check
        if line.strip().startswith("```"):
            if not in_code_block:
                # Flush existing text block
                if current_block:
                    text = "\n".join(current_block).strip()
                    if text: blocks.append({"type": "text", "text": text})
                current_block = [line]
                in_code_block = True
            else:
                current_block.append(line)
                blocks.append({"type": "protected", "text": "\n".join(current_block)})
                current_block = []
                in_code_block = False
            continue

        if in_code_block:
            current_block.append(line)
            continue

        # Blank lines indicate paragraph breaks
        if line.strip() == "":
            if current_block:
                text = "\n".join(current_block).strip()
                if text: blocks.append({"type": "text", "text": text})
                current_block = []
            # We preserve isolated blank lines as pure structure
            blocks.append({"type": "newline", "text": ""})
            continue

        # Otherwise standard line
        current_block.append(line)

    # Flush remainder
    if current_block:
        text = "\n".join(current_block).strip()
        if text:
            # If we somehow ended while inside a code block, protect it anyway
            if in_code_block:
                blocks.append({"type": "protected", "text": "\n".join(current_block)})
            else:
                blocks.append({"type": "text", "text": text})

    # --- Execute Tagging over text blocks ---
    modified = False
    new_blocks = []
    
    for b in blocks:
        if b["type"] == "text":
            text_str = b["text"]
            
            # Exclusion logic for "text": don't tag Headers, MOC lists, or very short fragments
            if (text_str.startswith("#") or 
                text_str.startswith("- [[") or 
                text_str.lower().startswith("source: `") or
                text_str.startswith("| ") or  # Tables
                len(text_str.split()) < 10):   # Too short
                new_blocks.append(text_str)
                continue
                
            # Don't tag if there's already an inline # tag in it (idempotency check)
            if re.search(r"#(bios|context)/[a-z]+", text_str):
                new_blocks.append(text_str)
                continue

            # Query LLM
            while True:
                time.sleep(RATE_LIMIT_DELAY)
                tags = invoke_gemma_1b(api_key, text_str)
                
                if tags == "RETRY":
                    continue
                break

            # Process LLM Output
            filtered_tags = [t for t in tags.split() if t.startswith("#") and ("bios/" in t or "context/" in t)]
            
            if filtered_tags:
                tag_string = " " + " ".join(filtered_tags)
                print(f"      + Appending {tag_string}")
                new_blocks.append(text_str + tag_string)
                modified = True
            else:
                new_blocks.append(text_str)
        elif b["type"] == "newline":
            new_blocks.append("")
        else:
            # Protected blocks
            new_blocks.append(b["text"])

    if modified:
        reassembled = "\n".join(new_blocks)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(reassembled)
        return True
    
    return False

def run_vault_sweep():
    print("="*60)
    print("  BiOS Semantic LLM Tagger (Gemma 3 1B) - Vault Sweep")
    print("="*60)

    api_key = fetch_api_key()
    if not api_key:
        print("❌ Critical Error: Could not locate Gemini API Key.")
        return

    search_pattern = os.path.join(DOCS_DIR, "**", "*.md")
    files = glob.glob(search_pattern, recursive=True)
    
    modified_count = 0
    total_processed = 0

    for fpath in files:
        if "obsidian_staging" in fpath or ".archive" in fpath:
            continue
            
        filename = os.path.basename(fpath)
        if "MOC" in filename or filename.startswith("MASTER_") or filename in ["SWARM_LEDGER.md", "ACTIVE_LEGAL_CASES.md", "ARCHITECTURE_DECISION_LOG.md"]:
            continue

        print(f"▶ Scanning: {filename}")
        if process_markdown_ast(fpath, api_key):
            print(f"  ✅ Tags Injected into {filename}")
            modified_count += 1
        total_processed += 1

    print("="*60)
    print(f"Sweep Complete. Analyzed {total_processed} files. Generated new semantic block tags in {modified_count} files.")

if __name__ == "__main__":
    run_vault_sweep()
