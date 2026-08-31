"""
Geometry Watcher — OCI ARM64 File Intake Service
=================================================
Monitors /app/shared_storage/ingest_prep/intake/ for new document files.
Supported formats: PDF, TXT, Markdown, EPUB.

Pipeline per document:
  1. PDF arrives  → PdfRefinery (PPStructure, CPU-only)
  2. refined_doc.json  → written to INTAKE_OUTPUT_DIR/{book_name}/
  3. POST  geometry_kernel /geometry/ingest_recursive  → triggers embedding + concept extraction
  4. Output appears in /app/shared_storage/ingest/output/

Environment variables:
  INTAKE_DIR            path to watch  (default: /app/shared_storage/ingest_prep/intake)
  OUTPUT_DIR            refined doc output root (default: /app/shared_storage/ingest/intake)
  GEOMETRY_KERNEL_URL   (default: http://geometry_kernel:8087)
  STORAGE_ROOT          passed to PdfRefinery work_dir base (default: /app/shared_storage)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

import requests
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer

# Ensure services are importable
sys.path.insert(0, "/app")

logger = logging.getLogger("geometry_watcher")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

INTAKE_DIR          = os.environ.get("INTAKE_DIR",          "/app/shared_storage/ingest_prep/intake")
OUTPUT_DIR          = os.environ.get("OUTPUT_DIR",          "/app/shared_storage/ingest/intake")
GEOMETRY_KERNEL_URL = os.environ.get("GEOMETRY_KERNEL_URL", "http://geometry_kernel:8087")
STORAGE_ROOT        = os.environ.get("STORAGE_ROOT",        "/app/shared_storage")

# How long to wait after a new file is seen before processing it
# (lets the copy/move finish before we open the file)
SETTLE_SECONDS = 3

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md", ".epub")


class PdfIntakeHandler(FileSystemEventHandler):
    """Watchdog event handler that processes newly-arrived documents."""

    def __init__(self):
        super().__init__()
        self._processing: set[str] = set()

    # ── watchdog callbacks ────────────────────────────────────────────────────

    def on_created(self, event: FileCreatedEvent):
        if not event.is_directory and event.src_path.lower().endswith(SUPPORTED_EXTENSIONS):
            self._handle(event.src_path)

    def on_moved(self, event: FileMovedEvent):
        if not event.is_directory and event.dest_path.lower().endswith(SUPPORTED_EXTENSIONS):
            self._handle(event.dest_path)

    # ── core handler ──────────────────────────────────────────────────────────

    def _handle(self, doc_path: str):
        abs_path = str(Path(doc_path).resolve())
        if abs_path in self._processing:
            return
        self._processing.add(abs_path)
        try:
            logger.info(f"📄 New document detected: {abs_path}")
            time.sleep(SETTLE_SECONDS)  # wait for file to finish landing

            if not Path(abs_path).exists():
                logger.warning(f"File vanished before processing: {abs_path}")
                return

            refined_path = self._preprocess(abs_path)
            if refined_path:
                self._trigger_ingest(abs_path, refined_path)
        except Exception as exc:
            logger.error(f"Error processing {abs_path}: {exc}", exc_info=True)
        finally:
            self._processing.discard(abs_path)

    # ── Document preprocessing (Phase 0, CPU) ───────────────────────────────

    def _preprocess(self, doc_path: str) -> str | None:
        """
        Run Phase 0 refinement on *doc_path* and write refined_doc.json to OUTPUT_DIR.
        PDFs go through PdfRefinery (PPStructure); text/epub go through lightweight extraction.
        Returns the path to refined_doc.json, or None on failure.
        """
        book_name = Path(doc_path).stem.replace("_", " ")
        safe_name = book_name.replace(" ", "_")

        work_dir  = str(Path(STORAGE_ROOT) / "atomized" / "refined" / safe_name)
        out_dir   = Path(OUTPUT_DIR) / safe_name
        out_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(doc_path).suffix.lower()

        if ext == ".pdf":
            return self._preprocess_pdf(doc_path, book_name, work_dir, out_dir)

        # TXT / MD / EPUB — use HeavyGeometryIngester.refine_pdf which handles all formats
        logger.info(f"🔬 Preprocessing '{book_name}' ({ext}) …")
        try:
            from services.geometry_heavy_lifter.core import HeavyGeometryIngester
            ingester = HeavyGeometryIngester(storage_root=STORAGE_ROOT)
            refined_path = ingester.refine_pdf(doc_path, book_name=book_name)
        except Exception as e:
            logger.error(f"Preprocessing FAILED for '{book_name}': {e}", exc_info=True)
            return None

        # Copy refined_doc.json to the watcher output directory so the kernel finds it
        out_refined = str(out_dir / "refined_doc.json")
        if refined_path != out_refined:
            import shutil
            shutil.copy2(refined_path, out_refined)

        logger.info(f"✅ Preprocessing done → {out_refined}")
        return out_refined

    def _preprocess_pdf(self, pdf_path: str, book_name: str, work_dir: str, out_dir: Path) -> str | None:
        """Original PDF preprocessing via PdfRefinery (PPStructure + PaddleOCR)."""
        from services.pdf_to_embedding.document_refinery import PdfRefinery

        logger.info(f"🔬 Preprocessing '{book_name}' with PPStructure (CPU)…")
        try:
            refinery = PdfRefinery(work_dir=work_dir)
            doc = refinery.refine(pdf_path, book_name=book_name)
        except ValueError as e:
            logger.error(f"Integrity check FAILED for '{book_name}': {e}")
            return None

        refined_path = str(out_dir / "refined_doc.json")
        with open(refined_path, "w") as fh:
            json.dump(
                {
                    "source_pdf":  doc.source_pdf,
                    "book_name":   doc.book_name,
                    "text_chunks": doc.text_chunks,
                    "image_crops": [asdict(c) for c in doc.image_crops],
                    "stats":       doc.stats,
                },
                fh,
                indent=2,
            )

        logger.info(
            f"✅ Preprocessing done → {refined_path}  "
            f"(chunks={doc.stats.get('text_chunks')}, "
            f"figures={doc.stats.get('image_crops')})"
        )
        return refined_path
        return refined_path

    # ── trigger geometry_kernel ingestion ─────────────────────────────────────

    def _trigger_ingest(self, original_doc: str, refined_path: str):
        """
        POST to geometry_kernel /geometry/ingest_recursive.
        The kernel normalises the path relative to /app/shared_storage.
        """
        book_name = Path(original_doc).stem.replace("_", " ")

        # Translate host path → container path visible to geometry_kernel
        # Both services mount shared_storage at /app/shared_storage
        container_path = refined_path.replace(
            str(Path(STORAGE_ROOT).resolve()),
            "/app/shared_storage",
        )

        payload = {
            "file_path":  container_path,
            "objective":  (
                f"Extract and map the geometric, metaphysical, and mathematical "
                f"concepts from '{book_name}' into a 3D epistemic space."
            ),
            "content_type": "NARRATIVE",
        }

        kernel_url = f"{GEOMETRY_KERNEL_URL}/geometry/ingest_recursive"
        logger.info(f"🚀 Triggering ingest: POST {kernel_url}  file={container_path}")

        try:
            resp = requests.post(kernel_url, json=payload, timeout=600)
            if resp.ok:
                result = resp.json()
                n_objects = len(result.get("objects", []))
                logger.info(
                    f"✅ Ingest complete for '{book_name}': "
                    f"{n_objects} concept nodes extracted"
                )
            else:
                logger.error(
                    f"Ingest request failed ({resp.status_code}): {resp.text[:500]}"
                )
        except requests.exceptions.ConnectionError:
            logger.error(
                f"Cannot reach geometry_kernel at {GEOMETRY_KERNEL_URL}. "
                "Is it running?"
            )
        except requests.exceptions.Timeout:
            logger.warning(
                "Ingest request timed out (600 s). Large document – "
                "kernel may still be processing."
            )


# ── health check for the watcher HTTP endpoint ───────────────────────────────

def start_health_server(port: int = 8089):
    """Tiny HTTP health endpoint so docker healthchecks work."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok","service":"geometry_watcher"}')

        def log_message(self, *_):
            pass  # suppress access log

    server = HTTPServer(("0.0.0.0", port), _H)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"Health endpoint listening on :{port}")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Ensure watch directory exists
    Path(INTAKE_DIR).mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    start_health_server()

    logger.info(f"👁  Watching {INTAKE_DIR}  →  {OUTPUT_DIR}")
    logger.info(f"    geometry_kernel: {GEOMETRY_KERNEL_URL}")

    event_handler = PdfIntakeHandler()
    observer = Observer()
    observer.schedule(event_handler, INTAKE_DIR, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(10)
            if not observer.is_alive():
                logger.error("Observer thread died, restarting…")
                observer = Observer()
                observer.schedule(event_handler, INTAKE_DIR, recursive=False)
                observer.start()
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        logger.info("Watcher stopped.")
