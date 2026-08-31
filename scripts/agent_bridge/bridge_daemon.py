#!/usr/bin/env python3
"""
BiOS Agent Bridge — a closed verification loop between the Cowork architect and
THIS Mac. The architect (which has no direct network/shell access to this box)
drops a job file in the inbox; this daemon runs it here, with full local access,
and writes the result back where the architect can read it through the shared
folder. No browser, no computer-use.

Flow:  inbox/<id>.job.json   ->  [run here]  ->  outbox/<id>.result.json
Job:    {"id": "...", "cmd": "curl -s localhost:8089/health", "cwd": "...", "timeout": 30}
Result: {"id","cmd","cwd","exit","stdout","stderr","ts"}

Guardrails (backstops — the architect still authors and owns each command):
  * per-job timeout (default 60s, hard cap 900s)
  * stdout/stderr capped at 100 KB
  * catastrophic-command denylist (rm -rf /, mkfs, dd of=/dev, shutdown, fork bomb...)
  * every job appended to bridge.log (full audit trail)
  * only ever executes files found in its own inbox
"""
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

BRIDGE = Path("/Users/danexall/biomimetics/.agent_bridge")
INBOX, OUTBOX, DONE, LOG = BRIDGE / "inbox", BRIDGE / "outbox", BRIDGE / "done", BRIDGE / "bridge.log"

POLL_SECONDS = 3
MAX_OUTPUT = 100_000
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 900

DENY = [
    r"rm\s+-rf\s+/\s", r"rm\s+-rf\s+/$", r"rm\s+-rf\s+/\*", r"rm\s+-rf\s+~",
    r"\bmkfs\b", r"dd\s+.*of=/dev/", r">\s*/dev/sd",
    r"\bshutdown\b", r"\breboot\b", r"\bhalt\b", r":\(\)\s*\{\s*:\s*\|",
]


def log(msg: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")


def denied(cmd: str):
    return next((p for p in DENY if re.search(p, cmd)), None)


def run_job(job_path: Path):
    try:
        job = json.loads(job_path.read_text())
    except Exception as e:
        log(f"bad job {job_path.name}: {e}")
        return
    jid = str(job.get("id") or job_path.stem)
    cmd = job.get("cmd", "")
    cwd = job.get("cwd", "/Users/danexall/biomimetics")
    timeout = min(int(job.get("timeout", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
    result = {"id": jid, "cmd": cmd, "cwd": cwd, "ts": datetime.now().isoformat()}

    d = denied(cmd)
    if d:
        result.update(exit=126, stdout="", stderr=f"BLOCKED by guardrail: /{d}/")
        log(f"BLOCKED {jid}: {cmd}")
    else:
        log(f"RUN {jid}: {cmd}")
        try:
            p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                               text=True, timeout=timeout)
            result.update(exit=p.returncode,
                          stdout=p.stdout[:MAX_OUTPUT], stderr=p.stderr[:MAX_OUTPUT])
        except subprocess.TimeoutExpired:
            result.update(exit=124, stdout="", stderr=f"timeout after {timeout}s")
        except Exception as e:  # noqa: BLE001
            result.update(exit=1, stdout="", stderr=str(e))
        log(f"DONE {jid} exit={result['exit']}")

    OUTBOX.mkdir(parents=True, exist_ok=True)
    (OUTBOX / f"{jid}.result.json").write_text(json.dumps(result, indent=2))
    DONE.mkdir(parents=True, exist_ok=True)
    try:
        job_path.rename(DONE / job_path.name)
    except Exception:
        job_path.unlink(missing_ok=True)


def main():
    for d in (INBOX, OUTBOX, DONE):
        d.mkdir(parents=True, exist_ok=True)
    log("bridge started")
    while True:
        for job in sorted(INBOX.glob("*.job.json")):
            run_job(job)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
