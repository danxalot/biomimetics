#!/usr/bin/env python3
"""
run_pipeline.py — standalone CLI entrypoint for the Geometry Heavy Lifter.
=============================================================================
General-purpose pipeline runner.  No documents are hardcoded.
The container requires an intake source and an output root at runtime.

Usage (inside container):

    # Single document (PDF, TXT, MD, EPUB, or MOBI):
    python services/geometry_heavy_lifter/run_pipeline.py \
        --doc /intake/MyBook.pdf \
        --name "my book" \
        --objective "Extract quaternion algebra concepts" \
        --output-dir /output

    # Whole intake directory (processes all supported files found):
    python services/geometry_heavy_lifter/run_pipeline.py \
        --intake-dir /intake \
        --output-dir /output

    # Skip Phase 0 — resume from existing refined_doc.json checkpoint:
    python services/geometry_heavy_lifter/run_pipeline.py \
        --refined /output/atomized/refined/my_book/refined_doc.json \
        --name "my book" \
        --objective "Extract quaternion algebra concepts" \
        --output-dir /output

Environment variables:
    HF_TOKEN      — Hugging Face access token (required for gated models)
    STORAGE_ROOT  — Default output root if --output-dir is not given
                    (falls back to /app/shared_storage)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure /app is on PYTHONPATH when running directly
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/services")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("run_pipeline")

DEFAULT_STORAGE_ROOT = os.environ.get("STORAGE_ROOT", "/app/shared_storage")


def run_book(ingester, book: dict, skip_refine: bool = False, refined_path: str = None):
    logger.info(f"\n{'='*64}")
    logger.info(f"  BOOK: {book['name']}")
    logger.info(f"{'='*64}")

    if refined_path is None:
        pdf_path = book["pdf"]
        if not os.path.exists(pdf_path):
            logger.error(f"PDF not found: {pdf_path}")
            return None

        if not skip_refine:
            logger.info("Phase 0: Refining PDF (PPStructure + PaddleOCR)…")
            # Checkpoint: refined_doc.json written here — GPU phases can be
            # restarted independently by passing --refined to skip this step.
            refined_path = ingester.refine_pdf(pdf_path, book_name=book["name"])
        else:
            safe = book["name"].replace(" ", "_")
            storage_root = ingester.storage_root
            refined_path = f"{storage_root}/atomized/refined/{safe}/refined_doc.json"
            if not os.path.exists(refined_path):
                logger.error(f"refined_doc.json not found at {refined_path}; re-run without --skip-refine")
                return None

    logger.info(f"Phase 1+2: GPU embed + extract  (refined_doc: {refined_path})")
    stats = ingester.process_file(refined_path, objective=book["objective"])
    logger.info(f"✅ Done: {stats}")
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Geometry Heavy Lifter — general-purpose document ingestion pipeline.",
        epilog="Requires one of: --pdf, --intake-dir, or --refined.",
    )
    # ── Input (one required) ──────────────────────────────────────────────────
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--pdf",        help="Path to a single PDF (legacy alias for --doc)")
    input_group.add_argument("--doc",        help="Path to a single document (PDF, TXT, MD, EPUB, MOBI)")
    input_group.add_argument("--intake-dir", help="Directory — all supported files inside are processed")
    input_group.add_argument("--refined",    help="Path to existing refined_doc.json (skip Phase 0)")
    # ── Metadata ──────────────────────────────────────────────────────────────
    parser.add_argument("--name",        help="Book name for output folder (required with --pdf/--refined)")
    parser.add_argument("--objective",   default="Extract key concepts and geometric structures",
                        help="Concept-extraction objective prompt")
    # ── Output ────────────────────────────────────────────────────────────────
    parser.add_argument("--output-dir",  default=DEFAULT_STORAGE_ROOT,
                        help="Root output directory (default: $STORAGE_ROOT or /app/shared_storage)")
    parser.add_argument("--skip-refine", action="store_true",
                        help="With --pdf: skip Phase 0, look for existing refined_doc.json")
    args = parser.parse_args()

    # Late import so logging is configured first
    from services.geometry_heavy_lifter.core import HeavyGeometryIngester
    ingester = HeavyGeometryIngester(storage_root=args.output_dir)

    if args.intake_dir:
        supported = (".pdf", ".txt", ".md", ".epub", ".mobi")
        docs = sorted(
            p for p in Path(args.intake_dir).iterdir()
            if p.is_file() and p.suffix.lower() in supported
        )
        if not docs:
            logger.error(f"No supported files found in {args.intake_dir}")
            sys.exit(1)
        logger.info(f"Intake directory: {len(docs)} documents found in {args.intake_dir}")
        for doc in docs:
            book = {
                "pdf":       str(doc),
                "name":      doc.stem.replace("_", " "),
                "objective": args.objective,
            }
            run_book(ingester, book, skip_refine=args.skip_refine)
        return

    doc_path = args.pdf or args.doc
    if doc_path:
        book = {
            "pdf":       doc_path,
            "name":      args.name or Path(doc_path).stem.replace("_", " "),
            "objective": args.objective,
        }
        run_book(ingester, book, skip_refine=args.skip_refine)
        return

    # --refined path: jump straight to GPU phases
    if not args.name:
        name_guess = Path(args.refined).parent.name.replace("_", " ")
        logger.info(f"--name not given, inferring from path: '{name_guess}'")
        args.name = name_guess
    book = {"pdf": "", "name": args.name, "objective": args.objective}
    run_book(ingester, book, skip_refine=True, refined_path=args.refined)


if __name__ == "__main__":
    main()
