#!/usr/bin/env python3
"""
Daily GCP Muninn → MemU assimilation (non-transient engrams).

Calls memory-orchestrator operation=consolidate. Does not touch local Muninn.
Schedule via Cloud Scheduler (preferred) or launchd invoking this script.

Usage:
  python3 scripts/memory/daily_muninn_to_memu.py
  python3 scripts/memory/daily_muninn_to_memu.py --dry-run
  python3 scripts/memory/daily_muninn_to_memu.py --threshold 0.5 --limit 200
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime

GCP_GATEWAY_URL = (
    "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily Muninn→MemU consolidate via GCP orchestrator")
    ap.add_argument("--gateway", default=GCP_GATEWAY_URL)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--auto-page", action="store_true", default=True,
                    help="Walk offsets until done (default on)")
    ap.add_argument("--no-auto-page", action="store_true",
                    help="Single batch only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--user-id", default="default")
    args = ap.parse_args()

    payload = {
        "operation": "consolidate",
        "threshold": args.threshold,
        "limit": args.limit,
        "batch": args.batch,
        "offset": args.offset,
        "auto_page": False if args.no_auto_page else True,
        "max_batches": 8,
        "time_budget_s": 240,
        "dry_run": args.dry_run,
        "user_id": args.user_id,
    }
    print(f"[{datetime.now().isoformat(timespec='seconds')}] POST consolidate → {args.gateway}")
    print(f"  threshold={args.threshold} limit={args.limit} dry_run={args.dry_run}")

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        args.gateway,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
        # macOS Python.org builds sometimes lack system CAs; fall back carefully
        try:
            import certifi  # noqa: F401
        except Exception:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
            body = resp.read().decode()
            result = json.loads(body)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:500]}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    status = result.get("status")
    if status in ("success", "partial", "no_action"):
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
