#!/usr/bin/env python3
"""
BiOS Overview Generator (Layer 4 — the self-building wiki)

Reads the partitioned Obsidian vault and REGENERATES the navigable overview:
  - _generated/INDEX.md               top-level map + partition counts
  - _generated/MOC_<partition>.md     one Map-of-Content per top partition
  - _generated/LIFE_LEGAL_TRACKER.md  the high-stakes legal/ombudsman/SAR tracker

Everything here is DERIVED and rebuilt each run. These files are state, never
intent — every one is stamped AUTO-GENERATED. Hand edits are overwritten.
The sync excludes _generated/, so this never feeds back into memory.
"""

import os
import sys
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

_SCRIPTS = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from lib.vault_io import read_text, write_text  # noqa: E402

VAULT_ROOT = Path("/Users/danexall/Google Drive/My Drive/Obsidian-life")
OUT_DIR = VAULT_ROOT / "_generated"
EXTENSIONS = {".md", ".markdown"}
EXCLUDE_SEGMENTS = {"obsidian_staging", "staging", ".archive", "_generated"}
EXCLUDE_NAME_SUBSTR = ("MASTER_",)

TOP_PARTITIONS = ["life", "arca", "bios", "grants", "pythia"]

STAMP = ("> **AUTO-GENERATED — do not edit.** Rebuilt by generate_overview.py.\n"
         "> Source of truth is the vault notes below; this file is a derived view.\n"
         "> Generated: {ts}\n")


def is_excluded(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if parts & EXCLUDE_SEGMENTS:
        return True
    return any(sub in path.name for sub in EXCLUDE_NAME_SUBSTR)


def extract_partitions(content: str) -> list:
    found = re.findall(r"(?<!\S)#partition/([a-zA-Z0-9_/]+)", content)
    seen, out = set(), []
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def parse_frontmatter(content: str) -> dict:
    meta = {}
    m = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip()
    return meta


def note_record(path: Path, content: str) -> dict:
    meta = parse_frontmatter(content)
    parts = extract_partitions(content)
    # most-specific partition (longest path) drives placement
    primary = max(parts, key=lambda s: s.count("/")) if parts else "life"
    title = meta.get("subject") or meta.get("title") or path.stem.replace("_", " ")
    return {
        "stem": path.stem,
        "title": title.strip().strip('"[]'),
        "date": meta.get("date", "")[:10],
        "status": meta.get("status", ""),
        "partitions": parts,
        "primary": primary,
        "top": (parts[0].split("/")[0] if parts else "life"),
    }


def collect() -> list:
    records = []
    for root, dirs, files in os.walk(VAULT_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".")
                   and d.lower() not in EXCLUDE_SEGMENTS]
        for f in files:
            fp = Path(root) / f
            if fp.suffix.lower() not in EXTENSIONS or is_excluded(fp):
                continue
            try:
                content = read_text(fp)
            except Exception:
                continue
            if extract_partitions(content):
                records.append(note_record(fp, content))
    return records


def link(stem: str) -> str:
    return f"[[{stem}]]"


def write(path: Path, body: str):
    write_text(path, body)


def build_moc(top: str, recs: list, ts: str) -> str:
    group = defaultdict(list)
    for r in recs:
        group[r["primary"]].append(r)
    lines = [f"# {top.capitalize()} — Map of Content\n", STAMP.format(ts=ts), ""]
    lines.append(f"_{len(recs)} notes across {len(group)} sub-partitions._\n")
    for sub in sorted(group):
        lines.append(f"\n## #{'partition/' + sub}\n")
        for r in sorted(group[sub], key=lambda x: x["date"], reverse=True):
            date = f"`{r['date']}` " if r["date"] else ""
            status = f" — _{r['status']}_" if r["status"] else ""
            lines.append(f"- {date}{link(r['stem'])} {r['title']}{status}")
    return "\n".join(lines) + "\n"


def build_legal_tracker(recs: list, ts: str) -> str:
    legal = [r for r in recs if any(p.startswith("life/legal") for p in r["partitions"])]
    lines = [
        "# Life / Legal Tracker — Ombudsman, Complaints & SAR\n",
        STAMP.format(ts=ts), "",
        "> Highest-stakes partition. This is a derived index of every note tagged "
        "`#partition/life/legal*`. Deadlines and case status are surfaced here so "
        "nothing is lost. Add case-level intent to the notes themselves, not here.\n",
        f"\n_{len(legal)} legal notes._\n",
    ]
    sar = [r for r in legal if any("sar" in p for p in r["partitions"])]
    if sar:
        lines.append("\n## SAR responses\n")
        for r in sorted(sar, key=lambda x: x["date"], reverse=True):
            date = f"`{r['date']}` " if r["date"] else ""
            lines.append(f"- {date}{link(r['stem'])} {r['title']}")
    lines.append("\n## All legal / complaint / ombudsman notes\n")
    for r in sorted(legal, key=lambda x: x["date"], reverse=True):
        date = f"`{r['date']}` " if r["date"] else ""
        status = f" — _{r['status']}_" if r["status"] else ""
        lines.append(f"- {date}{link(r['stem'])} {r['title']}{status}")
    return "\n".join(lines) + "\n"


def build_index(recs: list, counts: dict, ts: str) -> str:
    lines = ["# BiOS Knowledge Index\n", STAMP.format(ts=ts), "",
             f"_{len(recs)} partitioned notes total._\n", "\n## Partitions\n"]
    for top in TOP_PARTITIONS:
        n = counts.get(top, 0)
        lines.append(f"- **{top}** — {n} notes → [[MOC_{top}]]")
    lines.append("\n## Trackers\n")
    lines.append("- [[LIFE_LEGAL_TRACKER]] — ombudsman / complaints / SAR")
    return "\n".join(lines) + "\n"


def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    recs = collect()
    by_top = defaultdict(list)
    for r in recs:
        by_top[r["top"]].append(r)
    counts = {t: len(v) for t, v in by_top.items()}

    for top in TOP_PARTITIONS:
        write(OUT_DIR / f"MOC_{top}.md", build_moc(top, by_top.get(top, []), ts))
    write(OUT_DIR / "LIFE_LEGAL_TRACKER.md", build_legal_tracker(recs, ts))
    write(OUT_DIR / "INDEX.md", build_index(recs, counts, ts))

    dist = ", ".join(f"{t}={counts.get(t,0)}" for t in TOP_PARTITIONS)
    print(f"Overview regenerated: {len(recs)} notes [{dist}] -> {OUT_DIR}")


if __name__ == "__main__":
    main()
