#!/usr/bin/env python3
"""Google Drive File Stream I/O with deadlock retries (Errno 11)."""

from __future__ import annotations

import time
from pathlib import Path

VAULT_ROOT = Path("/Users/danexall/Google Drive/My Drive/Obsidian-life")
READ_RETRIES = 12
WRITE_RETRIES = 12


def is_deadlock(exc: BaseException) -> bool:
    errno = getattr(exc, "errno", None)
    return errno == 11 or "deadlock" in str(exc).lower()


def read_text(path: Path, retries: int = READ_RETRIES) -> str:
    last: BaseException | None = None
    for attempt in range(retries):
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            last = e
            if is_deadlock(e) and attempt < retries - 1:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise
    raise last  # type: ignore[misc]


def write_text(path: Path, content: str, retries: int = WRITE_RETRIES) -> None:
    import os
    import tempfile
    import shutil

    path.parent.mkdir(parents=True, exist_ok=True)
    last: BaseException | None = None
    for attempt in range(retries):
        try:
            path.write_text(content, encoding="utf-8")
            return
        except OSError as e:
            last = e
            if is_deadlock(e) and attempt < retries - 1:
                time.sleep(0.8 * (attempt + 1))
                continue
            if is_deadlock(e):
                fd, tmp = tempfile.mkstemp(suffix=path.suffix)
                os.close(fd)
                try:
                    Path(tmp).write_text(content, encoding="utf-8")
                    shutil.copy2(tmp, path)
                    return
                except Exception as e2:
                    last = e2
                finally:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
            raise
    raise last  # type: ignore[misc]


def land_architecture_note(filename: str, body: str) -> Path:
    """Write a condensed artifact into the GDrive vault (L2 shadow).

    Leaves the LLM_TAGGED marker off so the nightly tagger can partition it.
    """
    dest = VAULT_ROOT / "bios" / "architecture" / "artifacts" / filename
    write_text(dest, body if body.endswith("\n") else body + "\n")
    return dest
