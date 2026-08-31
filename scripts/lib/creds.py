#!/usr/bin/env python3
"""
BiOS shared credentials client — the single robust path to the local
Credentials Server (Azure Key Vault backed, :8089).

Why this exists: scripts kept reimplementing the cred fetch, each fragile — a
one-shot 5s call to `localhost` that stalled the whole nightly run when the
server did a slow Azure round-trip. This centralises it:

  * 127.0.0.1 (the server binds IPv4 only) — never `localhost` (avoids ::1 hangs)
  * retry + generous per-attempt timeout (Azure KV calls can stall 30-90s)
  * name self-discovery by substring, so callers never hardcode exact spellings
    (e.g. the ~6 `cloudflare*` tokens, or arca_oci_key vs arca-oci-key)

Secret VALUES are only ever returned to the immediate caller — never logged.
"""
import json
import time
import urllib.request

CRED_SERVER = "http://127.0.0.1:8089"
API_KEY_PATH = "/Users/danexall/biomimetics/secrets/credentials_api_key"


def _master_key() -> str:
    with open(API_KEY_PATH) as f:
        return f.read().strip()


def _get_json(path: str, key: str):
    req = urllib.request.Request(f"{CRED_SERVER}{path}", headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize_names(data) -> list:
    """The /secrets endpoint may return a bare list, a dict wrapper, or a map."""
    if isinstance(data, list):
        return [x if isinstance(x, str) else x.get("name", "") for x in data]
    if isinstance(data, dict):
        for k in ("secrets", "names", "keys"):
            v = data.get(k)
            if isinstance(v, list):
                return [x if isinstance(x, str) else x.get("name", "") for x in v]
        return list(data.keys())
    return []


def _retry(fn, retries=4, backoff=3):
    last = None
    for i in range(retries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries - 1:
                time.sleep(backoff * (i + 1))
    raise last


def list_names() -> list:
    key = _master_key()
    return _retry(lambda: _normalize_names(_get_json("/secrets", key)))


def discover(substring: str) -> list:
    s = substring.lower()
    return [n for n in list_names() if s in n.lower()]


def get(name: str):
    key = _master_key()

    def _fetch():
        data = _get_json(f"/secrets/{name}", key)
        return data.get("value") if isinstance(data, dict) else data
    return _retry(_fetch)


def get_first(substring: str, prefer=()):
    """Discover secrets matching `substring`; return the value of the best match.
    `prefer` is an ordered list of extra substrings to rank by (e.g. 'worker')."""
    names = discover(substring)
    if not names:
        return None
    for p in prefer:
        for n in names:
            if p.lower() in n.lower():
                return get(n)
    return get(names[0])
