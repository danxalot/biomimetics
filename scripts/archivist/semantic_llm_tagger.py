#!/usr/bin/env python3
"""
BiOS LLM Semantic Tagger (v2.1.0) - High-Speed Array Mapping
1 Document = 1 API Call | 15 RPM Strict Compliance

Optimized for speed and minimal Gemma 4 model calls.
- Maps documents to numbered paragraph payloads.
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
import sys

# --- Configuration ---
DOCS_DIR = "/Users/danexall/biomimetics/docs"
CREDENTIALS_SERVER = "http://localhost:8089"
RATE_LIMIT_DELAY = 6.0  # 6-second heartbeat for safe RPM/TPM pacing
MIN_WORDS_PER_PARAGRAPH = 20  # Minimum words to trigger semantic tagging

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
    path_lower = str(filepath).lower()
    content_lower = content.lower()

    # Pythia detection wins over path — pythia lives inside both arca and bios
    if any(kw in content_lower for kw in PYTHIA_KEYWORDS):
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

def build_prompt(domain, payload_text):
    """Returns (system_text, contents_list) for Gemma 4. Domain is locked by routing,
    so the model only ever chooses area + descriptor from a small constrained set."""
    taxonomy_block = render_taxonomy_block(domain)
    shot = FEWSHOT[domain]

    # Single declarative sentence. No rules, no constraints — those trigger reasoning.
    system_text = "You convert numbered paragraph lists to tag JSON."

    # Build the user turn shape that the fake-prior-turn will mirror.
    real_user = f"Tags:\n{taxonomy_block}\n\n{payload_text}"
    shot_user = f"Tags:\n{taxonomy_block}\n\n{shot['user']}"

    contents = [
        {"role": "user",  "parts": [{"text": shot_user}]},
        {"role": "model", "parts": [{"text": shot["model"]}]},
        {"role": "user",  "parts": [{"text": real_user}]},
    ]
    return system_text, contents

def fetch_api_key():
    """Fetch Gemini API key from Credentials Server."""
    creds_api_key_path = "/Users/danexall/biomimetics/secrets/credentials_api_key"
    try:
        if os.path.exists(creds_api_key_path):
            with open(creds_api_key_path, 'r') as f:
                master_key = f.read().strip()
            
            req = urllib.request.Request(
                f"{CREDENTIALS_SERVER}/secrets/google_api_key",
                headers={"X-API-Key": master_key},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("value")
        return None
    except Exception as e:
        print(f"  ⚠ Credentials Server unavailable ({e})")
        return None

def _scrub_to_json(raw_text):
    """Quad-armoured JSON extraction for Gemma 4 output drift.
    Gemma 4 emits a `<|channel>thought\\n...<channel|>` wrapper even when thinking is
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
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()

    # Direct parse
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Greedy extract: first '{' to last '}'
    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last > first:
        candidate = s[first:last + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Common Gemma drift: trailing commas, single quotes
            cleaned = re.sub(r",(\s*[}\]])", r"\1", candidate)
            cleaned = cleaned.replace("'", '"')
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return None
    return None


def invoke_gemma(api_key, system_text, contents, target_model):
    """Gemma 4 call. Uses native `system` role. Thinking is disabled by NOT prefixing
    the system prompt with `<|think|>`. Greedy decoding (temp=0, topK=1) to suppress
    any residual stochastic drift into the (empty) thought channel."""

    # Choke-point: 6s pause for 15 RPM compliance
    time.sleep(RATE_LIMIT_DELAY)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    payload_dict = {
        "systemInstruction": {"parts": [{"text": system_text}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.0,
            "topK": 1,
            "topP": 1.0,
            "candidateCount": 1,
            "maxOutputTokens": 131072,
            # Force JSON output at the API level. Supported on Gemini models on this
            # endpoint; Gemma 4 may also support it. If not, we get a fast HTTP 400.
            "response_mime_type": "application/json",
            "stopSequences": ["```", "\n\nInput:", "\n\nAllowed", "Themes:"],
        },
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
    data = json.dumps(payload_dict).encode("utf-8")
    req = urllib.request.Request(
        url,
        headers={"Content-Type": "application/json"},
        data=data,
    )

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=600) as r:
            resp_data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:800]
        print(f"    ❌ HTTP Error {e.code}: {body}")
        if e.code == 400 and "response_mime_type" in body:
            print("    ℹ response_mime_type not supported by this model — remove it from generationConfig.")
        return "ERROR"
    except Exception as e:
        print(f"    ❌ Network Error: {e}")
        return "ERROR"

    candidates = resp_data.get("candidates") or []
    if not candidates:
        print(f"    ❌ No candidates. Raw: {json.dumps(resp_data)[:400]}")
        return "ERROR"

    candidate = candidates[0]
    finish = candidate.get("finishReason", "")
    if "content" not in candidate:
        print(f"    ❌ API blocked (finish={finish}): {json.dumps(candidate)[:400]}")
        return "ERROR"

    parts = candidate["content"].get("parts") or []
    raw_text = "".join(p.get("text", "") for p in parts).strip()

    parsed = _scrub_to_json(raw_text)
    if parsed is not None:
        if finish == "MAX_TOKENS":
            print("    ⚠ Output hit MAX_TOKENS — JSON may be truncated/partial.")
        return parsed

    print("    ❌ Could not extract JSON from Gemma output.")
    print("    --- RAW LLM OUTPUT START ---")
    print(raw_text[:2000])
    print("    --- RAW LLM OUTPUT END ---")
    return "ERROR"

def scrub_content(content):
    """Surgically strip all legacy/prior tags from the body."""
    # Strip inline tags (any domain in our hierarchy + legacy 'context', plus '#host/*')
    tag_pattern = r'#(context|email|bios|arca|pythia|host|source)/[\w/-]+'
    content = re.sub(tag_pattern, '', content)
    
    # Strip standalone tags line
    content = re.sub(r'^(tags|Tags):[ \t]*.*$', '', content, flags=re.MULTILINE)
    
    # Clean up empty lines
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()

def update_frontmatter(content, tags):
    """Overwrite existing YAML frontmatter tags with the aggregate list."""
    tag_list_str = ", ".join([f'"{t}"' for t in tags])
    
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    
    if frontmatter_match:
        yaml_content = frontmatter_match.group(1)
        if re.search(r"^tags:", yaml_content, re.MULTILINE):
            new_yaml = re.sub(r"^tags:.*$", f"tags: [{tag_list_str}]", yaml_content, flags=re.MULTILINE)
        else:
            new_yaml = yaml_content.strip() + f"\ntags: [{tag_list_str}]"
        return content.replace(yaml_content, new_yaml)
    else:
        return f"---\ntags: [{tag_list_str}]\n---\n\n" + content

def derive_frontmatter_tags(domain, host, per_paragraph_tags):
    """Build the 3 document-level identity tags from inline paragraph tags.
    Rules:
      tag 1 = #<domain>
      tag 2 = most-common #<domain>/<area>
      tag 3 = #host/<host> for pythia, else next-most-common area (or modal descriptor)
    """
    from collections import Counter
    area_counter = Counter()
    descriptor_counter = Counter()
    for tags in per_paragraph_tags:
        for t in tags:
            parts = t.strip("#").split("/")
            if len(parts) == 2:
                area_counter[t] += 1
            elif len(parts) == 3:
                descriptor_counter[t] += 1
                # The area implicit in this descriptor also counts
                area_counter[f"#{parts[0]}/{parts[1]}"] += 1

    out = [f"#{domain}"]
    if area_counter:
        out.append(area_counter.most_common(1)[0][0])

    if domain == "pythia" and host:
        out.append(f"#host/{host}")
    else:
        # Prefer second-most-common area; fall back to top descriptor
        if len(area_counter) >= 2:
            out.append(area_counter.most_common(2)[1][0])
        elif descriptor_counter:
            out.append(descriptor_counter.most_common(1)[0][0])
        else:
            out.append(f"#{domain}/meta")
    return out

def process_file(filepath, api_key):
    """Processes an entire document in 1 API call using Paragraph Mapping."""
    with open(filepath, "r", encoding="utf-8") as f:
        original_content = f.read()

    if len(original_content.strip()) < 50:
        return False

    # Route: content-aware pythia detection + path-based domain fallback
    domain, host = route_domain(filepath, original_content)
    # Both Gemma 4 models work; 26B-A4B is faster (MoE). Use it everywhere.
    target_model = "gemma-4-26b-a4b-it"
    allowed_leaves = allowed_leaves_for(domain)

    clean_content = scrub_content(original_content)
    paragraphs = [p.strip() for p in clean_content.split("\n\n") if p.strip()]

    if not paragraphs:
        return False

    payload_parts = []
    taggable_count = 0
    for i, p in enumerate(paragraphs, 1):
        if len(p.split()) >= MIN_WORDS_PER_PARAGRAPH:
            payload_parts.append(f"[{i}] {p}")
            taggable_count += 1

    if not payload_parts:
        print(f"  ▶ Processing: {os.path.basename(filepath)}")
        print(f"    ⚠ Skipped: No paragraphs meet the {MIN_WORDS_PER_PARAGRAPH}-word threshold.")
        return False

    payload_text = "\n\n".join(payload_parts)

    host_label = f" (host={host})" if host else ""
    print(f"  ▶ Processing: {os.path.basename(filepath)}")
    print(f"    🔒 Domain: {domain}{host_label} | Taggable: {taggable_count}/{len(paragraphs)} | Heartbeat: {RATE_LIMIT_DELAY}s")

    system_text, contents = build_prompt(domain, payload_text)
    result = invoke_gemma(api_key, system_text, contents, target_model)

    if result == "ERROR" or result is None:
        print(f"    ❌ Failed to tag file. Halting further attempts on this file.")
        return False

    json_response = result
    if not json_response or not isinstance(json_response, dict):
        print(f"    ❌ Invalid response format received.")
        return False

    # Apply tags inline. Enforce exactly 3 tags per paragraph, all from the
    # constrained domain taxonomy. Hallucinated tags are dropped.
    tagged_paragraphs = []
    per_paragraph_tags = []

    for i, p in enumerate(paragraphs, 1):
        idx_str = str(i)
        if idx_str in json_response and isinstance(json_response[idx_str], list):
            p_tags = [
                t.strip() for t in json_response[idx_str]
                if isinstance(t, str) and t.strip() in allowed_leaves
            ][:3]
            if p_tags:
                tagged_paragraphs.append(f"{p}\n{' '.join(p_tags)}")
                per_paragraph_tags.append(p_tags)
            else:
                tagged_paragraphs.append(p)
        else:
            tagged_paragraphs.append(p)

    # Derive 3 document-level frontmatter tags from the inline tags
    if per_paragraph_tags:
        frontmatter_tags = derive_frontmatter_tags(domain, host, per_paragraph_tags)
    else:
        frontmatter_tags = [f"#{domain}", f"#{domain}/meta", f"#{domain}/meta/uncategorized"]

    final_body = "\n\n".join(tagged_paragraphs)
    final_content = update_frontmatter(final_body, frontmatter_tags)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(final_content)

    print(f"    ✅ Tagged {len(tagged_paragraphs)} paragraphs | Frontmatter: {' '.join(frontmatter_tags)}")
    return True

def run_vault_sweep():
    print("="*60)
    print("  BiOS Semantic Tagger v2.1.0 (High-Speed Array Mapping)")
    print("="*60)

    api_key = fetch_api_key()
    if not api_key:
        print("❌ Critical Error: Could not locate Gemini API Key.")
        return

    search_pattern = os.path.join(DOCS_DIR, "**", "*.md")
    files = glob.glob(search_pattern, recursive=True)
    
    modified_count = 0
    for fpath in files:
        if any(x in fpath for x in ["staging", ".archive", "MOC"]): continue
        filename = os.path.basename(fpath)
        if filename in ["SWARM_LEDGER.md", "ACTIVE_LEGAL_CASES.md"]: continue

        if process_file(fpath, api_key):
            modified_count += 1

    print("="*60)
    print(f"Sweep Complete. Successfully analyzed and updated {modified_count} files.")

if __name__ == "__main__":
    run_vault_sweep()