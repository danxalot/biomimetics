#!/usr/bin/env python3
"""Dual-harness MuninnDB conversation-turn loop (Claude Code + Grok TUI).

  inject  — UserPromptSubmit: recall session + prompt-relevant engrams
  track   — Stop / AgentResponse: remember the turn as a Hebbian engram

LOCAL Muninn only (127.0.0.1:8750). Does not touch GCP Muninn / MemU.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import time
from pathlib import Path

MUNINN_URL = os.environ.get("MUNINN_MCP_URL", "http://127.0.0.1:8750/mcp")
CRED_URL = "http://127.0.0.1:8089"
CRED_KEY_PATH = Path("/Users/danexall/biomimetics/secrets/credentials_api_key")
TURN_DIR = Path.home() / ".grok" / "muninn-turns"
INJECT_FILE = Path.home() / ".grok" / "muninn-inject.md"
INJECT_JSON = Path.home() / ".grok" / "muninn-inject.json"


def _token() -> str | None:
    env = os.environ.get("MUNINN_MCP_TOKEN")
    if env:
        return env.strip()
    try:
        key = CRED_KEY_PATH.read_text().strip()
        req = urllib.request.Request(
            f"{CRED_URL}/secrets/muninndb-token",
            headers={"X-API-Key": key},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            val = data.get("value") if isinstance(data, dict) else None
            return str(val).strip() if val else None
    except Exception:
        return None


def _call(token: str, tool: str, arguments: dict, timeout: float = 3.0) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        MUNINN_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _tool_text(resp: dict) -> str:
    try:
        items = (resp.get("result") or {}).get("content") or []
        if items and isinstance(items[0], dict):
            return (items[0].get("text") or "").strip()
    except Exception:
        pass
    return ""


def _first_str(d: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            inner = _first_str(v, keys)
            if inner:
                return inner
    return ""


def extract_prompt(evt: dict) -> str:
    return _first_str(
        evt,
        ("prompt", "userPrompt", "user_prompt", "text", "message"),
    )[:8000]


def extract_response(evt: dict) -> str:
    return _first_str(
        evt,
        ("response", "lastAssistantMessage", "assistantMessage", "output"),
    )[:12000]


def is_grok() -> bool:
    return bool(os.environ.get("GROK_HOOK_EVENT") or os.environ.get("GROK_SESSION_ID"))


def _sidecar_path(evt: dict) -> Path:
    session = (
        os.environ.get("GROK_SESSION_ID")
        or evt.get("sessionId")
        or evt.get("session_id")
        or "unknown"
    )
    prompt_id = evt.get("promptId") or evt.get("prompt_id") or "latest"
    TURN_DIR.mkdir(parents=True, exist_ok=True)
    return TURN_DIR / f"{session}_{prompt_id}.json"


def _pretty_muninn(text: str) -> str:
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except Exception:
        return text
    if isinstance(parsed, dict) and not parsed.get("memories") and parsed.get("total", 0) == 0:
        return ""
    memories = parsed.get("memories") if isinstance(parsed, dict) else None
    if not isinstance(memories, list):
        return text
    lines = []
    for mem in memories[:8]:
        if not isinstance(mem, dict):
            continue
        concept = (mem.get("concept") or "").strip()
        content = " ".join(str(mem.get("content") or "").split())
        if concept:
            lines.append(f"- **{concept}**")
            if content:
                lines.append(f"  {content[:500]}")
        elif content:
            lines.append(f"- {content[:500]}")
    return "\n".join(lines)


def _write_inject_file(context: str, prompt: str = "") -> None:
    try:
        INJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
        body = context.strip() if context.strip() else "_No Muninn engrams surfaced for this prompt._\n"
        INJECT_FILE.write_text(
            f"<!-- refreshed by UserPromptSubmit hook; local Muninn ACTIVATE -->\n{body}\n",
            encoding="utf-8",
        )
        INJECT_FILE.chmod(0o600)
        INJECT_JSON.write_text(
            json.dumps(
                {
                    "prompt": prompt,
                    "context": context.strip(),
                    "ts": time.time(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        INJECT_JSON.chmod(0o600)
    except Exception:
        pass


def activate_context(prompt: str) -> str:
    """Recall prompt-relevant local Muninn engrams. Empty string on miss/failure."""
    prompt = (prompt or "").strip()
    if not prompt:
        return ""
    token = _token()
    if not token:
        return ""

    where_text = _pretty_muninn(_tool_text(_call(token, "muninn_where_left_off", {"limit": 3})))

    phrases = [p.strip() for p in prompt.replace("?", " ").replace(".", " ").split() if len(p) > 3]
    if not phrases:
        phrases = [prompt[:80].strip()]
    recall_text = _pretty_muninn(
        _tool_text(
            _call(
                token,
                "muninn_recall",
                {"context": phrases[:5], "limit": 6, "threshold": 0.3, "mode": "balanced"},
            )
        )
    )

    parts = []
    if where_text:
        parts.append("[MuninnDB — Session continuity]\n" + where_text)
    if recall_text:
        parts.append("[MuninnDB — Relevant context]\n" + recall_text)
    return "\n\n".join(parts)


def inject(evt: dict) -> None:
    prompt = extract_prompt(evt)
    if not prompt:
        return
    if is_grok():
        try:
            _sidecar_path(evt).write_text(json.dumps({"prompt": prompt}), encoding="utf-8")
        except Exception:
            pass

    context = activate_context(prompt)
    _write_inject_file(context, prompt=prompt)

    if not context:
        return

    # Claude Code honours {"context": ...}. Stock Grok discards this stdout;
    # muninn_chat_proxy.py splices the same blob into the /v1/responses body.
    print(
        json.dumps(
            {
                "continue": True,
                "context": context,
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                },
            }
        )
    )


def track(evt: dict) -> None:
    # Grok fires an extra observe-only Stop at session teardown.
    reason = evt.get("reason")
    if reason and reason not in ("end_turn", None, ""):
        return
    if evt.get("subagentType") or evt.get("subagent_type"):
        return

    prompt = extract_prompt(evt)
    response = extract_response(evt)
    if is_grok() and (not prompt or not response):
        try:
            side = json.loads(_sidecar_path(evt).read_text(encoding="utf-8"))
            prompt = prompt or side.get("prompt", "")
        except Exception:
            pass
        if not response:
            response = extract_response(evt)

    if not prompt or not response:
        return

    token = _token()
    if not token:
        return

    concept = f"Conversation turn: {prompt.splitlines()[0][:60]}"
    content = f"Prompt: {prompt}\n\nResponse: {response}"
    _call(
        token,
        "muninn_remember",
        {
            "concept": concept,
            "content": content,
            "tags": ["conversation-turn", "hebbian-memory", "agent-response"],
            "confidence": 1.0,
        },
    )
    try:
        p = _sidecar_path(evt)
        if p.exists():
            p.unlink()
    except Exception:
        pass


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        raw = sys.stdin.read()
        evt = json.loads(raw) if raw.strip() else {}
        if not isinstance(evt, dict):
            evt = {}
    except Exception:
        return 0
    try:
        if mode == "inject":
            inject(evt)
        elif mode == "track":
            track(evt)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
