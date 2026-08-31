#!/usr/bin/env python3
"""Launch the real grok binary with the Muninn chat proxy in front of xAI.

The proxy is a child of this wrapper (or an existing session-scoped instance)
and exits when this process exits. Not a detached daemon.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROXY = Path(__file__).resolve().parent / "muninn_chat_proxy.py"
PORT = os.environ.get("MUNINN_GROK_PROXY_PORT", "18750")
PROXY_URL = f"http://127.0.0.1:{PORT}/v1"


def real_grok() -> str:
    env = os.environ.get("GROK_REAL_BIN")
    if env and Path(env).is_file():
        return env
    link = Path.home() / ".grok" / "bin" / "grok"
    if link.exists():
        resolved = link.resolve()
        name = resolved.name
        if resolved.is_file() and "grok_with_muninn" not in name and "muninn_chat_proxy" not in name:
            return str(resolved)
    downloads = Path.home() / ".grok" / "downloads"
    cands = sorted(downloads.glob("grok-*-macos-*")) if downloads.is_dir() else []
    if cands:
        return str(cands[-1])
    print("grok_with_muninn: could not locate the real grok binary", file=sys.stderr)
    raise SystemExit(127)


def main() -> int:
    grok = real_grok()
    if os.environ.get("GROK_MUNINN_PROXY_ACTIVE") == "1":
        os.execv(grok, [grok, *sys.argv[1:]])

    rc = subprocess.call(
        [sys.executable, str(PROXY), "ensure", "--parent-pid", str(os.getpid())],
    )
    if rc != 0:
        print("grok_with_muninn: muninn chat proxy failed to start", file=sys.stderr)
        return rc or 1

    env = os.environ.copy()
    env["GROK_MUNINN_PROXY_ACTIVE"] = "1"
    env["GROK_CLI_CHAT_PROXY_BASE_URL"] = PROXY_URL
    env["GROK_REAL_BIN"] = grok
    return subprocess.call([grok, *sys.argv[1:]], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
