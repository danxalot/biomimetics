"""
HeavyGeometryIngester — core business logic, no Modal imports.
==============================================================
All Modal-specific plumbing lives in modal_apps/geometry_heavy_lifter.py,
which imports this module.  When running standalone on Vultr the same class
is used directly from run_pipeline.py.

GPU phases (sequential VRAM handoff, designed for A10G 24 GB / L40S 48 GB):

  Phase 1 — vLLM Embedder  (Qwen3-VL-Embedding-2B, task="embed")
    • text chunks as plain strings
    • image crops as multimodal Qwen3-VL inputs
    • VRAM purge between phases (fully isolated in subprocess)

  Phase 2 — vLLM Instruct  (Qwen3-VL-8B-Instruct-AWQ)
    • concept extraction from text
    • concept extraction from image crops (vision tokens)
    • VRAM purge on exit (fully isolated in subprocess)

Output layout:
  /app/shared_storage/atomized/Concepts/{safe_book_name}/
    Objects.json    — concept nodes (mass, position, vector, source)
    Vectors.json    — raw high-dim embeddings
    Artifacts.json  — themes, novelty scores
"""

from __future__ import annotations

import gc
import json
import logging
import os
import time
import multiprocessing as mp
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# hf_transfer is unreliable on large models — force-disable it so HuggingFace
# falls back to the standard requests-based downloader with proper retry logic.
# Must be a forced assignment (not setdefault) to override the container default.
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

EMBED_MODEL    = "Qwen/Qwen3-VL-Embedding-2B"
INSTRUCT_MODEL = "cyankiwi/Qwen3-VL-8B-Instruct-AWQ-4bit"

logger = logging.getLogger("HeavyGeometryIngester")


def _phase1_worker(model_name: str, text_chunks: List[Any], image_crops: List[Dict], objective: str, checkpoint_path: str):
    import logging
    import json
    from PIL import Image
    from vllm import LLM
    
    worker_log = logging.getLogger("Phase1Worker")
    worker_log.info(f"Loading embedder: {model_name}")
    
    llm_embed = LLM(
        model=model_name,
        runner="pooling",
        trust_remote_code=True,
        gpu_memory_utilization=0.90,
        max_model_len=8192,
    )
    
    sanitized_chunks = []
    for c in text_chunks:
        c_str = str(c)
        clean_c = c_str.replace("<|vision_start|>", "").replace("<|image_pad|>", "").replace("<|vision_end|>", "")
        sanitized_chunks.append(clean_c)

    text_embed_inputs = [
        f"Instruct: {objective}\nText: {c[:3000]}"
        for c in sanitized_chunks
    ]
    
    worker_log.info(f"Embedding {len(text_embed_inputs)} text chunks...")
    text_embed_outputs = llm_embed.embed(text_embed_inputs)
    text_vectors = [o.outputs.embedding for o in text_embed_outputs]
    
    image_vectors = []
    if image_crops:
        inputs = []
        for crop in image_crops:
            prompt = f"<|vision_start|><|image_pad|><|vision_end|>Instruct: {objective}\nText: Represent this diagram as an embedding."
            img_path = crop.get("image_path")
            img = Image.open(img_path).convert("RGB")
            # Downscale if total pixels exceed Qwen3-VL budget (1 843 200)
            max_pixels = 1_843_200
            if img.width * img.height > max_pixels:
                ratio = (max_pixels / (img.width * img.height)) ** 0.5
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            inputs.append({"prompt": prompt, "multi_modal_data": {"image": img}})
            
        worker_log.info(f"Embedding {len(inputs)} image crops...")
        image_embed_outputs = llm_embed.embed(inputs)
        image_vectors = [o.outputs.embedding for o in image_embed_outputs]
        
    with open(checkpoint_path, "w") as f:
        json.dump({"text_vectors": text_vectors, "image_vectors": image_vectors}, f)


def _resolve_image_paths(image_crops: List[Dict], refined_dir: Path) -> None:
    """Resolve relative/stale image paths in-place against the refined doc directory."""
    for crop in image_crops:
        p = crop["image_path"]
        if not os.path.isabs(p):
            crop["image_path"] = str(refined_dir / p)
        elif not os.path.exists(p):
            parts = Path(p).parts
            crop["image_path"] = str(refined_dir / Path(*parts[-3:]))


def _atomic_json_write(path: str, data) -> None:
    """Write JSON atomically: tmp file → rename.  Prevents half-written checkpoints."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# ─────────────────────────────────────────────────────────────────────────────
# RLM (Recursive Loop) helpers — shared by Phase 2 workers
# ─────────────────────────────────────────────────────────────────────────────

def _build_rlm_prompt(objective: str, running_state: dict) -> str:
    """Build the RLM prompt with trajectory + accumulated context."""
    import json as _json
    trajectory = _json.dumps(running_state["trajectory_vector"])
    context = running_state["current_context"][:500]
    return (
        f"Objective: {objective}\n"
        f"Current System State: {trajectory}\n"
        f"Previous Context: {context}\n\n"
        "Task: detailed analysis to update the geometric state.\n"
        "1. Analyze the text chunk for key concepts (objects).\n"
        "2. Update the trajectory vector based on narrative movement.\n"
        "3. Summarize the context.\n\n"
        "CRITICAL: Output MUST be valid JSON with this exact schema:\n"
        "{\n"
        '    "vector": [float, float, float],\n'
        '    "summary": "concise summary of this chunk",\n'
        '    "objects": [\n'
        "        {\n"
        '            "id": "Concept Name",\n'
        '            "desc": "Qualitative description of the concept",\n'
        '            "mass": 0.5,\n'
        '            "position": [x, y, z]\n'
        "        }\n"
        "    ]\n"
        "}\n"
        "Output JSON only. No markdown."
    )


def _parse_rlm_response(text: str) -> dict:
    """Parse RLM JSON response, handling <think> blocks and markdown fences."""
    import json as _json, re
    text = text.strip()
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("{"):
        try:
            return _json.loads(text)
        except _json.JSONDecodeError:
            pass
    matches = re.findall(r"\{.*\}", text, re.DOTALL)
    for m in matches:
        try:
            return _json.loads(m)
        except _json.JSONDecodeError:
            continue
    return {}


def _update_running_state(state: dict, parsed: dict, chunk_index: int) -> None:
    """Update RLM running state with parsed LLM response. Merges objects by ID."""
    if "vector" in parsed and isinstance(parsed["vector"], list) and len(parsed["vector"]) == 3:
        for i in range(3):
            try:
                state["trajectory_vector"][i] += float(parsed["vector"][i])
            except (ValueError, TypeError):
                pass
        # Normalize trajectory to prevent overflow to inf on long books.
        # Preserves direction (geometric signal) while keeping values LLM-interpretable.
        import math
        mag = math.sqrt(sum(v * v for v in state["trajectory_vector"]))
        if mag > 100:
            scale = 100.0 / mag
            state["trajectory_vector"] = [v * scale for v in state["trajectory_vector"]]
    if "summary" in parsed:
        state["current_context"] = str(parsed["summary"])
    for obj in parsed.get("objects", []):
        obj_id = obj.get("id", "")
        if not obj_id:
            continue
        obj["_source_chunk"] = chunk_index
        obj.setdefault("mass", 0.5)
        obj.setdefault("position", [0, 0, 0])
        obj.setdefault("source", "text")
        state["objects"][obj_id] = obj


# ─────────────────────────────────────────────────────────────────────────────
# Batch Phase Workers (subprocess targets — isolated VRAM)
# ─────────────────────────────────────────────────────────────────────────────

def _batch_phase1_worker(model_name: str, manifest_path: str):
    """
    Phase 1: Load embedder ONCE, semantic-chunk all books, embed chunks + images.

    For each book:
      1. Join raw text blocks → full document text
      2. Run SemanticChunker (embedding-based boundary detection)
      3. Embed the resulting semantic chunks
      4. Embed image crops
      5. Write checkpoint: {semantic_chunks, text_vectors, image_vectors}

    Manifest JSON:
        {"objective": "...", "books": [{"refined_doc_path": "...", "checkpoint_path": "...", "book_name": "..."}, ...]}
    """
    import logging, json, os
    from pathlib import Path
    from PIL import Image
    from vllm import LLM
    from services.geometry_kernel.semantic_chunker import SemanticChunker, ChunkingFailure

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    wlog = logging.getLogger("BatchPhase1")

    with open(manifest_path) as f:
        manifest = json.load(f)

    objective = manifest["objective"]
    books = manifest["books"]

    # ── Load model ONCE ──
    wlog.info(f"Loading embedder: {model_name}")
    llm = LLM(model=model_name, runner="pooling", trust_remote_code=True,
              gpu_memory_utilization=0.90, max_model_len=8192)

    # ── Create embed_fn for SemanticChunker ──
    def embed_fn(texts):
        sanitized = [
            str(t).replace("<|vision_start|>", "").replace("<|image_pad|>", "").replace("<|vision_end|>", "")
            for t in texts
        ]
        outputs = llm.embed(sanitized)
        return [o.outputs.embedding for o in outputs]

    chunker = SemanticChunker(embed_fn=embed_fn)

    # ── Phase 1a: Semantic chunk all books ──
    per_book_chunks: list = []  # list of (book_entry, semantic_chunk_texts)
    for entry in books:
        with open(entry["refined_doc_path"]) as f:
            rd = json.load(f)

        raw_text_blocks = rd["text_chunks"]
        full_text = "\n\n".join(str(block) for block in raw_text_blocks)

        try:
            chunk_data = chunker.chunk_document(full_text)
            semantic_chunks = [c["text"] for c in chunk_data]
            wlog.info(
                f"  {entry['book_name']}: {len(raw_text_blocks)} raw blocks → "
                f"{len(semantic_chunks)} semantic chunks"
            )
        except ChunkingFailure as e:
            wlog.error(f"  {entry['book_name']}: Semantic chunking failed: {e}")
            raise

        per_book_chunks.append((entry, semantic_chunks))

    # ── Phase 1b: Batch-embed ALL semantic chunks + images across all books ──
    all_text_inputs: list = []
    all_image_inputs: list = []
    boundaries: list = []

    for entry, semantic_chunks in per_book_chunks:
        with open(entry["refined_doc_path"]) as f:
            rd = json.load(f)
        refined_dir = Path(entry["refined_doc_path"]).parent
        image_crops = rd["image_crops"]
        _resolve_image_paths(image_crops, refined_dir)

        t_start = len(all_text_inputs)
        for c in semantic_chunks:
            c_str = str(c).replace("<|vision_start|>", "").replace("<|image_pad|>", "").replace("<|vision_end|>", "")
            all_text_inputs.append(f"Instruct: {objective}\nText: {c_str[:3000]}")
        t_count = len(all_text_inputs) - t_start

        i_start = len(all_image_inputs)
        for crop in image_crops:
            prompt = (
                f"<|vision_start|><|image_pad|><|vision_end|>"
                f"Instruct: {objective}\nText: Represent this diagram as an embedding."
            )
            img = Image.open(crop["image_path"]).convert("RGB")
            max_pixels = 1_843_200
            if img.width * img.height > max_pixels:
                ratio = (max_pixels / (img.width * img.height)) ** 0.5
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            all_image_inputs.append({"prompt": prompt, "multi_modal_data": {"image": img}})
        i_count = len(all_image_inputs) - i_start

        boundaries.append((entry, semantic_chunks, t_start, t_count, i_start, i_count))

    wlog.info(f"Embedding {len(all_text_inputs)} semantic chunks across {len(books)} books...")
    text_out = llm.embed(all_text_inputs) if all_text_inputs else []
    all_text_vecs = [o.outputs.embedding for o in text_out]

    wlog.info(f"Embedding {len(all_image_inputs)} image crops across {len(books)} books...")
    img_out = llm.embed(all_image_inputs) if all_image_inputs else []
    all_img_vecs = [o.outputs.embedding for o in img_out]

    # ── Write per-book checkpoints atomically ──
    for entry, semantic_chunks, ts, tc, is_, ic in boundaries:
        _atomic_json_write(entry["checkpoint_path"], {
            "text_vectors": all_text_vecs[ts:ts + tc],
            "image_vectors": all_img_vecs[is_:is_ + ic],
            "semantic_chunks": semantic_chunks,
        })
        wlog.info(f"  ✅ Phase 1 checkpoint: {entry['book_name']} ({tc} chunks + {ic} images)")


def _batch_phase2_worker(model_name: str, manifest_path: str):
    """
    Phase 2: Interleaved multi-book RLM walk with batched GPU inference.

    Instead of processing books sequentially (batch=1 per chunk), all books
    are processed concurrently: each generate() call contains one chunk from
    every active book.  vLLM's continuous batching processes all sequences
    simultaneously on the GPU, achieving near-linear throughput scaling.

    State isolation is maintained: each book has its own running_state
    (trajectory, objects, context).  Batching is at the inference-engine
    level only — the RLM walk semantics are unchanged.

    When a book finishes its text chunks, its image crops are immediately
    processed and a checkpoint is written (crash-safe: completed books
    survive restarts).

    CPU threading auto-detects available cores via OpenMP/MKL defaults.
    No hardcoded core counts — works on L40S (16-core), A10G (4-core), etc.

    Manifest JSON:
        {"objective": "...", "books": [
            {"book_name": "...", "refined_doc_path": "...",
             "checkpoint_path": "...", "phase1_checkpoint": "..."}, ...
        ]}
    """
    import logging, json, os, time
    from pathlib import Path
    from PIL import Image
    from vllm import LLM, SamplingParams

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    wlog = logging.getLogger("BatchPhase2")

    with open(manifest_path) as f:
        manifest = json.load(f)

    objective = manifest["objective"]
    books_manifest = manifest["books"]

    # ── Load model ONCE with prefix caching for shared system prompt ──
    wlog.info(f"Loading instruct model: {model_name}")
    llm = LLM(model=model_name, dtype="half", trust_remote_code=True,
              gpu_memory_utilization=0.90, max_model_len=8192,
              disable_log_stats=True, enable_prefix_caching=True)
    sp = SamplingParams(temperature=0.1, max_tokens=2048, stop=["<|endoftext|>", "```\n"])

    # Shared system block — prefix-cached by vLLM across all chunks
    SYSTEM_BLOCK = (
        "<|im_start|>system\n"
        "You are a document analyzer. Extract key concepts and return ONLY valid JSON.\n"
        "<|im_end|>\n"
    )

    # ── Initialize all books ──
    active_books = []
    for entry in books_manifest:
        book_name = entry["book_name"]
        with open(entry["phase1_checkpoint"]) as f:
            p1 = json.load(f)
        with open(entry["refined_doc_path"]) as f:
            rd = json.load(f)
        refined_dir = Path(entry["refined_doc_path"]).parent
        image_crops = rd["image_crops"]
        _resolve_image_paths(image_crops, refined_dir)

        active_books.append({
            "entry": entry,
            "book_name": book_name,
            "semantic_chunks": p1["semantic_chunks"],
            "image_crops": image_crops,
            "chunk_idx": 0,
            "running_state": {
                "trajectory_vector": [0.0, 0.0, 0.0],
                "objects": {},
                "current_context": "",
            },
            "per_chunk_responses": [],
        })
        wlog.info(f"  Queued: {book_name} — {len(p1['semantic_chunks'])} chunks")

    total_chunks = sum(len(b["semantic_chunks"]) for b in active_books)
    processed = 0
    t0 = time.time()
    wlog.info(
        f"Starting interleaved RLM walk: {len(active_books)} books, "
        f"{total_chunks} total chunks (batch size = {len(active_books)})"
    )

    # ── Main interleaved loop ──
    while active_books:
        # Build batch: one chunk from each active book
        batch_prompts = []
        batch_map = []  # maps position in batch → index in active_books

        for idx, book in enumerate(active_books):
            chunk = book["semantic_chunks"][book["chunk_idx"]]
            rlm_prompt = _build_rlm_prompt(objective, book["running_state"])
            prompt = (
                SYSTEM_BLOCK +
                f"<|im_start|>user\n{rlm_prompt}\n\nPassage:\n{str(chunk)[:3000]}<|im_end|>\n"
                "<|im_start|>assistant\n"
            )
            batch_prompts.append(prompt)
            batch_map.append(idx)

        # Single batched generate — vLLM processes all sequences concurrently
        outputs = llm.generate(batch_prompts, sp)

        # Update each book's state from its output
        completed_indices = []
        for pos, (book_idx, output) in enumerate(zip(batch_map, outputs)):
            book = active_books[book_idx]
            response = output.outputs[0].text
            book["per_chunk_responses"].append(response)

            parsed = _parse_rlm_response(response)
            _update_running_state(book["running_state"], parsed, book["chunk_idx"])
            book["chunk_idx"] += 1
            processed += 1

            if book["chunk_idx"] >= len(book["semantic_chunks"]):
                completed_indices.append(book_idx)

        # Progress logging
        elapsed = time.time() - t0
        cps = processed / elapsed if elapsed > 0 else 0
        wlog.info(
            f"  {processed}/{total_chunks} chunks "
            f"(batch={len(active_books)}, {cps:.1f} chunks/s)"
        )

        # Finalize completed books: process images + write checkpoint
        for idx in sorted(completed_indices, reverse=True):
            book = active_books.pop(idx)
            _finalize_book_phase2(llm, sp, book, objective, wlog)

    elapsed = time.time() - t0
    wlog.info(
        f"Phase 2 complete: {processed} chunks across "
        f"{len(books_manifest)} books in {elapsed:.0f}s "
        f"({processed / elapsed:.1f} chunks/s)"
    )


def _finalize_book_phase2(llm, sp, book: dict, objective: str, wlog) -> None:
    """Process image crops for a completed book and write its Phase 2 checkpoint."""
    import json
    from PIL import Image

    book_name = book["book_name"]
    image_crops = book["image_crops"]
    running_state = book["running_state"]

    # ── Batch image concept extraction ──
    image_outputs = []
    if image_crops:
        img_inputs = []
        for crop in image_crops:
            caption = crop.get("caption", "")
            cap_note = f' Caption: "{caption}".' if caption else ""
            system = (
                f"Objective: {objective}.{cap_note} "
                "Examine this geometric diagram carefully. "
                "Extract every distinct geometric concept, mathematical relationship, "
                "or structural pattern visible. "
                "Output JSON ONLY: "
                '{{"objects": [{{"id": "ConceptName", "desc": "precise description", "mass": 25.0}}]}}'
            )
            prompt = (
                f"<|im_start|>system\n{system}<|im_end|>\n"
                "<|im_start|>user\n"
                "<|vision_start|><|image_pad|><|vision_end|>"
                "Examine this diagram and extract geometric concepts as JSON."
                "<|im_end|>\n"
                "<|im_start|>assistant\n"
            )
            img = Image.open(crop["image_path"]).convert("RGB")
            max_pixels = 1_843_200
            if img.width * img.height > max_pixels:
                ratio = (max_pixels / (img.width * img.height)) ** 0.5
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            img_inputs.append({"prompt": prompt, "multi_modal_data": {"image": img}})

        wlog.info(f"  Processing {len(img_inputs)} image crops for {book_name}...")
        img_out = llm.generate(img_inputs, sp)
        image_outputs = [o.outputs[0].text for o in img_out]

    # ── Write checkpoint (crash-safe: book survives restarts) ──
    _atomic_json_write(book["entry"]["checkpoint_path"], {
        "text_outputs": book["per_chunk_responses"],
        "image_outputs": image_outputs,
        "trajectory": running_state["trajectory_vector"],
        "accumulated_objects": list(running_state["objects"].values()),
    })
    wlog.info(
        f"  ✅ Phase 2: {book_name} — "
        f"{len(running_state['objects'])} objects, "
        f"trajectory={[round(v, 3) for v in running_state['trajectory_vector']]}"
    )


def _phase2_worker(model_name: str, text_chunks: List[Any], image_crops: List[Dict], objective: str, output_path: str):
    import logging
    import json
    from PIL import Image
    from vllm import LLM, SamplingParams
    
    worker_log = logging.getLogger("Phase2Worker")
    worker_log.info(f"Loading instruct model: {model_name}")
    
    llm_instruct = LLM(
        model=model_name,
        dtype="half",
        trust_remote_code=True,
        gpu_memory_utilization=0.90,
        max_model_len=8192,
        disable_log_stats=True,
    )
    sp = SamplingParams(temperature=0.1, max_tokens=2048, stop=["<|endoftext|>", "```\n"])
    
    text_prompts = []
    for c in text_chunks:
        c_str = str(c)
        system = (
            f"Objective: {objective}. "
            "Extract key geometric concepts from the following passage. "
            "Output JSON ONLY: "
            '{{"objects": [{{"id": "ConceptName", "desc": "description", "mass": 0.5}}]}}'
        )
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{c_str[:3000]}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        text_prompts.append(prompt)
        
    worker_log.info(f"Extracting concepts from {len(text_prompts)} text chunks...")
    text_outputs_raw = llm_instruct.generate(text_prompts, sp)
    text_outputs = [o.outputs[0].text for o in text_outputs_raw]
    
    image_outputs = []
    if image_crops:
        inputs = []
        for crop in image_crops:
            caption = crop.get("caption", "")
            cap_note = f' Caption: "{caption}".' if caption else ""
            system = (
                f"Objective: {objective}.{cap_note} "
                "Examine this geometric diagram carefully. "
                "Extract every distinct geometric concept, mathematical relationship, "
                "or structural pattern visible. "
                "Output JSON ONLY: "
                '{{"objects": [{{"id": "ConceptName", "desc": "precise description", "mass": 25.0}}]}}'
            )
            prompt = (
                f"<|im_start|>system\n{system}<|im_end|>\n"
                "<|im_start|>user\n"
                "<|vision_start|><|image_pad|><|vision_end|>"
                "Examine this diagram and extract geometric concepts as JSON."
                "<|im_end|>\n"
                "<|im_start|>assistant\n"
            )
            img = Image.open(crop["image_path"]).convert("RGB")
            max_pixels = 1_843_200
            if img.width * img.height > max_pixels:
                ratio = (max_pixels / (img.width * img.height)) ** 0.5
                img = img.resize(
                    (int(img.width * ratio), int(img.height * ratio)),
                    Image.LANCZOS,
                )
            inputs.append({"prompt": prompt, "multi_modal_data": {"image": img}})
            
        worker_log.info(f"Extracting concepts from {len(inputs)} image crops...")
        image_outputs_raw = llm_instruct.generate(inputs, sp)
        image_outputs = [o.outputs[0].text for o in image_outputs_raw]
        
    with open(output_path, "w") as f:
        json.dump({"text_outputs": text_outputs, "image_outputs": image_outputs}, f)


class HeavyGeometryIngester:
    """
    Stateless helper — instantiate once, call refine_pdf() then process_file().
    No GPU resources held between calls; every method loads and purges vLLM.

    Args:
        storage_root: Base directory for all outputs (refined_doc checkpoints +
                      final Concepts output).  Defaults to the STORAGE_ROOT env
                      var, falling back to /app/shared_storage.
    """
    def __init__(self, storage_root: str = None):
        self.storage_root = (
            storage_root
            or os.environ.get("STORAGE_ROOT", "/app/shared_storage")
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 0: PDF refinement (CPU — PPStructure + PaddleOCR)
    # ─────────────────────────────────────────────────────────────────────────

    def refine_pdf(self, pdf_path: str, book_name: Optional[str] = None) -> str:
        """
        Run PdfRefinery on *pdf_path* (or direct read for .md) and serialise the result to a JSON file
        next to the source file.

        Returns the path to the refined_doc.json.
        """
        if book_name is None:
            book_name = Path(pdf_path).stem

        safe = book_name.replace(" ", "_").replace("/", "_")
        work_dir = f"{self.storage_root}/atomized/refined/{safe}"
        logger.info(f"refine_pdf: '{book_name}' → {work_dir}")
        os.makedirs(work_dir, exist_ok=True)
        refined_path = os.path.join(work_dir, "refined_doc.json")

        # Skip expensive OCR if checkpoint already exists and source hasn't changed.
        if os.path.exists(refined_path) and os.path.getsize(refined_path) > 100:
            logger.info(f"✅ refine_pdf SKIP (checkpoint exists) → {refined_path}")
            return refined_path

        ext = Path(pdf_path).suffix.lower()

        if ext in (".md", ".txt"):
            with open(pdf_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Store the full text as raw blocks — semantic chunking happens in
            # Phase 1 via SemanticChunker (embedding-based boundary detection).
            # We split into paragraphs here only as raw extraction units that
            # Phase 1 will re-join and semantically re-chunk.
            raw_blocks = [c.strip() for c in content.split("\n\n") if c.strip()]
            if not raw_blocks and content.strip():
                raw_blocks = [content.strip()]
                
            with open(refined_path, "w") as f:
                json.dump({
                    "source_pdf":    pdf_path,
                    "book_name":     book_name,
                    "text_chunks":   raw_blocks,
                    "image_crops":   [],
                    "markdown_path": pdf_path,
                    "stats":         {"pages": 1, "text_chunks": len(raw_blocks), "image_crops": 0, "total_text_chars": len(content)},
                }, f, indent=2)
            logger.info(f"✅ refine_pdf ({ext}) done → {refined_path}")
            return refined_path

        if ext == ".epub":
            return self._refine_epub(pdf_path, book_name, work_dir, refined_path)

        if ext == ".mobi":
            return self._refine_mobi(pdf_path, book_name, work_dir, refined_path)

        from services.pdf_to_embedding.document_refinery import PdfRefinery
        refinery = PdfRefinery(work_dir=work_dir)
        doc = refinery.refine(pdf_path, book_name=book_name)

        refined_dir = Path(work_dir)
        # Store image_path as relative to the refined_doc.json directory so the
        # checkpoint is portable across different mount points / storage roots.
        crops_data = []
        for c in doc.image_crops:
            d = asdict(c)
            try:
                d["image_path"] = str(Path(d["image_path"]).relative_to(refined_dir))
            except ValueError:
                pass  # already relative or on a different drive — leave as-is
            crops_data.append(d)
        with open(refined_path, "w") as f:
            json.dump({
                "source_pdf":    doc.source_pdf,
                "book_name":     doc.book_name,
                "text_chunks":   doc.text_chunks,
                "image_crops":   crops_data,
                "markdown_path": doc.markdown_path,
                "stats":         doc.stats,
            }, f, indent=2)

        logger.info(f"✅ refine_pdf done → {refined_path}  stats={doc.stats}")
        return refined_path

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 0 helpers: EPUB / MOBI extraction
    # ─────────────────────────────────────────────────────────────────────────

    def _refine_epub(self, epub_path: str, book_name: str, work_dir: str, refined_path: str) -> str:
        """Extract text and images from an EPUB into refined_doc.json."""
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup

        book = epub.read_epub(epub_path)
        text_chunks: list[str] = []
        image_crops: list[dict] = []
        img_count = 0

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), "html.parser")
                text = soup.get_text(separator="\n").strip()
                if text:
                    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
                    text_chunks.extend(blocks)

                for img_tag in soup.find_all("img"):
                    img_src = img_tag.get("src")
                    if not img_src:
                        continue
                    img_item = book.get_item_with_href(img_src)
                    if img_item:
                        img_count += 1
                        img_filename = f"epub_img_{img_count}.png"
                        img_save_path = os.path.join(work_dir, img_filename)
                        with open(img_save_path, "wb") as fh:
                            fh.write(img_item.get_content())
                        image_crops.append({
                            "image_path": img_filename,
                            "page_num":   0,
                            "bbox":       [0, 0, 0, 0],
                            "caption":    f"EPUB image {img_count}",
                        })

        total_chars = sum(len(c) for c in text_chunks)
        with open(refined_path, "w") as f:
            json.dump({
                "source_pdf":    epub_path,
                "book_name":     book_name,
                "text_chunks":   text_chunks,
                "image_crops":   image_crops,
                "markdown_path": epub_path,
                "stats":         {"pages": 1, "text_chunks": len(text_chunks),
                                  "image_crops": img_count, "total_text_chars": total_chars},
            }, f, indent=2)
        logger.info(f"✅ refine_pdf (.epub) done → {refined_path}  "
                     f"chunks={len(text_chunks)} images={img_count}")
        return refined_path

    def _refine_mobi(self, mobi_path: str, book_name: str, work_dir: str, refined_path: str) -> str:
        """Convert MOBI → EPUB via calibre's ebook-convert, then extract."""
        import subprocess

        epub_path = os.path.join(work_dir, f"{Path(mobi_path).stem}.epub")
        logger.info(f"Converting MOBI → EPUB: {mobi_path}")
        result = subprocess.run(
            ["ebook-convert", mobi_path, epub_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ebook-convert failed: {result.stderr[:500]}")

        logger.info(f"MOBI → EPUB conversion done: {epub_path}")
        return self._refine_epub(epub_path, book_name, work_dir, refined_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 1 + 2: GPU embedding + concept extraction
    # ─────────────────────────────────────────────────────────────────────────

    def process_file(self, refined_doc_path: str, objective: str = "Extract geometric concepts") -> Dict:
        """
        Read a refined_doc.json, embed everything, extract concepts, write outputs.
        Routes through batch_process_files for unified semantic chunking + RLM pipeline.
        Returns a stats dict.
        """
        t0 = time.time()
        results = self.batch_process_files([refined_doc_path], objective=objective)
        if not results:
            raise RuntimeError(f"process_file failed for {refined_doc_path}")
        stats = next(iter(results.values()))
        stats["elapsed_s"] = round(time.time() - t0, 1)
        return stats

    # ─────────────────────────────────────────────────────────────────────────
    # Batch processing: single model load for N books
    # ─────────────────────────────────────────────────────────────────────────

    def batch_process_files(self, refined_paths: List[str],
                            objective: str = "Extract geometric concepts") -> Dict[str, dict]:
        """
        Process multiple refined docs with a single model load per GPU phase.

        Checkpoint strategy (crash-safe):
          • Phase 1 → per-book ``phase1_vectors.json``  (skip if valid on restart)
          • Phase 2 → per-book ``phase2_outputs.json``   (skip if valid on restart)
          • Phase 3 → per-book ``Objects/Vectors/Artifacts.json`` in Concepts dir

        Returns ``{book_name: stats_dict}`` for every successfully processed book.
        """
        t0 = time.time()
        results: Dict[str, dict] = {}

        # ── Load all refined docs ────────────────────────────────────────────
        book_data: List[Dict] = []
        for rp in refined_paths:
            if not os.path.exists(rp):
                logger.warning(f"refined_doc not found, skipping: {rp}")
                continue
            with open(rp) as f:
                rd = json.load(f)
            refined_dir = Path(rp).parent
            _resolve_image_paths(rd["image_crops"], refined_dir)

            book_data.append({
                "book_name":        rd["book_name"],
                "text_chunks":      rd["text_chunks"],
                "image_crops":      rd["image_crops"],
                "refined_doc_path": rp,
                "refined_dir":      refined_dir,
                "phase1_checkpoint": str(refined_dir / "phase1_vectors.json"),
                "phase2_checkpoint": str(refined_dir / "phase2_outputs.json"),
            })

        if not book_data:
            return results

        logger.info(f"batch_process_files: {len(book_data)} books loaded")

        # ── PHASE 1: Batch embed ─────────────────────────────────────────────
        uncached_p1 = []
        for b in book_data:
            cp = b["phase1_checkpoint"]
            if os.path.exists(cp) and os.path.getsize(cp) > 100:
                if os.path.getmtime(cp) >= os.path.getmtime(b["refined_doc_path"]):
                    logger.info(f"  [Phase 1 SKIP] {b['book_name']} (checkpoint valid)")
                    continue
            uncached_p1.append(b)

        if uncached_p1:
            logger.info(
                f"  [Phase 1] {len(uncached_p1)} books need embedding "
                f"({len(book_data) - len(uncached_p1)} cached)"
            )
            manifest_path = f"{self.storage_root}/atomized/refined/_batch_p1_manifest.json"
            _atomic_json_write(manifest_path, {
                "objective": objective,
                "books": [
                    {
                        "book_name": b["book_name"],
                        "refined_doc_path": b["refined_doc_path"],
                        "checkpoint_path": b["phase1_checkpoint"],
                    }
                    for b in uncached_p1
                ],
            })
            ctx = mp.get_context("spawn")
            p = ctx.Process(target=_batch_phase1_worker, args=(EMBED_MODEL, manifest_path))
            p.start()
            p.join()
            if p.exitcode != 0:
                raise RuntimeError("Batch Phase 1 subprocess crashed.")
            if os.path.exists(manifest_path):
                os.unlink(manifest_path)

        # Load phase 1 results for all books
        for b in book_data:
            with open(b["phase1_checkpoint"]) as f:
                vc = json.load(f)
            b["text_vectors"]  = vc["text_vectors"]
            b["image_vectors"] = vc["image_vectors"]
            b["semantic_chunks"] = vc.get("semantic_chunks", b["text_chunks"])
            logger.info(
                f"  Loaded Phase 1: {b['book_name']} — "
                f"{len(b['text_vectors'])} text + {len(b['image_vectors'])} image vectors, "
                f"{len(b['semantic_chunks'])} semantic chunks"
            )

        # ── PHASE 2: Batch instruct ──────────────────────────────────────────
        uncached_p2 = []
        for b in book_data:
            cp = b["phase2_checkpoint"]
            if os.path.exists(cp) and os.path.getsize(cp) > 100:
                logger.info(f"  [Phase 2 SKIP] {b['book_name']} (checkpoint valid)")
                continue
            uncached_p2.append(b)

        if uncached_p2:
            logger.info(
                f"  [Phase 2] {len(uncached_p2)} books need concept extraction "
                f"({len(book_data) - len(uncached_p2)} cached)"
            )
            manifest_path = f"{self.storage_root}/atomized/refined/_batch_p2_manifest.json"
            _atomic_json_write(manifest_path, {
                "objective": objective,
                "books": [
                    {
                        "book_name": b["book_name"],
                        "refined_doc_path": b["refined_doc_path"],
                        "checkpoint_path": b["phase2_checkpoint"],
                        "phase1_checkpoint": b["phase1_checkpoint"],
                    }
                    for b in uncached_p2
                ],
            })
            ctx = mp.get_context("spawn")
            p2 = ctx.Process(target=_batch_phase2_worker, args=(INSTRUCT_MODEL, manifest_path))
            p2.start()
            p2.join()
            if p2.exitcode != 0:
                raise RuntimeError("Batch Phase 2 subprocess crashed.")
            if os.path.exists(manifest_path):
                os.unlink(manifest_path)

        # Load phase 2 results for all books
        for b in book_data:
            with open(b["phase2_checkpoint"]) as f:
                p2_data = json.load(f)
            b["text_outputs"]        = p2_data["text_outputs"]
            b["image_outputs"]       = p2_data["image_outputs"]
            b["trajectory"]          = p2_data.get("trajectory", [0, 0, 0])
            b["accumulated_objects"] = p2_data.get("accumulated_objects", [])

        # ── PHASE 3: Per-book PCA + assembly + output ────────────────────────
        for b in book_data:
            try:
                stats = self._assemble_book_output(b)
                results[b["book_name"]] = stats
                # Clean up intermediate checkpoints on success
                for cp in [b["phase1_checkpoint"], b["phase2_checkpoint"]]:
                    if os.path.exists(cp):
                        os.unlink(cp)
            except Exception as e:
                logger.error(f"Phase 3 failed for {b['book_name']}: {e}")
                # Keep checkpoints so the next run can skip phases 1+2

        elapsed = time.time() - t0
        logger.info(f"✅ batch_process_files done: {len(results)}/{len(book_data)} books in {elapsed:.0f}s")
        return results

    def _assemble_book_output(self, book: Dict) -> Dict:
        """Phase 3: Assemble solar system from RLM-accumulated objects + image concepts."""
        from services.geometry_kernel.clever_artifacts import extract_clever_artifacts

        book_name         = book["book_name"]
        semantic_chunks   = book.get("semantic_chunks", book["text_chunks"])
        image_crops       = book["image_crops"]
        text_vectors      = book["text_vectors"]
        image_vectors     = book["image_vectors"]
        image_outputs     = book["image_outputs"]
        trajectory        = book.get("trajectory", [0, 0, 0])
        accumulated_objs  = book.get("accumulated_objects", [])

        logger.info(f"  [Phase 3] Assembling {book_name}...")

        # ── Text objects: use RLM-accumulated objects (already merged by ID) ──
        objects_list: List[Dict] = []
        for obj in accumulated_objs:
            chunk_idx = obj.pop("_source_chunk", 0)
            obj.setdefault("source", "text")
            # Assign the embedding vector from the chunk this object last appeared in
            if chunk_idx < len(text_vectors):
                obj["vector"] = text_vectors[chunk_idx]
            else:
                obj["vector"] = text_vectors[-1] if text_vectors else []
            # Position comes from the LLM's RLM response (already set on the object)
            objects_list.append(obj)

        # ── Image objects: parse + PCA project (independent of RLM state) ──
        image_objects: List[Dict] = []
        if image_crops:
            image_objects = self._parse_image_outputs(image_outputs, image_crops, image_vectors)
            # PCA project image vectors for position assignment
            if image_vectors:
                img_projected = self._pca_project(image_vectors)
            else:
                img_projected = []
            for j, obj in enumerate(image_objects):
                crop_idx = obj.pop("_crop_idx", j % max(len(image_vectors), 1))
                obj.setdefault("mass", 25.0)
                obj.setdefault("source", "image")
                obj["vector"] = image_vectors[crop_idx] if crop_idx < len(image_vectors) else []
                obj["position"] = img_projected[crop_idx] if crop_idx < len(img_projected) else [0.0, 0.0, 0.0]
                objects_list.append(obj)

        logger.info(f"   ↳ {book_name}: {len(objects_list)} concept objects assembled.")

        safe_name = book_name.replace(" ", "_").replace("/", "_")
        out_dir   = f"{self.storage_root}/atomized/Concepts/{safe_name}"
        os.makedirs(out_dir, exist_ok=True)

        # Write core outputs atomically
        all_vectors = text_vectors + image_vectors
        _atomic_json_write(f"{out_dir}/Vectors.json", all_vectors)
        _atomic_json_write(f"{out_dir}/Objects.json", objects_list)

        # Solar system model with trajectory from RLM walk
        geometric_model = {"objects": objects_list, "trajectory": trajectory}
        artifacts_data = None
        try:
            artifacts = extract_clever_artifacts(
                geometric_model, "\n".join(str(c) for c in semantic_chunks[:50])
            )
            artifacts_data = artifacts if isinstance(artifacts, dict) else artifacts.to_dict()
            _atomic_json_write(f"{out_dir}/Artifacts.json", artifacts_data)
        except Exception as _e:
            logger.warning(f"Artifacts extraction failed for {book_name} ({_e}) — skipped.")

        # Write the full solar system model
        solar_system = {
            "system_id": book_name,
            "gravity_well": {"concept": "geometric concept extraction", "mass": len(semantic_chunks)},
            "objects": objects_list,
            "trajectory": trajectory,
            "analysis_artifacts": artifacts_data,
        }
        _atomic_json_write(f"{out_dir}/SolarSystem.json", solar_system)

        return {
            "book":          book_name,
            "text_objects":  len(objects_list) - len(image_objects),
            "image_objects": len(image_objects),
            "total_objects": len(objects_list),
            "output_data": {
                "objects":   objects_list,
                "vectors":   all_vectors,
                "artifacts": artifacts_data,
                "trajectory": trajectory,
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_image_outputs(self, outputs: List[str], image_crops: List[Dict], image_vectors) -> List[Dict]:
        objects = []
        for i, text in enumerate(outputs):
            parsed = self._robust_parse(text)
            for obj in parsed.get("objects", []):
                obj["page_number"] = image_crops[i].get("page_number")
                obj["image_path"]  = image_crops[i].get("image_path")
                obj["_crop_idx"]   = i  # source crop index for vector lookup
                objects.append(obj)
        return objects

    def _robust_parse(self, text: str) -> Dict:
        try:
            text = text.strip()
            if text.startswith("```json"): text = text[7:]
            if text.startswith("```"):     text = text[3:]
            if text.endswith("```"):       text = text[:-3]
            return json.loads(text.strip())
        except Exception:
            return {}

    def _pca_project(self, vectors: List[List[float]]) -> List[List[float]]:
        if len(vectors) < 3:
            return [[0.0, 0.0, 0.0]] * len(vectors)
        try:
            import numpy as np
            from sklearn.decomposition import PCA
            
            X = np.array(vectors, dtype=np.float32)
            pca = PCA(n_components=3)
            proj = pca.fit_transform(X)
            
            # Normalize to [-1, 1] range
            max_val = np.abs(proj).max()
            if max_val > 0:
                proj = proj / max_val
            
            return proj.tolist()
        except ImportError:
            # Fallback: manual SVD-based PCA using NumPy
            import numpy as np
            
            X = np.array(vectors, dtype=np.float32)
            centered = X - X.mean(axis=0)
            
            # SVD
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            
            # Project onto first 3 principal components
            proj = centered @ Vt[:3].T
            
            # Normalize
            max_val = np.abs(proj).max()
            if max_val > 0:
                proj = proj / max_val
            
            return proj.tolist()
        except Exception as e:
            logger.warning(f"PCA failed ({e}), returning zero positions.")
            return [[0.0, 0.0, 0.0]] * len(vectors)
