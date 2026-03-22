#!/usr/bin/env python3
"""
BiOS Log Reviewer
Reads jarvis.log, extracts errors and improvement ideas,
pushes summary to CoPaw memory for Notion sync.
"""

import os
import re
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

LOG_FILE = Path.home() / "biomimetics" / "logs" / "jarvis.log"
COPAW_LOG = Path.home() / "biomimetics" / "logs" / "copaw.log"
COPAW_URL = "http://127.0.0.1:8088"
MAX_LOG_SIZE_MB = 50


def read_recent_logs(hours=24):
    """Read log entries from the last N hours."""
    if not LOG_FILE.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    entries = []

    with open(LOG_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Parse timestamp: "2026-03-21 16:30:00,123 [LEVEL] message"
            match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if match:
                try:
                    ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                    if ts >= cutoff:
                        entries.append(line)
                except ValueError:
                    pass
    return entries


def analyze_entries(entries):
    """Extract errors, warnings, and patterns."""
    errors = []
    warnings = []
    tool_calls = []
    tool_errors = []
    connection_errors = []

    for entry in entries:
        if "[ERROR]" in entry:
            errors.append(entry)
        elif "[WARNING]" in entry or "⚠️" in entry:
            warnings.append(entry)
        elif "TOOL_CALL:" in entry:
            tool_calls.append(entry)
        elif "TOOL_ERROR:" in entry:
            tool_errors.append(entry)
        elif "ConnectionClosed" in entry or "1011" in entry or "1008" in entry:
            connection_errors.append(entry)

    return {
        "errors": errors,
        "warnings": warnings,
        "tool_calls": tool_calls,
        "tool_errors": tool_errors,
        "connection_errors": connection_errors,
        "total_entries": len(entries),
    }


def generate_review(analysis):
    """Generate a human-readable review with improvement ideas."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Jarvis Log Review — {now}\n"]

    lines.append(f"**Period**: Last 24 hours")
    lines.append(f"**Total log entries**: {analysis['total_entries']}")
    lines.append(f"**Errors**: {len(analysis['errors'])}")
    lines.append(f"**Warnings**: {len(analysis['warnings'])}")
    lines.append(f"**Tool calls**: {len(analysis['tool_calls'])}")
    lines.append(f"**Tool errors**: {len(analysis['tool_errors'])}")
    lines.append(f"**Connection drops**: {len(analysis['connection_errors'])}")
    lines.append("")

    if analysis["errors"]:
        lines.append("## Errors\n")
        for e in analysis["errors"][:10]:
            lines.append(f"- `{e}`")
        lines.append("")

    if analysis["tool_errors"]:
        lines.append("## Tool Errors\n")
        for e in analysis["tool_errors"][:10]:
            lines.append(f"- `{e}`")
        lines.append("")

    if analysis["connection_errors"]:
        lines.append("## Connection Drops\n")
        lines.append("These indicate Gemini API server-side issues.")
        for e in analysis["connection_errors"][:5]:
            lines.append(f"- `{e}`")
        lines.append("")

    # Improvement ideas based on patterns
    ideas = []
    if len(analysis["connection_errors"]) > 3:
        ideas.append(
            "**Frequent connection drops**: Consider adding automatic reconnection logic to jarvis_daemon.py"
        )
    if len(analysis["tool_errors"]) > 2:
        ideas.append(
            "**Tool failures**: Review tool timeout settings and endpoint availability"
        )
    if len(analysis["errors"]) > 5:
        ideas.append(
            "**High error rate**: Investigate recurring error patterns for root cause"
        )

    if ideas:
        lines.append("## Improvement Ideas\n")
        for i, idea in enumerate(ideas, 1):
            lines.append(f"{i}. {idea}")
        lines.append("")

    return "\n".join(lines)


def push_to_memory(review_text):
    """Save review to CoPaw memory."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"jarvis-log-review-{timestamp}"

    try:
        resp = requests.put(
            f"{COPAW_URL}/api/agent/memory/{filename}",
            data=review_text,
            headers={"Content-Type": "text/plain"},
            timeout=10,
        )
        if resp.status_code < 300:
            print(f"✅ Review saved to memory: {filename}")
            return True
        else:
            print(f"⚠️  CoPaw returned {resp.status_code}: {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"❌ Failed to push to CoPaw: {e}")
        return False


def main():
    print(f"📋 BiOS Log Reviewer — {datetime.now().isoformat()}")

    entries = read_recent_logs(hours=24)
    print(f"  Found {len(entries)} log entries from last 24h")

    if not entries:
        print("  No entries to review.")
        return

    analysis = analyze_entries(entries)
    review = generate_review(analysis)

    print(f"  Errors: {len(analysis['errors'])}, Warnings: {len(analysis['warnings'])}")
    print(
        f"  Tool calls: {len(analysis['tool_calls'])}, Tool errors: {len(analysis['tool_errors'])}"
    )

    # Push to CoPaw memory
    if push_to_memory(review):
        # Clear log files after successful push — Notion is the repository
        for logfile in [LOG_FILE, COPAW_LOG]:
            if logfile.exists():
                with open(logfile, "w") as f:
                    f.write("")
        print(f"  🗑️  Log files cleared — review preserved in Notion")

    # Also print summary
    print("\n" + review)


if __name__ == "__main__":
    main()
