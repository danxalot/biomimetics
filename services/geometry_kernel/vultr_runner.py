#!/usr/bin/env python3
"""
ARCA Vultr Runner
=================
Replaces azure_runner.py for Vultr GPU instances.

Polls /app/shared_storage/inbox/ for job files, processes each document
through HeavyGeometryIngester with full checkpointing, writes manifests
with SHA-256 checksums, and marks jobs complete atomically.

Job file format (inbox/<jobid>.json):
  {
    "job_id": "abc123",
    "file_path": "/app/shared_storage/inbox/docs/MyDoc.md",
    "objective": "Extract geometry and JEPA training vectors",
    "force_clean": false
  }

Output layout (on persistent block volume /app/shared_storage):
  atomized/Concepts/<safe_name>/
    Vectors.json          — embedding vectors
    Objects.json          — extracted concept objects
  data/ingestion/output/
    <safe_name>_<ts>.json — full solar system result
  data/ingestion/checkpoints/<safe_name>/
    latest.json           — resume checkpoint (every 10 chunks)
  manifests/
    <job_id>.manifest.json — checksums + job metadata
  inbox/done/
    <jobid>.json          — original job file moved here on success
  inbox/failed/
    <jobid>.json          — moved here on unrecoverable failure
"""

import os
import sys
import json
import time
import signal
import hashlib
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/services")
sys.path.insert(0, "/app/services/geometry_kernel")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/app/shared_storage/vultr_runner.log", mode="a"),
    ],
)
logger = logging.getLogger("VultrRunner")

# ── Paths ─────────────────────────────────────────────────────────────────────
SHARED = Path(os.environ.get("SHARED_STORAGE", "/app/shared_storage"))
INBOX       = SHARED / "inbox"
INBOX_DONE  = INBOX / "done"
INBOX_FAIL  = INBOX / "failed"
MANIFEST_DIR = SHARED / "manifests"
OUTPUT_DIR  = SHARED / "data" / "ingestion" / "output"
CKPT_BASE   = SHARED / "data" / "ingestion" / "checkpoints"

for d in [INBOX, INBOX_DONE, INBOX_FAIL, MANIFEST_DIR, OUTPUT_DIR, CKPT_BASE]:
    d.mkdir(parents=True, exist_ok=True)

# ── Shutdown ──────────────────────────────────────────────────────────────────
shutdown_flag = threading.Event()

def _sig(signum, frame):
    logger.warning(f"🛑 Signal {signum} — initiating graceful shutdown")
    shutdown_flag.set()

signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)


# ── Checksum helpers ──────────────────────────────────────────────────────────
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, data: dict):
    """Write JSON atomically via tmp file + rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


# ── Manifest ──────────────────────────────────────────────────────────────────
def write_manifest(job_id: str, job: dict, output_files: list[Path], status: str, error: str = ""):
    manifest = {
        "job_id": job_id,
        "status": status,
        "error": error,
        "file_path": job.get("file_path"),
        "objective": job.get("objective"),
        "started_at": job.get("_started_at"),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "outputs": [],
    }
    for p in output_files:
        if p.exists():
            manifest["outputs"].append({
                "path": str(p.relative_to(SHARED)),
                "size_bytes": p.stat().st_size,
                "sha256": sha256_file(p),
            })
    mpath = MANIFEST_DIR / f"{job_id}.manifest.json"
    atomic_write(mpath, manifest)
    logger.info(f"📋 Manifest written: {mpath}")
    return mpath


# ── Process one job ───────────────────────────────────────────────────────────
def process_job(job_path: Path):
    job = json.loads(job_path.read_text())
    job_id = job.get("job_id", job_path.stem)
    file_path = job.get("file_path")
    objective = job.get("objective", "Extract geometric concepts for JEPA training")
    force_clean = job.get("force_clean", False)
    job["_started_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"📂 Starting job {job_id}: {file_path}")

    # Resolve path — support relative-to-shared_storage
    src = Path(file_path)
    if not src.is_absolute():
        src = SHARED / file_path
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    safe_name = src.name.replace(".", "_").replace(" ", "_")

    # Optionally wipe checkpoint for a clean run
    ckpt_dir = CKPT_BASE / safe_name
    if force_clean and ckpt_dir.exists():
        import shutil
        shutil.rmtree(ckpt_dir)
        logger.info(f"🧹 force_clean=True: Removed checkpoint dir {ckpt_dir}")

    # ── Load ingester ─────────────────────────────────────────────────────────
    try:
        from model_engine import CognitiveScheduler
        from recursive_ingestion import RecursiveIngestion
    except ImportError as e:
        logger.error(f"Import failed: {e}")
        raise

    scheduler = CognitiveScheduler()
    ingester = RecursiveIngestion(scheduler)

    # ── Run ingestion (resumes from checkpoint if present) ────────────────────
    result = ingester.ingest_content(
        file_path=str(src),
        objective=objective,
        content_type="AUTO",
        verbosity="full",
        use_semantic_chunking=True,
    )

    # ── Collect output files ──────────────────────────────────────────────────
    out_files: list[Path] = []

    # Main output (written by recursive_ingestion itself)
    for p in OUTPUT_DIR.glob(f"{safe_name}_*.json"):
        out_files.append(p)

    # Vectors + Objects (written by heavy_lifter if it ran embed pass)
    concept_dir = SHARED / "atomized" / "Concepts" / safe_name
    for name in ["Vectors.json", "Objects.json"]:
        p = concept_dir / name
        if p.exists():
            out_files.append(p)

    # Also save the result dict explicitly as a canonical output
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    canonical = OUTPUT_DIR / f"{safe_name}_canonical_{ts}.json"
    atomic_write(canonical, result)
    out_files.append(canonical)

    logger.info(f"✅ Job {job_id} complete — {len(out_files)} output files")
    return out_files


# ── Job lifecycle ─────────────────────────────────────────────────────────────
def run_job(job_path: Path):
    job_id = job_path.stem
    try:
        out_files = process_job(job_path)
        write_manifest(job_id, json.loads(job_path.read_text()), out_files, status="success")
        # Move to done/
        dest = INBOX_DONE / job_path.name
        job_path.replace(dest)
        logger.info(f"✅ Job {job_id} → done/")
    except Exception as e:
        logger.error(f"❌ Job {job_id} failed: {e}", exc_info=True)
        try:
            job = json.loads(job_path.read_text()) if job_path.exists() else {}
            write_manifest(job_id, job, [], status="failed", error=str(e))
            dest = INBOX_FAIL / job_path.name
            job_path.replace(dest)
        except Exception as ex:
            logger.critical(f"Failed to write failure manifest: {ex}")


# ── Main poll loop ────────────────────────────────────────────────────────────
def main():
    logger.info("🚀 ARCA Vultr Runner started")
    logger.info(f"   Inbox:     {INBOX}")
    logger.info(f"   Manifests: {MANIFEST_DIR}")
    logger.info(f"   Outputs:   {OUTPUT_DIR}")

    # Process any pre-queued jobs first, then poll
    while not shutdown_flag.is_set():
        pending = sorted(INBOX.glob("*.json"))
        if not pending:
            time.sleep(10)
            continue

        for job_path in pending:
            if shutdown_flag.is_set():
                logger.warning("⚠️  Shutdown requested mid-queue — stopping after current job")
                break
            logger.info(f"📋 Processing queued job: {job_path.name}")
            run_job(job_path)

    logger.info("🛑 Vultr Runner shut down cleanly")


if __name__ == "__main__":
    main()
