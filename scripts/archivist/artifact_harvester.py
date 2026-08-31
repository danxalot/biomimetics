#!/usr/bin/env python3
"""
BiOS Artifact Harvester
Silently scrapes logs and artifacts from development tools and stages them
for long-term memory ingestion. Incremental via SHA-256 of the source file.
"""

import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime

HOME = Path.home()
STAGING_ROOT = HOME / "biomimetics" / ".staging" / "raw_dev_artifacts"
STATE_FILE = HOME / ".arca" / "harvest_state.json"
MAX_COPY_BYTES = 2_000_000
GROK_LAST_MESSAGES = 24  # last user+assistant turns only, not full jsonl

SCRAPE_TARGETS = [
    {"name": "claude", "globs": [str(HOME / ".claude" / "sessions" / "*.json")]},
    {
        "name": "zed",
        "globs": [str(HOME / "Library" / "Application Support" / "Zed" / "conversations" / "*.json")],
    },
    {
        "name": "bios_artifacts",
        "globs": [str(HOME / "biomimetics" / "docs" / "projects" / "bios" / "artifacts" / "*")],
    },
    {
        "name": "antigravity",
        "globs": [str(HOME / ".gemini" / "antigravity" / "brain" / "*" / "*.md")],
    },
    {
        "name": "grok",
        "globs": [str(HOME / ".grok" / "sessions" / "**" / "chat_history.jsonl")],
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"files": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict):
                t = c.get("text") or c.get("content") or ""
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts)
    if isinstance(content, dict):
        return _text_of(content.get("text") or content.get("content") or "")
    return ""


def compact_grok_jsonl(src: Path) -> bytes:
    """Keep last N user/assistant messages. Drops reasoning/tool dumps."""
    msgs = []
    with src.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict) or obj.get("type") not in ("user", "assistant"):
                continue
            text = " ".join(_text_of(obj.get("content")).split())
            if not text:
                continue
            msgs.append({"type": obj["type"], "content": text[:4000]})
    msgs = msgs[-GROK_LAST_MESSAGES:]
    payload = {"source": "grok", "source_path": str(src), "messages": msgs}
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def iter_matches(pattern: str):
    # Path.glob needs the pattern relative to a root; use glob.glob recursive.
    import glob

    return [Path(p) for p in glob.glob(pattern, recursive=True)]


def harvest():
    print("=" * 60)
    print(f"🚜 BiOS Artifact Harvester - {datetime.now().isoformat()}")
    print("=" * 60)

    today = datetime.now().strftime("%Y-%m-%d")
    state = load_state()
    copied = 0
    skipped = 0
    too_big = 0

    for target in SCRAPE_TARGETS:
        name = target["name"]
        staging_dir = STAGING_ROOT / name / today
        staging_dir.mkdir(parents=True, exist_ok=True)

        files = []
        for pattern in target["globs"]:
            files.extend(iter_matches(pattern))
        files = [p for p in files if p.is_file()]
        if not files:
            print(f"  Empty: {name}")
            continue

        print(f"  Scanning {len(files)} items from {name}...")
        for p in files:
            key = str(p)
            try:
                digest = sha256_file(p)
            except Exception as e:
                print(f"    ⚠️  Hash failed {p.name}: {e}")
                continue
            if state.get("files", {}).get(key) == digest:
                skipped += 1
                continue
            if p.name.startswith("MASTER_") or "MASTER_" in p.name:
                skipped += 1
                continue
            dest = staging_dir / p.name
            if dest.exists():
                dest = staging_dir / f"{p.parent.name}_{p.name}"
            try:
                if name == "grok" and p.suffix.lower() == ".jsonl":
                    dest = dest.with_suffix(".json")
                    dest.write_bytes(compact_grok_jsonl(p))
                else:
                    if p.stat().st_size > MAX_COPY_BYTES:
                        too_big += 1
                        print(f"    ⚠️  Skip large {p.name} ({p.stat().st_size} bytes)")
                        continue
                    shutil.copy2(p, dest)
                state.setdefault("files", {})[key] = digest
                copied += 1
            except Exception as e:
                print(f"    ⚠️  Failed to copy {p.name}: {e}")

    save_state(state)
    print("-" * 60)
    print(f"✅ Harvest complete. copied={copied} unchanged={skipped} oversized={too_big}")
    print(f"   Staged in {STAGING_ROOT}")
    print("=" * 60)


if __name__ == "__main__":
    harvest()
