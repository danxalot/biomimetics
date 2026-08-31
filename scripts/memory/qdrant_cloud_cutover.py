#!/usr/bin/env python3
"""
Qdrant Cloud cutover for GCP MemU (MemU-only — never Muninn).

What "cutover" means
--------------------
MemU currently may point at a temporary Qdrant on the muninn-global VM NAT
(http://104.198.54.178:6333). Product intent is Qdrant *Cloud*:
  https://<cluster-id>.<region>.aws.cloud.qdrant.io
  collection memu_archive_1536 (1536-dim, cosine)

This script:
  1. Loads API key (+ optional URL) from gcloud Secret Manager / env / credentials server
  2. Validates Cloud connectivity (list collections)
  3. Ensures collection memu_archive_1536 exists (1536, cosine)
  4. Optionally scrolls points from the old (VM) Qdrant and upserts into Cloud
  5. Prints the gcloud commands to re-point Cloud Run MemU (does NOT auto-redeploy
     unless --apply-memu is set)

Usage
-----
  # Dry validate cloud (default URL from docs)
  python3 scripts/memory/qdrant_cloud_cutover.py --check

  # Create collection + migrate from VM Qdrant, then update MemU env
  python3 scripts/memory/qdrant_cloud_cutover.py --migrate --apply-memu

  # Custom cloud URL
  QDRANT_CLOUD_URL=https://....aws.cloud.qdrant.io \\
    python3 scripts/memory/qdrant_cloud_cutover.py --check --migrate --apply-memu

Requires: qdrant-client, gcloud auth for arca-471022
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.request
from typing import Optional

DEFAULT_CLOUD_URL = (
    "https://bfc3f711-81d4-43c6-b7bb-f58c99684d70.eu-west-2-0.aws.cloud.qdrant.io"
)
DEFAULT_VM_URL = "http://104.198.54.178:6333"
COLLECTION = "memu_archive_1536"
DIMS = 1536
PROJECT = "arca-471022"
REGION = "us-central1"
MEMU_SERVICE = "memu"


def _gcloud_secret(name: str) -> Optional[str]:
    try:
        out = subprocess.check_output(
            [
                "gcloud", "secrets", "versions", "access", "latest",
                f"--secret={name}", f"--project={PROJECT}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip() or None
    except Exception:
        return None


def _cred_server_secret(name: str) -> Optional[str]:
    key_path = os.path.expanduser("~/biomimetics/secrets/credentials_api_key")
    if not os.path.isfile(key_path):
        return None
    api_key = open(key_path).read().strip()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:8089/secrets/{name}",
            headers={"X-API-Key": api_key},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        return (data.get("value") or data.get("secret") or "").strip() or None
    except Exception:
        return None


def _file_secret(*paths: str) -> Optional[str]:
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.isfile(p):
            v = open(p).read().strip()
            if "=" in v and not v.startswith("eyJ") and not v.startswith("http"):
                v = v.split("=", 1)[-1].strip()
            if v:
                return v
    return None


def load_api_key() -> str:
    # Prefer JWT from local secrets / credentials server over any stale SM key
    for src in (
        lambda: os.environ.get("QDRANT_API_KEY"),
        lambda: _file_secret(
            "~/biomimetics/secrets/qdrant_api_key",
            "~/Documents/VS Code Projects/ARCA/.secrets/qdrant_api_key",
        ),
        lambda: _cred_server_secret("qdrant_api_key"),
        lambda: _gcloud_secret("qdrant_api_key"),
    ):
        v = src()
        if v:
            return v.strip()
    raise SystemExit("No QDRANT_API_KEY found (env / local secrets / credentials server / SM)")


def load_cloud_url() -> str:
    for src in (
        lambda: os.environ.get("QDRANT_CLOUD_URL"),
        lambda: os.environ.get("QDRANT_URL") if "cloud.qdrant" in os.environ.get("QDRANT_URL", "") else None,
        lambda: _file_secret(
            "~/biomimetics/secrets/qdrant_endpoint_claws",
            "~/biomimetics/secrets/qdrant_endpoint",
            "~/Documents/VS Code Projects/ARCA/.secrets/qdrant_endpoint_claws",
        ),
        lambda: _cred_server_secret("qdrant_endpoint"),
        lambda: _cred_server_secret("qdrant_endpoint_claws"),
        lambda: _gcloud_secret("qdrant_url"),
        lambda: _gcloud_secret("qdrant_endpoint"),
        lambda: DEFAULT_CLOUD_URL,
    ):
        v = src()
        if v:
            return v.strip().rstrip("/")
    return DEFAULT_CLOUD_URL


def client(url: str, api_key: Optional[str] = None):
    from qdrant_client import QdrantClient
    kwargs = {"url": url, "timeout": 30, "check_compatibility": False}
    if api_key:
        kwargs["api_key"] = api_key
    return QdrantClient(**kwargs)


def ensure_collection(c, name: str = COLLECTION, dims: int = DIMS) -> None:
    from qdrant_client.models import Distance, VectorParams
    existing = [x.name for x in c.get_collections().collections]
    if name in existing:
        print(f"✅ collection exists: {name}")
        info = c.get_collection(name)
        print(f"   points={info.points_count} status={info.status}")
        return
    print(f"Creating collection {name} ({dims}d cosine)…")
    c.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dims, distance=Distance.COSINE),
    )
    print(f"✅ created {name}")


def migrate(src_url: str, dst, api_key: Optional[str], collection: str = COLLECTION) -> int:
    """Scroll all points from src (no key / optional) into dst cloud."""
    from qdrant_client.models import PointStruct
    src = client(src_url, api_key=None)
    # VM Qdrant may be unauthenticated
    try:
        cols = [x.name for x in src.get_collections().collections]
    except Exception as e:
        print(f"❌ cannot list source collections at {src_url}: {e}")
        return 0
    if collection not in cols:
        print(f"⚠️  source missing collection {collection}; nothing to migrate")
        return 0

    ensure_collection(dst, collection)
    offset = None
    moved = 0
    while True:
        records, offset = src.scroll(
            collection_name=collection,
            limit=64,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not records:
            break
        points = []
        for r in records:
            if r.vector is None:
                continue
            points.append(
                PointStruct(id=r.id, vector=r.vector, payload=r.payload or {})
            )
        if points:
            dst.upsert(collection_name=collection, points=points)
            moved += len(points)
            print(f"  migrated {moved} points…")
        if offset is None:
            break
    print(f"✅ migration complete: {moved} points → cloud")
    return moved


def apply_memu(cloud_url: str) -> None:
    """Update Cloud Run MemU QDRANT_URL to cloud and store URL in Secret Manager."""
    # Persist URL secret for future deploys
    try:
        subprocess.run(
            ["gcloud", "secrets", "describe", "qdrant_url", f"--project={PROJECT}"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # add version
        p = subprocess.Popen(
            ["gcloud", "secrets", "versions", "add", "qdrant_url",
             f"--project={PROJECT}", "--data-file=-"],
            stdin=subprocess.PIPE, text=True,
        )
        p.communicate(cloud_url)
    except Exception:
        subprocess.run(
            ["gcloud", "secrets", "create", "qdrant_url",
             f"--project={PROJECT}", "--replication-policy=automatic",
             "--data-file=-"],
            input=cloud_url, text=True, check=False,
        )

    cmd = [
        "gcloud", "run", "services", "update", MEMU_SERVICE,
        f"--region={REGION}", f"--project={PROJECT}",
        f"--update-env-vars=QDRANT_URL={cloud_url}",
        "--quiet",
    ]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print("✅ MemU QDRANT_URL updated. Restart/traffic already on latest revision.")
    print("Next: verify MemU /health shows cloud URL; then stop VM qdrant.service")


def main() -> int:
    ap = argparse.ArgumentParser(description="Qdrant Cloud cutover for MemU")
    ap.add_argument("--check", action="store_true", help="Only validate cloud access")
    ap.add_argument("--migrate", action="store_true", help="Copy points VM → cloud")
    ap.add_argument("--apply-memu", action="store_true", help="Point Cloud Run MemU at cloud URL")
    ap.add_argument("--src", default=DEFAULT_VM_URL, help="Source Qdrant (VM temporary)")
    ap.add_argument("--cloud-url", default=None, help="Override cloud cluster URL")
    ap.add_argument("--stop-vm-qdrant", action="store_true",
                    help="After successful apply, disable qdrant on muninn-global")
    args = ap.parse_args()

    cloud_url = (args.cloud_url or load_cloud_url()).rstrip("/")
    api_key = load_api_key()
    print(f"Cloud URL: {cloud_url}")
    print(f"API key length: {len(api_key)}")

    try:
        c = client(cloud_url, api_key)
        cols = [x.name for x in c.get_collections().collections]
        print(f"✅ cloud reachable; collections={cols}")
    except Exception as e:
        print(f"❌ Qdrant Cloud check FAILED: {e}")
        print(
            "\nCutover blocked until you supply a valid cluster:\n"
            "  1. Create/repair free cluster at https://cloud.qdrant.io\n"
            "  2. gcloud secrets versions add qdrant_api_key --data-file=- <<<'NEW_KEY'\n"
            "  3. gcloud secrets create qdrant_url --data-file=- <<<'https://….cloud.qdrant.io'\n"
            "  4. Re-run: python3 scripts/memory/qdrant_cloud_cutover.py --check --migrate --apply-memu\n"
        )
        return 2

    if args.check and not args.migrate and not args.apply_memu:
        ensure_collection(c)
        return 0

    ensure_collection(c)

    if args.migrate:
        migrate(args.src, c, api_key)

    if args.apply_memu:
        apply_memu(cloud_url)

    if args.stop_vm_qdrant:
        if not args.apply_memu:
            print("Refusing --stop-vm-qdrant without --apply-memu")
            return 3
        # Final health via MemU
        try:
            req = urllib.request.Request(
                "https://memu-757330161781.us-central1.run.app/health"
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                health = json.loads(r.read().decode())
            print("MemU health qdrant_url:", health.get("qdrant_url"))
            if "cloud.qdrant" not in str(health.get("qdrant_url", "")):
                print("❌ MemU still not on cloud URL — not stopping VM qdrant")
                return 4
        except Exception as e:
            print(f"❌ MemU health check failed: {e}")
            return 4
        print("Stopping qdrant.service on muninn-global…")
        subprocess.check_call([
            "gcloud", "compute", "ssh", "muninn-global",
            "--zone=us-central1-c", f"--project={PROJECT}",
            "--command=sudo systemctl disable --now qdrant.service; "
            "ss -lntp | grep 6333 || echo '6333 closed'",
        ])
        print("✅ VM Qdrant stopped (Muninn untouched)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
