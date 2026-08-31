#!/usr/bin/env python3
"""Split oversized Obsidian notes into heading-sized chunks before memory sync.

Layer 2 (the vault) is the bound: MemU stores chunks, Muninn only gets a catalog
card. A note larger than CHUNK_CHARS is replaced by a stub index plus a folder
of section files. Original body is archived next to the folder.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.vault_io import VAULT_ROOT, read_text, write_text  # noqa: E402

CHUNK_CHARS = 12000  # must match tagged_memory_sync.MAX_CHARS
TAG_MARKER = "<!-- LLM_TAGGED -->"
HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.M)


def _split_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[: end + 5], text[end + 5 :]
    return "", text


def _slug(heading: str, idx: int) -> str:
    raw = re.sub(r"\[\[|\]\]|#", "", heading)
    raw = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_")
    raw = raw[:50] or f"section_{idx:02d}"
    return f"{idx:02d}_{raw}"


def _partition_line(text: str) -> str:
    found = re.findall(r"(?<!\S)#partition/[a-zA-Z0-9_/]+", text)
    return " ".join(dict.fromkeys(found)) or "#partition/bios"


def chunk_note(path: Path) -> int:
    text = read_text(path)
    if len(text) <= CHUNK_CHARS:
        return 0
    fm, body = _split_frontmatter(text)
    matches = list(HEADING.finditer(body))
    if not matches:
        return 0

    sections: list[tuple[str, str]] = []
    preamble = body[: matches[0].start()].strip()
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        title = m.group(2).strip()
        block = body[m.start() : end].strip()
        sections.append((title, block))

    folder = path.with_suffix("")
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / ".archive" / f"{path.stem}.full.md"
    write_text(archive, text if text.endswith("\n") else text + "\n")

    part = _partition_line(text)
    links: list[str] = []
    if preamble:
        intro_name = "00_Preamble.md"
        intro = (
            f"{fm}\n# {path.stem} — Preamble\n\n{part}\n\n{preamble}\n\n{TAG_MARKER}\n"
        )
        write_text(folder / intro_name, intro)
        links.append(f"- [[{folder.name}/{intro_name[:-3]}|Preamble]]")

    wrote = 0
    buf_title = ""
    buf = ""
    flushed = 0

    def flush():
        nonlocal buf, buf_title, flushed, wrote
        if not buf.strip():
            return
        flushed += 1
        slug = _slug(buf_title or f"section_{flushed}", flushed)
        fname = f"{slug}.md"
        note = f"{fm}\n# {buf_title or path.stem}\n\n{part}\n\n{buf.strip()}\n\n{TAG_MARKER}\n"
        write_text(folder / fname, note)
        links.append(f"- [[{folder.name}/{slug}|{buf_title or slug}]]")
        wrote += 1
        buf, buf_title = "", ""

    for title, block in sections:
        pieces = [block]
        if len(block) > CHUNK_CHARS:
            pieces = []
            step = CHUNK_CHARS
            for start in range(0, len(block), step):
                pieces.append(block[start : start + step])
        for i, piece in enumerate(pieces):
            label = title if i == 0 else f"{title} ({i + 1})"
            if buf and len(buf) + len(piece) > CHUNK_CHARS:
                flush()
            if not buf:
                buf_title = label
            buf += ("\n\n" if buf else "") + piece
            if len(buf) >= CHUNK_CHARS:
                flush()
    flush()

    stub = (
        f"{fm}\n"
        f"# {path.stem}\n\n"
        f"{part}\n\n"
        "> Oversized note split into Obsidian chunks before memory sync. "
        "Full original is archived beside this folder and is not synced to memory.\n\n"
        "## Sections\n\n"
        + "\n".join(links)
        + f"\n\n{TAG_MARKER}\n"
    )
    write_text(path, stub)
    return wrote


def _is_chunk_dir(path: Path) -> bool:
    return (path / ".archive").is_dir() or (path / "00_Preamble.md").is_file()


def main() -> int:
    n = 0
    candidates = []
    for path in VAULT_ROOT.rglob("*.md"):
        parts = {p.lower() for p in path.parts}
        if parts & {"_generated", ".archive", "obsidian_staging", "staging"}:
            continue
        if path.name.endswith(".full.md"):
            continue
        if "Emails" in path.parts or path.parent.name == "artifacts":
            continue
        if _is_chunk_dir(path.parent):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size <= CHUNK_CHARS:
            continue
        candidates.append(path)
    for path in candidates:
        if _is_chunk_dir(path.parent):
            continue
        wrote = chunk_note(path)
        if wrote:
            print(f"chunked {path.relative_to(VAULT_ROOT)} -> {wrote} sections")
            n += 1
    print(f"chunked_notes={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
