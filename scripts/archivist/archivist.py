#!/usr/bin/env python3
"""
BiOS Archivist — IDE-Independent Knowledge Graph Assimilator

Scans artifact sources (IDE brain directories, raw docs, Notion tasks),
synthesizes them into tagged Obsidian nodes, and stages them for the
knowledge graph.

Usage:
    python3 scripts/archivist/archivist.py              # Ongoing (idempotent)
    python3 scripts/archivist/archivist.py --bootstrap   # Process everything, ignore state
"""

import os
import sys
import json
import ssl
import hashlib
import glob
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent  # biomimetics/
CONFIG_PATH = REPO_ROOT / "config" / "archivist_sources.json"
CREDENTIALS_SERVER = "http://localhost:8089"
CREDENTIALS_API_KEY_PATH = REPO_ROOT / "secrets" / "credentials_api_key"

# Tag assignment rules — keyword in path/content → tag
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
    "disability": "context/health/disability",
    "loss of capacity": "context/health/incapacity",
    "incapacity": "context/health/incapacity",
    "side effects": "context/health/side_effects",
    "adverse reaction": "context/health/side_effects",
    "systemic failure": "context/legal/systemic_failure",
    "systemic harm": "context/legal/systemic_harm",
    "failure of care": "context/legal/failure_of_care",
    "negligence": "context/legal/failure_of_care",
    "duty of candour": "context/legal/duty_of_candour",
    "consequential loss": "context/legal/consequential_loss",
    "health": "context/life",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config():
    """Load archivist_sources.json."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def load_state(state_path):
    """Load the processed-artifacts state file."""
    if os.path.exists(state_path):
        with open(state_path, "r") as f:
            return json.load(f)
    return {"processed": {}}


def save_state(state, state_path):
    """Persist the state file."""
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def content_hash(content):
    """SHA256 hash of content for idempotency."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def fetch_notion_token():
    """Fetch Notion API key from Credentials Server, fallback to local file."""
    try:
        api_key = CREDENTIALS_API_KEY_PATH.read_text().strip()
        req = urllib.request.Request(
            f"{CREDENTIALS_SERVER}/secrets/notion-api-key",
            headers={"X-API-Key": api_key},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("value")
    except Exception as e:
        print(f"  ⚠ Credentials Server unavailable ({e}), trying local fallback")
        local = REPO_ROOT / "secrets" / "notion-api-key"
        if local.exists():
            return local.read_text().strip()
        return None


def derive_tags(filepath, content, default_tags, config_moc):
    """
    Derive Obsidian tags and MOCs from filepath + content.
    Combines legacy TAG_RULES with strict path-based routing.
    """
    tags = set(default_tags)
    mocs = {config_moc} if config_moc else set()
    
    # 1. Legacy Keyword Logic (Retained)
    check_text = (filepath + "\n" + content[:2000]).lower()
    for keyword, tag in TAG_RULES.items():
        if keyword in check_text:
            tags.add(tag)
            
    # 2. Path-Based Routing Logic (Integrated)
    if "ARCA/shared_storage/Awake/" in filepath:
        tags.update(["source/arca", "arca"])
        mocs.add("ARCA_MOC")
        
    if "biomimetics/docs/" in filepath:
        tags.update(["source/biomimetics", "bios/architecture"])
        mocs.add("Biomimetics_MOC")
        
    # 3. Pythia Keyword Logic
    pythia_keywords = ["vsa", "ebm", "jepa", "reasoningbank", "geometric sentience"]
    if any(kw in check_text for kw in pythia_keywords):
        tags.add("pythia")
        mocs.add("Pythia_MOC")
        
    return sorted(list(tags)), sorted(list(mocs))



def derive_title(filepath):
    """Generate a human-readable title from a filename."""
    name = Path(filepath).stem
    # Convert snake_case / kebab-case to Title Case
    title = name.replace("_", " ").replace("-", " ")
    return title.title()


def sanitize_filename(title):
    """Create a safe filename from a title."""
    safe = re.sub(r"[^\w\s-]", "", title)
    safe = re.sub(r"\s+", "_", safe.strip())
    return safe


# ---------------------------------------------------------------------------
# Obsidian Node Synthesis
# ---------------------------------------------------------------------------

def synthesize_node(title, content, tags, mocs, source_path=""):
    """Render an artifact into an Obsidian node with YAML frontmatter."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tag_yaml = "\n".join(f"  - {t}" for t in tags)

    # Extract first meaningful paragraph as summary
    lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("---")]
    summary = lines[0][:200] if lines else "No summary available."

    # Multi-MOC Relational Metadata
    up_links = "\n".join(f"Up: [[{m}]]" for m in mocs)

    node = f"""---
aliases: []
tags:
{tag_yaml}
date: {date_str}
status: active
source: "{source_path}"
---

# {title}

## Relational Metadata
{up_links}

---

## Summary
{summary}

---

## Content

{content}

---

## Traceability
Source: `{source_path}`
Assimilated: {date_str}
Compliance: All operations within free tier limits.
"""
    return node



# ---------------------------------------------------------------------------
# Source Scanners
# ---------------------------------------------------------------------------

def scan_filesystem_sources(config, state, bootstrap=False):
    """Scan configured filesystem paths for artifact markdown files."""
    artifacts = []

    for source in config.get("filesystem_sources", []):
        base = source["base_path"]
        names = source.get("artifact_names", [])
        ignore = source.get("ignore", [])
        default_tags = source.get("default_tags", [])
        moc = source.get("moc", "Biomimetics_MOC")

        if not os.path.isdir(base):
            print(f"  ⚠ Source dir not found: {base}")
            continue

        for name_pattern in names:
            if "*" in name_pattern:
                # Glob pattern — scan the base directory
                matches = glob.glob(os.path.join(base, name_pattern))
            else:
                # Exact filename — might be in subdirs
                matches = glob.glob(os.path.join(base, "**", name_pattern), recursive=True)
                # Also check directly in base
                direct = os.path.join(base, name_pattern)
                if os.path.isfile(direct) and direct not in matches:
                    matches.append(direct)

            for fpath in matches:
                # Skip ignored patterns
                rel = os.path.relpath(fpath, base)
                if any(ig in rel for ig in ignore):
                    continue
                # Skip .resolved files
                if ".resolved" in fpath or ".metadata.json" in fpath:
                    continue

                try:
                    with open(fpath, "r", errors="replace") as f:
                        content = f.read()
                except Exception:
                    continue

                if not content.strip():
                    continue

                chash = content_hash(content)
                if not bootstrap and chash in state.get("processed", {}):
                    continue

                artifacts.append({
                    "title": derive_title(fpath),
                    "content": content,
                    "source_path": fpath,
                    "content_hash": chash,
                    "default_tags": default_tags,
                    "moc": moc,
                    "source_name": source["name"],
                })

    return artifacts


def scan_notion_source(config, state, bootstrap=False):
    """Poll Notion for 'Ready for Sync' tasks."""
    notion_cfg = config.get("notion_source", {})
    if not notion_cfg.get("enabled"):
        return []

    token = fetch_notion_token()
    if not token:
        print("  ⚠ No Notion token available, skipping Notion source")
        return []

    db_id = notion_cfg["database_id"]
    filter_status = notion_cfg["filter_status"]
    default_tags = notion_cfg.get("default_tags", [])
    moc = notion_cfg.get("moc", "Biomimetics_MOC")

    # Query Notion for matching tasks
    query_body = json.dumps({
        "filter": {
            "property": "State",
            "select": {"equals": filter_status}
        },
        "page_size": 20
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        data=query_body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
    )

    artifacts = []
    try:
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx.load_verify_locations(certifi.where())
        except ImportError:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for page in data.get("results", []):
            page_id = page["id"]
            props = page.get("properties", {})

            # Extract title (BiOS Tasks uses 'Task Name')
            title_prop = props.get("Task Name", props.get("Name", {})).get("title", [])
            title = title_prop[0]["plain_text"] if title_prop else f"Notion_{page_id[:8]}"

            # Extract description/body
            desc_prop = props.get("Description", {}).get("rich_text", [])
            body = desc_prop[0]["plain_text"] if desc_prop else ""

            content = f"# {title}\n\n{body}\n\nNotion Page ID: {page_id}"
            chash = content_hash(content)

            if not bootstrap and chash in state.get("processed", {}):
                continue

            artifacts.append({
                "title": title,
                "content": content,
                "source_path": f"notion://{page_id}",
                "content_hash": chash,
                "default_tags": default_tags,
                "moc": moc,
                "source_name": "notion",
                "notion_page_id": page_id,
            })

    except Exception as e:
        print(f"  ⚠ Notion query failed: {e}")

    return artifacts


def archive_notion_task(page_id, token, archive_status):
    """Update a Notion task to 'Archived' status."""
    body = json.dumps({
        "properties": {
            "State": {"select": {"name": archive_status}}
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.notion.com/v1/pages/{page_id}",
        data=body,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10):
            print(f"    ✅ Notion task {page_id[:8]} → {archive_status}")
    except Exception as e:
        print(f"    ⚠ Failed to archive Notion task: {e}")


# ---------------------------------------------------------------------------
# MOC Updater
# ---------------------------------------------------------------------------

def update_moc(moc_name, node_title, moc_dir):
    """Append [[node_title]] to the MOC file if not already present."""
    moc_path = os.path.join(moc_dir, f"{moc_name}.md")
    if not os.path.exists(moc_path):
        print(f"  ⚠ MOC file not found: {moc_path}")
        return

    with open(moc_path, "r") as f:
        moc_content = f.read()

    link = f"[[{node_title}]]"
    if link in moc_content:
        return  # Already linked

    # Append under "## Key Nodes" or at end
    entry = f"- {link}\n"
    if "## Key Nodes" in moc_content:
        moc_content = moc_content.replace("## Key Nodes\n", f"## Key Nodes\n{entry}", 1)
    else:
        moc_content += f"\n{entry}"

    with open(moc_path, "w") as f:
        f.write(moc_content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    bootstrap = "--bootstrap" in sys.argv
    mode = "BOOTSTRAP" if bootstrap else "SWEEP"
    print(f"\n{'='*60}")
    print(f"  BiOS Archivist — {mode} MODE")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}\n")

    config = load_config()
    output = config["output"]
    state_path = output["state_file"]
    staging_dir = output["staging_dir"]
    moc_dir = output["moc_dir"]

    os.makedirs(staging_dir, exist_ok=True)
    state = {} if bootstrap else load_state(state_path)
    if "processed" not in state:
        state["processed"] = {}

    # Collect artifacts from all sources
    print("📂 Scanning filesystem sources...")
    fs_artifacts = scan_filesystem_sources(config, state, bootstrap)
    print(f"   Found {len(fs_artifacts)} new filesystem artifacts")

    print("📋 Scanning Notion source...")
    notion_artifacts = scan_notion_source(config, state, bootstrap)
    print(f"   Found {len(notion_artifacts)} new Notion artifacts")

    all_artifacts = fs_artifacts + notion_artifacts
    if not all_artifacts:
        print("\n✅ No new artifacts to process. Knowledge graph is current.")
        return

    print(f"\n🔧 Processing {len(all_artifacts)} artifacts...\n")

    notion_token = fetch_notion_token()
    archive_status = config.get("notion_source", {}).get("archive_status", "Archived")
    processed_count = 0

    for artifact in all_artifacts:
        title = artifact["title"]
        content = artifact["content"]
        source_path = artifact["source_path"]
        chash = artifact["content_hash"]
        default_tags = artifact["default_tags"]
        moc = artifact["moc"]

        # Derive tags and MOCs (Legacy + Strict Routing)
        tags, mocs = derive_tags(source_path, content, default_tags, moc)

        # Synthesize node
        node_content = synthesize_node(title, content, tags, mocs, source_path)


        # Write to staging
        safe_name = sanitize_filename(title)
        out_filename = f"{safe_name}.md"
        out_path = os.path.join(staging_dir, out_filename)

        with open(out_path, "w") as f:
            f.write(node_content)

        # Update MOCs
        for m in mocs:
            update_moc(m, safe_name, moc_dir)


        # Archive Notion task if applicable
        if artifact.get("notion_page_id") and notion_token:
            archive_notion_task(artifact["notion_page_id"], notion_token, archive_status)

        # Record in state
        state["processed"][chash] = {
            "title": title,
            "staged_as": out_filename,
            "source": source_path,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        processed_count += 1
        print(f"  ✅ {out_filename}")
        print(f"     Tags: {', '.join(tags)}")

    # Save state
    save_state(state, state_path)

    print(f"\n{'='*60}")
    print(f"  ✅ Archivist complete: {processed_count} artifacts staged")
    print(f"  📁 Output: {staging_dir}")
    print(f"  📊 State: {state_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
