"""
ARCA Intake Watcher Daemon
===========================

Automatic intake processing daemon that watches for new documents
in the intake directory and processes them through ARCA's analysis pipeline.

Pipeline:
  1. Watch  shared_storage/ingest/intake/  for new files (.md, .txt, .docx, .pdf)
  2. Read document content
  3. Send to Pythia (port 11435) for LLM-based concept analysis
  4. Send to geometry_onnx_interpreter (port 8096) for 2048-dim vector embedding
  5. Save comprehensive JSON record to  shared_storage/ingest/output/
  6. Move processed file to  shared_storage/ingested/intake/

Services:
  - Pythia Server          (port 11435) — llama.cpp + Qwen3VL-2B
  - Geometry ONNX Interp   (port 8096)  — ONNX model + oracle layer

Usage:
  python intake_watcher.py                  # Daemon mode (default)
  python intake_watcher.py --watch          # Daemon mode (explicit)
  python intake_watcher.py --once           # One-shot: process current files, exit
  python intake_watcher.py --interval 10    # Poll every 10 seconds
"""

import argparse
import json
import logging
import math
import os
import re
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

INTAKE_DIR = _PROJECT_ROOT / "shared_storage" / "ingest" / "intake"
OUTPUT_DIR = _PROJECT_ROOT / "shared_storage" / "ingest" / "output"
INGESTED_DIR = _PROJECT_ROOT / "shared_storage" / "ingested" / "intake"

# ---------------------------------------------------------------------------
# Service endpoints
# ---------------------------------------------------------------------------
PYTHIA_URL = os.getenv("PYTHIA_SERVER_URL", "http://localhost:11435")
PYTHIA_CHAT_ENDPOINT = f"{PYTHIA_URL}/v1/chat/completions"
PYTHIA_MODEL = "Qwen3VL-2B-Instruct-Q8_0.gguf"
PYTHIA_PORT = 11435

GEOMETRY_URL = os.getenv("ONNX_INTERPRETER_URL", "http://localhost:8096")
GEOMETRY_ONNX_ENDPOINT = f"{GEOMETRY_URL}/interpret/onnx_only"
GEOMETRY_PORT = 8096

# ---------------------------------------------------------------------------
# Supported file extensions
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx", ".pdf"}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

logger = logging.getLogger("intake_watcher")


# ═══════════════════════════════════════════════════════════════════════════════
# Document reading
# ═══════════════════════════════════════════════════════════════════════════════


def read_document(filepath: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Read document content from a file.

    Returns:
        (content, error)  — content is None on failure, error is None on success.
    """
    suffix = filepath.suffix.lower()

    if suffix in (".md", ".txt"):
        return _read_text_file(filepath)
    elif suffix == ".docx":
        return _read_docx_file(filepath)
    elif suffix == ".pdf":
        return (
            None,
            "PDF reading not supported — install a PDF library and extend this handler",
        )
    else:
        return None, f"Unsupported file extension: {suffix}"


def _read_text_file(filepath: Path) -> Tuple[Optional[str], Optional[str]]:
    """Read plain text or markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if not content.strip():
            return None, "File is empty"
        return content, None
    except Exception as exc:
        return None, f"Failed to read text file: {exc}"


def _read_docx_file(filepath: Path) -> Tuple[Optional[str], Optional[str]]:
    """Read .docx file using python-docx if available."""
    try:
        import docx  # python-docx
    except ImportError:
        return (
            None,
            "python-docx not installed — cannot read .docx files (pip install python-docx)",
        )

    try:
        doc = docx.Document(str(filepath))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        if not paragraphs:
            return None, "DOCX file contains no text paragraphs"
        return "\n\n".join(paragraphs), None
    except Exception as exc:
        return None, f"Failed to read DOCX file: {exc}"


# ═══════════════════════════════════════════════════════════════════════════════
# Concept extraction  (mirrors geometry_test.py logic)
# ═══════════════════════════════════════════════════════════════════════════════

STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "shall",
    "can",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "we",
    "our",
    "you",
    "your",
    "they",
    "their",
    "them",
    "not",
    "all",
    "as",
    "if",
    "so",
    "than",
    "such",
    "also",
    "into",
    "through",
    "during",
    "about",
    "up",
    "out",
    "which",
    "who",
    "whom",
    "what",
    "when",
    "where",
    "how",
    "each",
    "every",
    "both",
    "more",
    "most",
    "other",
    "some",
    "any",
    "no",
    "own",
}


def extract_concepts(text: str, max_concepts: int = 32) -> List[Dict[str, Any]]:
    """
    Extract key concepts from document text and assign 3D positions
    on a Fibonacci sphere.  Deterministic — same text always yields
    the same geometric layout.
    """
    # Sentence-level split for description lookup
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    # TF-style keyword extraction
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    freq: Dict[str, int] = {}
    for w in words:
        if w not in STOP_WORDS:
            freq[w] = freq.get(w, 0) + 1

    ranked = sorted(freq.items(), key=lambda x: -x[1])
    keywords = [kw for kw, _ in ranked[:max_concepts]]

    if not keywords:
        keywords = ["document", "concept", "analysis", "structure"]
        for kw in keywords:
            if kw not in freq:
                freq[kw] = 1

    # Golden-angle spiral on a sphere (Fibonacci sphere)
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    concepts = []

    for i, keyword in enumerate(keywords):
        y = 1.0 - (i / max(len(keywords) - 1, 1)) * 2.0
        radius_at_y = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden_angle * i
        x = math.cos(theta) * radius_at_y
        z = math.sin(theta) * radius_at_y

        mass = min(1.0, freq.get(keyword, 1) / max(ranked[0][1], 1))
        scale = 1.0 + mass * 4.0
        position = [
            round(x * scale, 4),
            round(y * scale, 4),
            round(z * scale, 4),
        ]

        # Pick a representative sentence containing this keyword
        desc = ""
        for s in sentences:
            if keyword in s.lower():
                desc = s[:120]
                break

        concepts.append(
            {
                "id": f"concept:{keyword}",
                "mass": round(mass, 4),
                "position": position,
                "desc": desc or f"Extracted concept: {keyword}",
            }
        )

    return concepts


def build_solar_system(
    doc_text: str,
    system_id: str,
    max_concepts: int = 32,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Convert document text into SolarSystem JSON for geometry_onnx_interpreter.

    Returns:
        (solar_system_dict, concepts_list)
    """
    concepts = extract_concepts(doc_text, max_concepts=max_concepts)

    gravity_concept = concepts[0]["id"].replace("concept:", "") if concepts else "core"
    gravity_mass = concepts[0]["mass"] * 10 if concepts else 5.0

    if concepts:
        positions = [c["position"] for c in concepts]
        n = len(positions)
        centroid = [
            round(sum(p[0] for p in positions) / n, 4),
            round(sum(p[1] for p in positions) / n, 4),
            round(sum(p[2] for p in positions) / n, 4),
        ]
    else:
        centroid = [0.0, 0.0, 0.0]

    solar_system = {
        "system_id": system_id,
        "gravity_well": {
            "concept": gravity_concept,
            "mass": round(gravity_mass, 4),
        },
        "objects": concepts,
        "trajectory": centroid,
    }

    return solar_system, concepts


# ═══════════════════════════════════════════════════════════════════════════════
# Pythia (LLM) interaction
# ═══════════════════════════════════════════════════════════════════════════════

PYTHIA_SYSTEM_PROMPT = (
    "You are ARCA's document analysis agent (codename: Pythia). "
    "Analyse the following document thoroughly. Extract and summarise:\n"
    "1. The core thesis or purpose of the document.\n"
    "2. Key concepts, entities, and technical terms.\n"
    "3. Relationships between concepts.\n"
    "4. Any actionable insights or recommendations.\n"
    "5. A concise 2-3 sentence summary.\n\n"
    "Be precise and structured in your response."
)


def send_to_pythia(document_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Send document text to Pythia for LLM analysis.

    Returns:
        (response_text, error)
    """
    import requests

    # Truncate very long documents to avoid overwhelming the context window
    max_chars = 12000
    if len(document_text) > max_chars:
        truncated_text = (
            document_text[:max_chars] + "\n\n[... document truncated for analysis ...]"
        )
        logger.info(
            "Document truncated from %d to %d chars for Pythia",
            len(document_text),
            max_chars,
        )
    else:
        truncated_text = document_text

    payload = {
        "model": PYTHIA_MODEL,
        "messages": [
            {"role": "system", "content": PYTHIA_SYSTEM_PROMPT},
            {"role": "user", "content": truncated_text},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }

    try:
        logger.info("Sending document to Pythia at %s", PYTHIA_CHAT_ENDPOINT)
        t0 = time.monotonic()
        resp = requests.post(
            PYTHIA_CHAT_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        elapsed = time.monotonic() - t0
        logger.info("Pythia responded in %.2fs (HTTP %d)", elapsed, resp.status_code)

        if resp.status_code != 200:
            return None, f"Pythia returned HTTP {resp.status_code}: {resp.text[:300]}"

        data = resp.json()
        # OpenAI-compatible response format
        choices = data.get("choices", [])
        if not choices:
            return None, "Pythia response contained no choices"

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            return None, "Pythia response message had empty content"

        return content.strip(), None

    except requests.exceptions.ConnectionError:
        return None, f"Pythia unavailable (connection refused on port {PYTHIA_PORT})"
    except requests.exceptions.Timeout:
        return None, "Pythia request timed out (120s)"
    except Exception as exc:
        return None, f"Pythia request failed: {exc}"


# ═══════════════════════════════════════════════════════════════════════════════
# Geometry ONNX interpreter interaction
# ═══════════════════════════════════════════════════════════════════════════════


def send_to_geometry(
    solar_system: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Send SolarSystem JSON to geometry_onnx_interpreter for ONNX-only inference.

    Returns:
        (result_dict, error)
        result_dict contains 'vector', 'inference_time_ms', 'confidence', 'energy'
    """
    import requests

    try:
        logger.info(
            "Sending SolarSystem to geometry interpreter at %s", GEOMETRY_ONNX_ENDPOINT
        )
        t0 = time.monotonic()
        resp = requests.post(
            GEOMETRY_ONNX_ENDPOINT,
            json=solar_system,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        elapsed = time.monotonic() - t0
        logger.info(
            "Geometry interpreter responded in %.2fs (HTTP %d)",
            elapsed,
            resp.status_code,
        )

        if resp.status_code != 200:
            return (
                None,
                f"Geometry interpreter returned HTTP {resp.status_code}: {resp.text[:300]}",
            )

        result = resp.json()
        return result, None

    except requests.exceptions.ConnectionError:
        return (
            None,
            f"Geometry interpreter unavailable (connection refused on port {GEOMETRY_PORT})",
        )
    except requests.exceptions.Timeout:
        return None, "Geometry interpreter request timed out (30s)"
    except Exception as exc:
        return None, f"Geometry interpreter request failed: {exc}"


# ═══════════════════════════════════════════════════════════════════════════════
# Main processing pipeline
# ═══════════════════════════════════════════════════════════════════════════════


def process_file(filepath: Path) -> bool:
    """
    Process a single intake file through the full pipeline.

    Returns True if at least one service responded (partial or complete),
    False if processing should be retried later (both services down, or
    the document couldn't be read at all).
    """
    filename = filepath.name
    document_title = filepath.stem
    errors: List[str] = []
    processing_status = "complete"

    logger.info("=" * 60)
    logger.info("Processing: %s", filename)
    logger.info("=" * 60)

    submission_timestamp = datetime.now(timezone.utc).isoformat()
    timestamp_compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # ── Step 1: Read document ──
    logger.info("Step 1: Reading document content")
    document_content, read_error = read_document(filepath)
    if read_error:
        logger.warning("Document read issue: %s", read_error)
        errors.append(f"read: {read_error}")

    if document_content is None:
        # Can't proceed without content
        logger.error("Cannot read document content — skipping (will retry)")
        # For .pdf or missing python-docx, we still want to move the file
        # but mark as failed.  However, if the file truly can't be read ever
        # (e.g., PDF without library), we should still produce a record.
        if filepath.suffix.lower() in (".pdf", ".docx"):
            document_content = ""
            processing_status = "failed"
            logger.warning(
                "Producing failure record for unreadable %s file", filepath.suffix
            )
        else:
            return False

    # ── Step 2: Extract concepts & build SolarSystem ──
    logger.info("Step 2: Extracting concepts")
    system_id = f"intake_{document_title}"
    if document_content:
        solar_system, concepts = build_solar_system(
            document_content, system_id=system_id
        )
        num_concepts = len(concepts)
        logger.info("Extracted %d concepts", num_concepts)
    else:
        solar_system = {
            "system_id": system_id,
            "gravity_well": {"concept": "unknown", "mass": 1.0},
            "objects": [],
            "trajectory": [0.0, 0.0, 0.0],
        }
        concepts = []
        num_concepts = 0

    # ── Step 3: Send to Pythia ──
    logger.info("Step 3: Sending to Pythia (port %d)", PYTHIA_PORT)
    pythia_response = None
    if document_content:
        pythia_response, pythia_error = send_to_pythia(document_content)
        if pythia_error:
            logger.warning("Pythia error: %s", pythia_error)
            errors.append(f"pythia: {pythia_error}")
            processing_status = (
                "partial" if processing_status == "complete" else processing_status
            )
    else:
        errors.append("pythia: skipped — no document content")
        processing_status = "failed"

    # ── Step 4: Send to geometry interpreter ──
    logger.info("Step 4: Sending to geometry interpreter (port %d)", GEOMETRY_PORT)
    geometry_vector = None
    geometry_inference_ms = None
    if concepts:
        geo_result, geo_error = send_to_geometry(solar_system)
        if geo_error:
            logger.warning("Geometry error: %s", geo_error)
            errors.append(f"geometry: {geo_error}")
            processing_status = (
                "partial" if processing_status == "complete" else processing_status
            )
        else:
            assert (
                geo_result is not None
            )  # type narrowing: no error means result exists
            geometry_vector = geo_result.get("vector")
            geometry_inference_ms = geo_result.get("inference_time_ms")
            logger.info(
                "Geometry vector received (%d dims, %.2fms)",
                len(geometry_vector) if geometry_vector else 0,
                geometry_inference_ms or 0,
            )
    else:
        errors.append("geometry: skipped — no concepts extracted")
        processing_status = (
            "partial" if processing_status == "complete" else processing_status
        )

    # ── Check if both services failed ──
    both_services_down = (
        pythia_response is None
        and geometry_vector is None
        and document_content  # only if we actually had content to send
    )
    # Check specifically for connection errors (services down vs. other errors)
    connection_errors = [
        e
        for e in errors
        if "connection refused" in e.lower() or "unavailable" in e.lower()
    ]
    if both_services_down and len(connection_errors) >= 2:
        logger.error(
            "Both Pythia and Geometry services are unavailable — leaving file for retry"
        )
        return False

    # ── Step 5: Build output JSON ──
    logger.info("Step 5: Saving output record")
    output_record = {
        "document_title": document_title,
        "document_path": str(filepath),
        "document_content": document_content or "",
        "submission_timestamp": submission_timestamp,
        "pythia_response": pythia_response,
        "pythia_model": PYTHIA_MODEL,
        "pythia_port": PYTHIA_PORT,
        "geometry_vector_2048": geometry_vector,
        "geometry_inference_ms": geometry_inference_ms,
        "num_concepts_extracted": num_concepts,
        "concepts": concepts,
        "processing_status": processing_status,
        "errors": errors,
    }

    output_filename = f"{document_title}_{timestamp_compact}.json"
    # Sanitize filename: replace problematic characters
    output_filename = re.sub(r'[<>:"/\\|?*]', "_", output_filename)
    output_path = OUTPUT_DIR / output_filename

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_record, f, indent=2, ensure_ascii=False)
        logger.info("Output saved: %s", output_path)
    except Exception as exc:
        logger.error("Failed to save output JSON: %s", exc)
        return False

    # ── Step 6: Move processed file to ingested ──
    logger.info("Step 6: Moving processed file to ingested")
    try:
        INGESTED_DIR.mkdir(parents=True, exist_ok=True)
        dest = INGESTED_DIR / filename
        # Handle filename collision — append timestamp
        if dest.exists():
            stem = filepath.stem
            suffix = filepath.suffix
            dest = INGESTED_DIR / f"{stem}_{timestamp_compact}{suffix}"
        shutil.move(str(filepath), str(dest))
        logger.info("Moved to: %s", dest)
    except Exception as exc:
        logger.error("Failed to move file to ingested: %s", exc)
        # Output was saved, so we still consider this a success
        # The file will be re-processed next cycle but dedup by presence in output dir

    logger.info(
        "Processing complete: status=%s, errors=%d", processing_status, len(errors)
    )
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# File discovery
# ═══════════════════════════════════════════════════════════════════════════════


def get_intake_files() -> List[Path]:
    """Return list of processable files currently in the intake directory."""
    if not INTAKE_DIR.exists():
        return []
    files = []
    for item in sorted(INTAKE_DIR.iterdir()):
        if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(item)
    return files


def process_all_current() -> int:
    """Process all files currently in intake. Returns count of files processed."""
    files = get_intake_files()
    if not files:
        logger.info("No files in intake directory")
        return 0

    logger.info("Found %d file(s) to process", len(files))
    processed = 0
    for filepath in files:
        try:
            success = process_file(filepath)
            if success:
                processed += 1
            else:
                logger.warning("File deferred for retry: %s", filepath.name)
        except Exception as exc:
            logger.error(
                "Unexpected error processing %s: %s", filepath.name, exc, exc_info=True
            )

    logger.info("Processed %d / %d files", processed, len(files))
    return processed


# ═══════════════════════════════════════════════════════════════════════════════
# Daemon mode — watchdog or polling
# ═══════════════════════════════════════════════════════════════════════════════

_shutdown_requested = False


def _handle_signal(signum, frame):
    """Handle SIGINT / SIGTERM for graceful shutdown."""
    global _shutdown_requested
    sig_name = (
        signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    )
    logger.info("Received %s — shutting down gracefully", sig_name)
    _shutdown_requested = True


def run_watchdog_daemon(poll_interval: float = 5.0):
    """
    Run the daemon using the watchdog library for filesystem events.
    Falls back to polling if watchdog is not available.
    """
    try:
        from watchdog.events import (
            FileCreatedEvent,
            FileMovedEvent,
            FileSystemEventHandler,
        )
        from watchdog.observers import Observer

        _has_watchdog = True
    except ImportError:
        _has_watchdog = False

    if _has_watchdog:
        logger.info("Using watchdog for filesystem monitoring")
        _run_with_watchdog(
            Observer,
            FileSystemEventHandler,
            FileCreatedEvent,
            FileMovedEvent,
            poll_interval,
        )
    else:
        logger.info(
            "watchdog not available — falling back to polling (interval=%.1fs)",
            poll_interval,
        )
        _run_with_polling(poll_interval)


def _run_with_watchdog(
    Observer,
    FileSystemEventHandler,
    FileCreatedEvent,
    FileMovedEvent,
    poll_interval: float,
):
    """Daemon loop using watchdog filesystem observer."""

    # Ensure intake dir exists
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)

    class IntakeHandler(FileSystemEventHandler):
        """Handle new files appearing in the intake directory."""

        def __init__(self):
            super().__init__()
            self._processing: Set[str] = set()

        def on_created(self, event):
            if event.is_directory:
                return
            self._handle_file(Path(event.src_path))

        def on_moved(self, event):
            if event.is_directory:
                return
            self._handle_file(Path(event.dest_path))

        def _handle_file(self, filepath: Path):
            if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                return
            if str(filepath) in self._processing:
                return

            # Brief delay to let file writes complete
            time.sleep(0.5)

            # Verify the file still exists (may have been moved already)
            if not filepath.exists():
                return

            self._processing.add(str(filepath))
            try:
                logger.info("New file detected: %s", filepath.name)
                process_file(filepath)
            except Exception as exc:
                logger.error(
                    "Error processing %s: %s", filepath.name, exc, exc_info=True
                )
            finally:
                self._processing.discard(str(filepath))

    handler = IntakeHandler()
    observer = Observer()
    observer.schedule(handler, str(INTAKE_DIR), recursive=False)
    observer.start()

    logger.info("Watchdog observer started — monitoring %s", INTAKE_DIR)

    # Process any files already present
    process_all_current()

    try:
        while not _shutdown_requested:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — stopping observer")
    finally:
        observer.stop()
        observer.join(timeout=5.0)
        logger.info("Watchdog observer stopped")


def _run_with_polling(poll_interval: float):
    """Daemon loop using simple polling."""
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)

    known_files: Set[str] = set()
    # Seed with currently known files (we'll process them first)
    logger.info(
        "Polling daemon started — monitoring %s (interval=%.1fs)",
        INTAKE_DIR,
        poll_interval,
    )

    # Initial sweep
    process_all_current()
    # After initial sweep, snapshot what's left (deferred files)
    for f in get_intake_files():
        known_files.add(str(f))

    try:
        while not _shutdown_requested:
            time.sleep(poll_interval)
            if _shutdown_requested:
                break

            current_files = get_intake_files()
            current_set = {str(f) for f in current_files}

            # Find new files
            new_files = current_set - known_files
            if new_files:
                logger.info("Poll detected %d new file(s)", len(new_files))
                for fpath_str in sorted(new_files):
                    fpath = Path(fpath_str)
                    if fpath.exists():
                        try:
                            success = process_file(fpath)
                            if success:
                                known_files.discard(fpath_str)
                            else:
                                # Keep in known set so we don't spam retries every cycle
                                known_files.add(fpath_str)
                        except Exception as exc:
                            logger.error(
                                "Error processing %s: %s",
                                fpath.name,
                                exc,
                                exc_info=True,
                            )
                            known_files.add(fpath_str)

            # Also retry previously deferred files periodically
            still_present = {str(f) for f in get_intake_files()}
            deferred = known_files & still_present
            if deferred:
                logger.debug("Retrying %d deferred file(s)", len(deferred))
                for fpath_str in sorted(deferred):
                    fpath = Path(fpath_str)
                    if fpath.exists():
                        try:
                            success = process_file(fpath)
                            if success:
                                known_files.discard(fpath_str)
                        except Exception:
                            pass  # Already logged inside process_file

            # Clean up known_files entries for files that no longer exist
            known_files = known_files & {str(f) for f in get_intake_files()}

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — stopping polling loop")

    logger.info("Polling daemon stopped")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="ARCA Intake Watcher — automatic document processing daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python intake_watcher.py              # Daemon mode (default)\n"
            "  python intake_watcher.py --once        # Process current files and exit\n"
            "  python intake_watcher.py --interval 10 # Poll every 10 seconds\n"
        ),
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--once",
        action="store_true",
        help="One-shot mode: process all files currently in intake, then exit",
    )
    mode_group.add_argument(
        "--watch",
        action="store_true",
        default=True,
        help="Daemon mode: continuously watch for new files (default)",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Poll interval in seconds for fallback polling mode (default: 5.0)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
    )

    # Also log to file in shared_storage/logs/
    log_dir = _PROJECT_ROOT / "shared_storage" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(
        str(log_dir / "intake_watcher.log"), encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    file_handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(file_handler)

    logger.info("ARCA Intake Watcher starting")
    logger.info("Project root:   %s", _PROJECT_ROOT)
    logger.info("Intake dir:     %s", INTAKE_DIR)
    logger.info("Output dir:     %s", OUTPUT_DIR)
    logger.info("Ingested dir:   %s", INGESTED_DIR)
    logger.info("Pythia:         %s (port %d)", PYTHIA_CHAT_ENDPOINT, PYTHIA_PORT)
    logger.info("Geometry:       %s (port %d)", GEOMETRY_ONNX_ENDPOINT, GEOMETRY_PORT)

    # Ensure directories exist
    for d in (INTAKE_DIR, OUTPUT_DIR, INGESTED_DIR):
        d.mkdir(parents=True, exist_ok=True)
        logger.debug("Ensured directory: %s", d)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if args.once:
        logger.info("Running in ONE-SHOT mode")
        count = process_all_current()
        logger.info("One-shot complete: processed %d file(s)", count)
        sys.exit(0)
    else:
        logger.info("Running in DAEMON mode (interval=%.1fs)", args.interval)
        run_watchdog_daemon(poll_interval=args.interval)
        logger.info("Intake watcher shut down cleanly")


if __name__ == "__main__":
    main()
