#!/usr/bin/env python3
"""
BiOS LLM Semantic Tagger (v2.3.0) - High-Speed Array Mapping
1 Document = N API Calls (Chunked) | 15 RPM Strict Compliance

Optimized for speed and minimal Gemini Flash Lite calls.
- Maps documents to numbered paragraph payloads in chunks.
- Enforces strict 'Rule of 4' tags per paragraph.
- Double-armored JSON parsing (API MimeType + Regex Scrubber).
- Synchronizes inline tags with a global YAML frontmatter block.
"""

import os
import glob
import re
import json
import time
import urllib.request
import ssl
import certifi
import sys

# --- Configuration ---
DOCS_DIR = "/Users/danexall/Google Drive/My Drive/Obsidian-life"
CREDENTIALS_SERVER = "http://127.0.0.1:8089"  # 127.0.0.1 (not localhost) — server binds IPv4 only
RATE_LIMIT_DELAY = 6.0  # 6-second heartbeat for safe RPM/TPM pacing
MIN_WORDS_PER_PARAGRAPH = 20  # Minimum words to trigger semantic tagging
# High-volume tagging: 3.1 Flash Lite free quota (500/day). Synthesis uses 3.5.
from pathlib import Path as _Path
import sys as _sys
_SCRIPTS = str(_Path(__file__).resolve().parent.parent)
if _SCRIPTS not in _sys.path:
    _sys.path.insert(0, _SCRIPTS)
from lib.gemini import MODEL_VOLUME as FLASH_LITE_MODEL  # noqa: E402
PARAGRAPH_CHUNK_SIZE = 5 # Number of paragraphs to process per API call
TAG_MARKER = "<!-- LLM_TAGGED -->"


# --------------------------------------------------------------------------
# HIERARCHICAL TAXONOMY: domain -> area -> descriptor leaves
# 3 tags per paragraph: #domain, #domain/area, #domain/area/descriptor
# 3 tags per frontmatter: #domain, #domain/area (modal), #host/* or #domain/area (next)
# --------------------------------------------------------------------------
TAXONOMY = {
    "email": {
        "legal":          ["systemic_failure", "failure_of_care", "duty_of_candour", "consequential_loss", "complaint"],
        "health":         ["incapacity", "side_effects", "mental_capacity", "disability"],
        "finance":        ["unauthorised_payment", "account_access", "benefit"],
        "correspondence": ["evidence", "action_required", "response"],
        "meta":           ["uncategorized"],
    },
    "arca": {
        "services":        ["api", "daemon", "scheduler", "integration"],
        "mesh":            ["routing", "transport", "coordination"],
        "docker":          ["image", "compose", "deployment", "runtime"],
        "geometry_kernel": ["binding", "embedding", "retrieval", "inference"],
        "architecture":    ["component", "schema", "protocol", "config"],
        "meta":            ["uncategorized", "operational"],
    },
    "bios": {
        "voice_agent":         ["stt", "tts", "dialogue", "intent"],
        "notion":              ["sync", "query", "schema", "cleanup"],
        "mcp_server":          ["transport", "tool", "auth", "deployment"],
        "copaw":               ["workflow", "trigger", "action"],
        "personal_assistant":  ["task", "calendar", "memory", "routing"],
        "architecture":        ["component", "schema", "protocol", "config"],
        "meta":                ["uncategorized", "operational"],
    },
    "pythia": {
        "neural_system":  ["hopfield", "mamba", "kanerva", "jepa", "hdc", "latent_bypass", "concept_monad"],
        "physics_engine": ["hamiltonian", "koopman", "kuramoto", "resonance", "akasha2"],
        "geometry":       ["manifold", "versor", "conformal", "kinematics", "vsa", "ebm"],
        "training":       ["ued", "gpu", "model_training", "dataset"],
        "inference":      ["reasoningbank", "attractor", "dynamics", "retrieval"],
        "meta":           ["uncategorized"],
    },
}

# Pythia detection: any keyword match in content forces domain=pythia regardless of path
# Only high-signal terms that are UNIQUE to pythia. General shared terms like
# "vsa", "ebm", "reasoningbank" appear in bios/arca docs routinely and must NOT
# trigger pythia routing — they are pythia components, not pythia content.
PYTHIA_KEYWORDS = [
    "pythia", "hopfield", "hamiltonian", "koopman", "kanerva", "kuramoto",
    "akasha", "versor", "conformal", "jepa", "concept monad",
    "latent bypass", "latent_bypass", "10k vector", "10kvector",
    "energy-based model", "energy based model",
]

def allowed_leaves_for(domain):
    """Return the full set of valid leaf tags for a domain."""
    leaves = set()
    for area, descriptors in TAXONOMY[domain].items():
        leaves.add(f"#{domain}/{area}")
        for d in descriptors:
            leaves.add(f"#{domain}/{area}/{d}")
    leaves.add(f"#{domain}")
    return leaves

def render_taxonomy_block(domain):
    """Human-readable allowed-tag block for the prompt."""
    lines = []
    for area, descriptors in TAXONOMY[domain].items():
        leaves = ", ".join(f"#{domain}/{area}/{d}" for d in descriptors)
        lines.append(f"  #{domain}/{area} -> {leaves}")
    return "\n".join(lines)

# Few-shot examples per domain. Each shows TWO paragraphs tagged with the exact
# 3-tier hierarchy (#domain, #domain/area, #domain/area/descriptor).
FEWSHOT = {
    "email": {
        "user":  ("[1] On 14 March I emailed the bank about the unauthorised standing order taken from my joint account.\n"
                  "[2] The clinician failed to record my disclosed allergy, in breach of the duty of candour."),
        "model": '{"1":["#email","#email/finance","#email/finance/unauthorised_payment"],"2":["#email","#email/legal","#email/legal/duty_of_candour"]}',
    },
    "arca": {
        "user":  ("[1] The mesh router uses ZMQ transport to coordinate worker nodes across the cluster.\n"
                  "[2] Docker compose file pins the geometry kernel image to a CUDA 12.4 runtime."),
        "model": '{"1":["#arca","#arca/mesh","#arca/mesh/routing"],"2":["#arca","#arca/docker","#arca/docker/runtime"]}',
    },
    "bios": {
        "user":  ("[1] The voice agent pipes STT output into an intent classifier before dispatching to the assistant.\n"
                  "[2] Notion cleanup script archives duplicate database entries on a nightly schedule."),
        "model": '{"1":["#bios","#bios/voice_agent","#bios/voice_agent/intent"],"2":["#bios","#bios/notion","#bios/notion/cleanup"]}',
    },
    "pythia": {
        "user":  ("[1] The Hopfield network stores 10K binary patterns in the attractor landscape.\n"
                  "[2] Conformal mapping projects the manifold onto a versor representation for VSA binding."),
        "model": '{"1":["#pythia","#pythia/neural_system","#pythia/neural_system/hopfield"],"2":["#pythia","#pythia/geometry","#pythia/geometry/conformal"]}',
    },
}

def route_domain(filepath, content):
    """Determine the document's domain and (for pythia) host.
    Returns (domain, host) where host is 'arca'|'bios'|None."""
    from lib.origin import is_ide_log, pythia_by_path

    path_lower = str(filepath).lower()
    content_lower = content.lower()

    # IDE harvests stay bios/arca even if they mention Pythia internals.
    if is_ide_log(filepath, content) and not pythia_by_path(filepath):
        if "/arca/" in path_lower:
            return "arca", None
        return "bios", None

    # Pythia partition is path-true, or a dedicated pythia doc (keyword + not an IDE log)
    if pythia_by_path(filepath) or (
        any(kw in content_lower for kw in PYTHIA_KEYWORDS)
        and not is_ide_log(filepath, content)
    ):
        if "/arca/" in path_lower:
            host = "arca"
        elif "/bios/" in path_lower or "/biomimetics/" in path_lower:
            host = "bios"
        else:
            host = None
        return "pythia", host

    if "/email" in path_lower or "/personal" in path_lower:
        return "email", None
    if "/arca/" in path_lower:
        return "arca", None
    return "bios", None  # default

# --------------------------------------------------------------------------
# DOCUMENT-LEVEL PARTITION DELINEATION (runs on EVERY file, prose or not)
# Guarantees each note is routed to a project partition for memory ingestion,
# so nothing is dropped just because it lacks flowing prose. v1 = deterministic
# path+content signals; an LLM refinement pass can layer on top later.
# --------------------------------------------------------------------------
PARTITION_TAXONOMY = ["life", "life/email", "life/legal", "life/legal/sar",
                      "arca", "bios", "grants", "pythia"]

def classify_partition(filepath, content, frontmatter=""):
    """Return an ordered, de-duplicated list of '#partition/...' tags.
    Always returns at least one (defaults to life)."""
    p = str(filepath).lower()
    c = content.lower()
    tags = []
    def add(leaf):
        t = f"#partition/{leaf}"
        if t not in tags:
            tags.append(t)

    is_email = ("source: email" in c or "\nsender:" in c
                or "/emails/" in p or "/email" in p or "/personal" in p)

    # Legal / SAR / ombudsman — safety-critical partition, highest priority
    legal_sig = (any(k in c for k in [
                    "subject access request", "ombudsman", "lgsco", "phso",
                    "maladministration", "calderdale", "blue badge",
                    "penalty charge", "duty of candour", "safeguarding",
                    "housing officer", "swypft"])
                 or any(k in p for k in ["legal", "complaint", "evidence_pack",
                                          "ombudsman", "/sar"]))
    if legal_sig:
        add("life"); add("life/legal")
        if "subject access request" in c or "sar" in p:
            add("life/legal/sar")

    # Grants / funding for the AI project
    if (any(k in c for k in ["grant application", "funding call", "fellowship",
                             "ukri", "innovate uk", "horizon europe",
                             "research council", "grant opportunity"])
            or "grant" in p):
        add("grants")

    # Pythia research: path wins. Keywords must not hijack IDE work-logs.
    from lib.origin import is_ide_log, pythia_by_path
    if pythia_by_path(filepath):
        add("pythia")
    elif any(kw in c for kw in PYTHIA_KEYWORDS) and not is_ide_log(filepath, content):
        add("pythia")

    # ARCA project docs. IDE logs that mention Muninn/MemU stay bios.
    if "/arca/" in p:
        add("arca")
    elif not is_ide_log(filepath, content) and any(k in c for k in [
            "arca ", "pythia_server", "geometry kernel"]):
        add("arca")

    # BiOS system docs
    if (any(k in p for k in ["/bios", "biomimetics"]) or any(k in c for k in [
            "biomimetics", "silent listener", "archivist", "voice agent",
            "bios memory"])):
        add("bios")

    # Email that isn't already a project/legal doc -> life email
    if is_email and not any(
            t.startswith("#partition/arca") or t.startswith("#partition/grants")
            or t.startswith("#partition/life/legal") for t in tags):
        add("life"); add("life/email")

    if not tags:
        add("life")
    return tags

def build_prompt(domain, payload_text, frontmatter=""):
    """Returns contents_list for Gemma 4. Domain is locked by routing,
    so the model only ever chooses area + descriptor from a small constrained set."""
    taxonomy_block = render_taxonomy_block(domain)
    shot = FEWSHOT[domain]

    # Merged system text into the first user message to avoid 500 errors on Gemma models
    system_text = "You convert numbered paragraph lists to tag JSON. Output ONLY valid JSON. Do not include markdown formatting, reasoning, or backticks."

    # Add frontmatter context if available
    context_header = ""
    if frontmatter:
        context_header = f"""DOCUMENT CONTEXT:
---
{frontmatter}
---
\n"""

    # Build the user turn shape that the fake-prior-turn will mirror.
    real_user = f"""{context_header}Please generate tags for the following paragraphs:

Tags:
{taxonomy_block}

{payload_text}"""
    shot_user = f"""{system_text}

Tags:
{taxonomy_block}

{shot['user']}"""

    contents = [
        {"role": "user",  "parts": [{"text": shot_user}]},
        {"role": "model", "parts": [{"text": shot["model"]}]},
        {"role": "user",  "parts": [{"text": real_user}]},
    ]
    return contents

def fetch_api_key():
    """Fetch Gemini API key from Credentials Server only."""
    from lib.gemini import fetch_api_key as _fetch
    try:
        return _fetch()
    except Exception as e:
        print(f"  ⚠ Credentials Server unavailable ({e})")
        return None

def _scrub_to_json(raw_text):
    """Quad-armoured JSON extraction for Gemma 4 output drift.
    Gemma 4 emits a <|channel>thought
...<channel|> wrapper even when thinking is
    disabled (empty block in that case). Strip it before anything else."""
    if not raw_text:
        return None

    s = raw_text.strip()

    # Strip Gemma 4 thought-channel block (empty or full)
    s = re.sub(r"<\|channel\|?>thought\s*.*?<\s*channel\|?>", "", s, flags=re.DOTALL)
    # Defensive: strip any stray channel/think control tokens
    s = re.sub(r"<\|?/?(?:think|channel|start_of_turn|end_of_turn)[^>]*\|?>", "", s)
    s = s.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    fence = re.match(r"^\s*```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()

    # Final scrub: ensure we have something starting with { or [
    start_brace = s.find("{")
    start_bracket = s.find("[")
    
    if start_brace != -1 and start_bracket != -1:
        start = min(start_brace, start_bracket)
    elif start_brace != -1:
        start = start_brace
    else:
        start = start_bracket

    end_brace = s.rfind("}")
    end_bracket = s.rfind("]")
    
    if end_brace != -1 and end_bracket != -1:
        end = max(end_brace, end_bracket)
    elif end_brace != -1:
        end = end_brace
    else:
        end = end_bracket

    if start != -1 and end != -1:
        s = s[start:end+1]

    try:
        parsed = json.loads(s)
        # Normalize list of dicts to a single dict if the model drifted from few-shot format
        if isinstance(parsed, list):
            new_map = {}
            for item in parsed:
                if isinstance(item, dict):
                    key = None
                    tags = []
                    for k, v in item.items():
                        if k in ["id", "paragraph", "para", "index"]:
                            key = str(v)
                        elif k == "tags":
                            tags = v
                        elif isinstance(v, list) and str(k).isdigit():
                            key = str(k)
                            tags = v
                    if key is not None:
                        new_map[key] = tags
            return new_map
        return parsed
    except Exception as e:
        print(f"  ⚠ JSON parse error: {e}")
        print(f"  [DEBUG] Raw response was: {repr(raw_text)}")
        print(f"  [DEBUG] Scrubbed string was: {repr(s)}")
        return None

def invoke_gemma(api_key, contents, model_id):
    """Call Google Generative AI API (Gemini) with retries."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
            "topP": 0.95,
            "responseMimeType": "application/json",
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    retries = 3
    backoff_factor = 2
    for i in range(retries):
        try:
            ctx = ssl.create_default_context(cafile=certifi.where())

            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp: # Increased timeout to 60s
                data = json.loads(resp.read().decode("utf-8"))
                if "candidates" in data and data["candidates"]:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                # Handle cases where API returns success but no candidates
                print(f"  ⚠ API returned success but no candidates. Response: {data}")
                return None
        except urllib.error.HTTPError as e:
            # 5xx errors and 429 (Rate Limit) are worth retrying
            if (500 <= e.code < 600 or e.code == 429) and i < retries - 1:
                wait = backoff_factor ** i
                print(f"  ⚠ API call failed with HTTP {e.code}. Retrying in {wait}s...")
                time.sleep(wait)
                continue
            else:
                # Other HTTP errors (like 4xx) are likely permanent, don't retry
                print(f"  ⚠ API call failed with HTTP {e.code}: {e.read().decode()}")
                return None
        except Exception as e:
            # Other errors like timeouts
            wait = backoff_factor ** i
            if i < retries - 1:
                print(f"  ⚠ API call failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ⚠ API call failed after {retries} retries: {e}")
                return None
    return None

def process_file(fpath, api_key):
    """Process a single markdown file: partition, tag, and reassemble."""
    print(f"▶ Processing: {os.path.basename(fpath)}")

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        if TAG_MARKER in content:
            print(f"  ○ Skipping: Already tagged.")
            return False
    except Exception as e:
        print(f"  ⚠ Read error: {e}")
        return False

    domain, host = route_domain(fpath, content)
    model_id = FLASH_LITE_MODEL if domain == "email" else FLASH_LITE_MODEL
    print(f"  ○ Using model: {model_id}")

    lines = content.split("\n")
    paragraphs = []
    current_para = []
    in_fence = False

    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---" and not in_fence:
            paragraphs.append({"type": "protected", "text": line})
            in_fence = "yaml"
            continue
        if in_fence == "yaml":
            paragraphs[-1]["text"] += "\n" + line
            if line.strip() == "---": in_fence = False
            continue

        if line.strip().startswith("```"):
            if not in_fence:
                if current_para:
                    paragraphs.append({"type": "text", "text": "\n".join(current_para)})
                    current_para = []
                paragraphs.append({"type": "protected", "text": line})
                in_fence = "code"
            else:
                paragraphs[-1]["text"] += "\n" + line
                in_fence = False
            continue

        if in_fence == "code":
            paragraphs[-1]["text"] += "\n" + line
            continue

        if line.strip() == "":
            if current_para:
                paragraphs.append({"type": "text", "text": "\n".join(current_para)})
                current_para = []
            paragraphs.append({"type": "newline", "text": ""})
        else:
            current_para.append(line)

    if current_para:
        paragraphs.append({"type": "text", "text": "\n".join(current_para)})

    frontmatter_text = ""
    if paragraphs and paragraphs[0]["type"] == "protected" and paragraphs[0]["text"].startswith("---"):
        frontmatter_text = paragraphs[0]["text"]

    # Document-level partition delineation — ALWAYS computed, even with no prose.
    partition_tags = classify_partition(fpath, content, frontmatter_text)
    partition_line = " ".join(partition_tags)

    text_indices = [i for i, p in enumerate(paragraphs) if p["type"] == "text" and len(p["text"].split()) >= MIN_WORDS_PER_PARAGRAPH]

    if not text_indices:
        print(f"  ○ No prose to enrich — document-level partition only: {partition_line}")

    all_chunks_succeeded = True
    for i in range(0, len(text_indices), PARAGRAPH_CHUNK_SIZE):
        chunk_indices = text_indices[i:i + PARAGRAPH_CHUNK_SIZE]

        payload_text = "\n\n".join(f"[{j+1}] {paragraphs[idx]['text']}" for j, idx in enumerate(chunk_indices))
        prompt_contents = build_prompt(domain, payload_text, frontmatter_text)

        print(f"  ○ Processing chunk {i//PARAGRAPH_CHUNK_SIZE + 1}...")
        raw_response = invoke_gemma(api_key, prompt_contents, model_id)

        if not raw_response:
            print(f"  ⚠ Failed to get response for chunk.")
            all_chunks_succeeded = False
            continue

        tag_map = _scrub_to_json(raw_response)
        if not tag_map:
            print(f"  ⚠ Failed to parse JSON for chunk.")
            all_chunks_succeeded = False
            continue

        for j, idx in enumerate(chunk_indices):
            key = str(j + 1)
            if key in tag_map:
                tags = tag_map[key]
                if isinstance(tags, list) and tags:
                    tag_string = " " + " ".join(tags)
                    paragraphs[idx]["text"] += tag_string

        time.sleep(1.0) # Small delay between chunks

    # Reassemble body, inject the document-level partition line after any
    # frontmatter, then the processed marker. EVERY file is written + marked,
    # so ingestion is decoupled from prose-tagging and nothing is dropped.
    reassembled = "\n".join(p["text"] for p in paragraphs)
    if frontmatter_text and frontmatter_text in reassembled:
        reassembled = reassembled.replace(
            frontmatter_text, frontmatter_text + "\n\n" + partition_line, 1)
    else:
        reassembled = partition_line + "\n\n" + reassembled

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(reassembled + "\n\n" + TAG_MARKER)

    if text_indices and all_chunks_succeeded:
        print(f"  ✅ Enriched + partitioned: {partition_line}")
    elif text_indices:
        print(f"  ⚠️ Partitioned; some enrichment chunks failed: {partition_line}")
    else:
        print(f"  ✅ Partitioned (no prose): {partition_line}")
    return True

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="process at most N files that actually get written (0 = all)")
    args, _ = parser.parse_known_args()

    print("="*60)
    print("  BiOS Semantic LLM Tagger (v2.4.0) - Partition Delineation")
    print("="*60)

    from lib.origin import rewrite_artifact_partitions
    from lib.vault_io import read_text, write_text
    art_dir = os.path.join(DOCS_DIR, "bios", "architecture", "artifacts")
    fixed = 0
    if os.path.isdir(art_dir):
        for fpath in glob.glob(os.path.join(art_dir, "*.md")):
            fp = _Path(fpath)
            try:
                old = read_text(fp)
            except Exception:
                continue
            new = rewrite_artifact_partitions(fpath, old)
            if new != old:
                write_text(fp, new)
                fixed += 1
                print(f"  ✏ corrected partitions: {os.path.basename(fpath)}")
        if fixed:
            print(f"  Fixed {fixed} mis-partitioned artifact notes (origin kept, pythia keyword dropped).")

    api_key = fetch_api_key()
    if not api_key:
        print("❌ Critical Error: Could not locate Gemini API Key.")
        sys.exit(1)

    files = glob.glob(os.path.join(DOCS_DIR, "**", "*.md"), recursive=True)

    processed = 0
    for fpath in files:
        if any(x in fpath for x in ["obsidian_staging", ".archive", "_generated", "MOC", "MASTER_"]):
            continue

        did = process_file(fpath, api_key)
        if did:
            processed += 1
            if args.limit and processed >= args.limit:
                print(f"\n[--limit {args.limit}] stopping after {processed} written files.")
                break
            time.sleep(RATE_LIMIT_DELAY)

    print(f"\nDone. {processed} files written this run.")

if __name__ == "__main__":
    main()
