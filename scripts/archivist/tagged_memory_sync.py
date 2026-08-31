#!/usr/bin/env python3
"""
BiOS Vault-to-Memory Syncer (v2)
Vectorises the WHOLE partitioned Obsidian vault into the GCP memory orchestrator
(MuninnDB working memory + MemU archive). Every note processed by the semantic
tagger carries the <!-- LLM_TAGGED --> marker and a #partition/* delineation;
this syncer walks the entire vault, not just emails, and attaches the partition
to each memory's metadata so downstream retrieval can filter by project.

Incremental + idempotent via SHA-256 state. Decoupled from prose-tagging: the
marker now means "processed & partitioned", not "has flowing prose".
"""

import os
import json
import hashlib
import re
import time
import argparse
from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.error
import ssl

try:
    import certifi
except ImportError:
    certifi = None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VAULT_ROOT = Path("/Users/danexall/Google Drive/My Drive/Obsidian-life")
STATE_FILE = Path.home() / ".arca" / "tagged_sync_state.json"
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
TAG_MARKER = "<!-- LLM_TAGGED -->"

EXTENSIONS = {".md", ".markdown"}

# Never ingest: raw staging, archives, and auto-generated overview outputs
# (the last would create a feedback loop — L4 is derived FROM memory, not INTO it).
EXCLUDE_SEGMENTS = ("obsidian_staging", "staging", ".archive", "_generated")
EXCLUDE_NAME_SUBSTR = ("MASTER_",)

MAX_CHARS = 20000  # safety cap per note payload
SYNC_RETRIES = 4
READ_RETRIES = 5
STATE_FLUSH_EVERY = 10

# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

def ssl_context():
    """macOS Python 3.13's default CA store is empty; always pin certifi."""
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def read_vault_file(path: Path) -> str:
    """Google Drive File Stream raises EDEADLK (Errno 11); retry the read."""
    last = None
    for attempt in range(READ_RETRIES):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            last = e
            if getattr(e, "errno", None) == 11 or "deadlock" in str(e).lower():
                time.sleep(0.4 * (attempt + 1))
                continue
            raise
    raise last

def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def extract_partitions(content: str) -> list:
    """Return the ordered list of partition leaves, e.g. ['life', 'life/legal']."""
    found = re.findall(r"(?<!\S)#partition/([a-zA-Z0-9_/]+)", content)
    seen, out = set(), []
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

def extract_tags(content: str) -> list:
    tags = []
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if match:
        frontmatter = match.group(1)
        tags_match = re.search(r"tags:\s*\[(.*?)\]", frontmatter)
        if tags_match:
            tags = [t.strip() for t in tags_match.group(1).split(",") if t.strip()]
        else:
            tags_list_match = re.search(r"tags:\s*\n((?:\s*-\s*\S+\n?)+)", frontmatter)
            if tags_list_match:
                tags = [line.strip().lstrip("-").strip() for line in tags_list_match.group(1).strip().split("\n")]
    inline_tags = re.findall(r"(?<!\S)#([a-zA-Z0-9_/]+)", content)
    tags.extend(inline_tags)
    return list(set(tags))

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"files": {}}

def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def _ssl_post(payload: dict, timeout: int = 90) -> dict:
    data = json.dumps(payload).encode("utf-8")
    ctx = ssl_context()
    req = urllib.request.Request(
        GCP_GATEWAY_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
        body = response.read().decode()
        return json.loads(body) if body else {}


def purge_source(filepath: str) -> bool:
    """Remove prior DB copies of this vault path (Muninn + MemU)."""
    try:
        result = _ssl_post(
            {
                "operation": "purge",
                "source": filepath,
                "source_filter": filepath,
                "timeframe": "all",
            },
            timeout=60,
        )
        status = result.get("status")
        return status in ("success", "partial") or not result.get("errors")
    except Exception as e:
        print(f"  ⚠ purge {filepath}: {e}")
        return False


def file_record(state: dict, rel_path: str) -> dict:
    raw = (state.get("files") or {}).get(rel_path)
    if isinstance(raw, str):
        return {"hash": raw}
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def set_file_record(state: dict, rel_path: str, sha: str, memory_id=None) -> None:
    rec = {"hash": sha}
    if memory_id:
        rec["memory_id"] = memory_id
    state.setdefault("files", {})[rel_path] = rec


def sync_to_gcp(content: str, filepath: str, tags: list, partitions: list) -> tuple:
    """Upsert this vault note. Returns (ok, memory_id)."""
    purge_source(filepath)
    payload = {
        "operation": "memorize",
        "upsert": True,
        "skip_token_budget": True,
        "content": content[:MAX_CHARS],
        "metadata": {
            "source": filepath,
            "tags": tags,
            "partition": partitions,
            "partition_primary": partitions[0] if partitions else "life",
            "synced_at": datetime.now().isoformat(),
            "tagged": True,
            "source_system": "vault_sync",
        },
    }

    last_err = None
    for attempt in range(SYNC_RETRIES):
        try:
            result = _ssl_post(payload, timeout=90)
            status = result.get("status")
            if status == "success":
                return True, result.get("memory_id")
            errs = result.get("errors") or []
            print(f"❌ Sync not success for {filepath}: status={status} errors={errs}")
            return False, None
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504) and attempt < SYNC_RETRIES - 1:
                wait = 2 ** attempt
                print(f"  ⚠ HTTP {e.code} for {filepath}; retry in {wait}s")
                time.sleep(wait)
                continue
            print(f"❌ Failed to sync {filepath}: HTTP {e.code}")
            return False, None
        except Exception as e:
            last_err = e
            if attempt < SYNC_RETRIES - 1:
                wait = 2 ** attempt
                print(f"  ⚠ {filepath}: {e}; retry in {wait}s")
                time.sleep(wait)
                continue
            print(f"❌ Failed to sync {filepath}: {e}")
            return False, None
    print(f"❌ Failed to sync {filepath}: {last_err}")
    return False, None

def is_excluded(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    if any(seg.lower() in parts for seg in EXCLUDE_SEGMENTS):
        return True
    if any(sub in path.name for sub in EXCLUDE_NAME_SUBSTR):
        return True
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hygiene", action="store_true",
                        help="Re-upsert tagged notes even if hash unchanged (replace stacked copies).")
    parser.add_argument("--legacy-only", action="store_true",
                        help="With --hygiene, only records stored as a bare hash string.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print actions; do not call the orchestrator or write state.")
    args, _ = parser.parse_known_args()

    print("="*60)
    print(f"  BiOS Vault Memory Syncer v2 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.hygiene:
        print(f"  mode: hygiene legacy_only={args.legacy_only} dry_run={args.dry_run}")
    print("="*60)

    if not VAULT_ROOT.exists():
        print(f"❌ Error: Vault root not found at {VAULT_ROOT}")
        raise SystemExit(1)

    state = load_state()
    synced_count = 0
    skipped_count = 0
    error_count = 0
    untagged_count = 0
    deleted_count = 0
    by_partition = {}
    seen_paths = set()

    for root, dirs, files in os.walk(VAULT_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith('.')
                   and d.lower() not in EXCLUDE_SEGMENTS]

        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() not in EXTENSIONS:
                continue
            if is_excluded(file_path):
                continue

            rel_path = str(file_path.relative_to(VAULT_ROOT))
            seen_paths.add(rel_path)

            try:
                content = read_vault_file(file_path)
            except Exception as e:
                print(f"⚠ Could not read {rel_path}: {e}")
                error_count += 1
                continue

            # Only sync notes the tagger has processed + partitioned.
            if TAG_MARKER not in content:
                untagged_count += 1
                continue

            current_hash = compute_sha256(content)
            rec = file_record(state, rel_path)
            previous_hash = rec.get("hash")
            is_legacy = isinstance((state.get("files") or {}).get(rel_path), str)
            force = args.hygiene and (not args.legacy_only or is_legacy)

            if current_hash != previous_hash or force:
                partitions = extract_partitions(content)
                tags = extract_tags(content)
                prim = partitions[0] if partitions else "life"
                print(f"🔄 [{prim}] {rel_path}...")
                if args.dry_run:
                    print("   dry-run: would purge+upsert")
                    synced_count += 1
                    by_partition[prim] = by_partition.get(prim, 0) + 1
                    continue
                ok, memory_id = sync_to_gcp(content, rel_path, tags, partitions)
                if ok:
                    set_file_record(state, rel_path, current_hash, memory_id)
                    synced_count += 1
                    by_partition[prim] = by_partition.get(prim, 0) + 1
                    print(f"   ✅ Done.")
                    if synced_count % STATE_FLUSH_EVERY == 0:
                        save_state(state)
                else:
                    error_count += 1
            else:
                skipped_count += 1

    stale = [p for p in list((state.get("files") or {}).keys()) if p not in seen_paths]
    for rel_path in stale:
        print(f"🗑 missing from vault, purging {rel_path}...")
        if args.dry_run:
            print("   dry-run: would purge")
            deleted_count += 1
            continue
        if purge_source(rel_path):
            state["files"].pop(rel_path, None)
            deleted_count += 1
        else:
            error_count += 1

    if not args.dry_run:
        save_state(state)

    print("-" * 60)
    print(f"Summary: {synced_count} synced, {skipped_count} unchanged, "
          f"{deleted_count} purged, {untagged_count} untagged (skipped), "
          f"{error_count} errors.")
    if by_partition:
        dist = ", ".join(f"{k}={v}" for k, v in sorted(by_partition.items()))
        print(f"By partition: {dist}")
    print("=" * 60)
    if error_count:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
