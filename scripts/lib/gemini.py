#!/usr/bin/env python3
"""Shared Gemini caller for the archivist pipeline.

Uses the Credentials Server only (no local key files). TLS via certifi.

Auth is the Google AI Studio unpaid key (`google-ai-studio-key`), never
`google-billing-api-key`. Both Flash-Lite models have a 500/day free tier.

  MODEL_VOLUME (3.1 Flash Lite) — tagging, email classification, short JSON
  MODEL_SYNTH  (3.5 Flash Lite) — condensation / master-doc rewrite
  Thinking is left at the model default (free-tier budget is fine).
"""

from __future__ import annotations

import json
import ssl
import urllib.request
from typing import Optional

MODEL_VOLUME = "gemini-3.1-flash-lite-preview"
MODEL_SYNTH = "gemini-3.5-flash-lite"

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


def fetch_api_key() -> Optional[str]:
    from lib.creds import get

    # Pin the Studio unpaid key. Do not search substring "gemini" — that misses
    # google-ai-studio-key and must never resolve google-billing-api-key.
    for name in ("google-ai-studio-key", "gemini-api-key", "google-api-key"):
        try:
            val = get(name)
        except Exception:
            val = None
        if val and str(val).strip():
            return str(val).strip()
    return None


def invoke(
    user_content: str,
    *,
    system: Optional[str] = None,
    model: str = MODEL_VOLUME,
    temperature: float = 0.2,
    json_mode: bool = False,
    timeout: int = 120,
) -> Optional[str]:
    """Return model text, or None on failure. Never logs the API key."""
    api_key = fetch_api_key()
    if not api_key:
        raise RuntimeError("gemini-api-key unavailable from credentials server")

    gen: dict = {"temperature": temperature, "topP": 0.95}
    if json_mode:
        gen["responseMimeType"] = "application/json"

    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": gen,
    }
    if system:
        payload["system_instruction"] = {"parts": [{"text": system}]}

    url = GEMINI_URL.format(model=model)
    data = json.dumps(payload).encode("utf-8")
    ctx = _ssl_context()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))
        return response_data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None
