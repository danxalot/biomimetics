#!/usr/bin/env python3
"""Ensure MemU Qdrant payload indexes exist so purge/upsert can filter by source.

MemU /purge uses Filter on metadata.source. Without a keyword index Qdrant
returns 400 and vault upserts stack copies instead of replacing them.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.creds import get  # noqa: E402

COLLECTION = "memu_archive_1536"
DEFAULT_URL = (
    "https://bfc3f711-81d4-43c6-b7bb-f58c99684d70.eu-west-2-0.aws.cloud.qdrant.io"
)

# Fields the vault sync / purge path actually filters on.
INDEXES = (
    ("metadata.source", "keyword"),
    ("metadata.partition_primary", "keyword"),
    ("metadata.source_system", "keyword"),
    ("metadata.tagged", "bool"),
)


def _ssl():
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


def main() -> int:
    url = (get("qdrant_endpoint") or get("qdrant_endpoint_claws") or DEFAULT_URL).rstrip("/")
    key = (get("qdrant_api_key") or "").strip()
    if not key:
        print("ERROR: qdrant_api_key missing from credentials server")
        return 1

    ctx = _ssl()

    def qreq(method: str, path: str, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "api-key": key},
        )
        try:
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                raw = resp.read().decode() or "{}"
                return resp.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:800]

    status, info = qreq("GET", f"/collections/{COLLECTION}")
    if status != 200:
        print(f"ERROR: GET collection {status}: {info}")
        return 1
    result = info.get("result") or {}
    schema = result.get("payload_schema") or {}
    print(f"collection={COLLECTION} points={result.get('points_count')} existing_indexes={list(schema)}")

    created = 0
    for field, schema_type in INDEXES:
        current = schema.get(field) or {}
        if isinstance(current, dict) and current.get("data_type") == schema_type:
            print(f"  present {field} ({schema_type})")
            continue
        st, body = qreq(
            "PUT",
            f"/collections/{COLLECTION}/index",
            {"field_name": field, "field_schema": schema_type, "wait": True},
        )
        ok = st in (200, 201) or (isinstance(body, dict) and body.get("status") == "ok")
        print(f"  create {field} {schema_type} -> http={st} ok={ok}")
        if not ok:
            print(f"    {body}")
            return 1
        created += 1

    st, info2 = qreq("GET", f"/collections/{COLLECTION}")
    schema2 = ((info2.get("result") or {}).get("payload_schema") or {}) if isinstance(info2, dict) else {}
    print("payload_schema:")
    for k, v in sorted(schema2.items()):
        dt = v.get("data_type") if isinstance(v, dict) else v
        pts = v.get("points") if isinstance(v, dict) else None
        print(f"  {k}: {dt} points={pts}")
    print(f"created={created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
