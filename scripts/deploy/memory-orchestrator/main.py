"""
Memory Orchestrator Cloud Function — dual-tier GCP gateway.

Routes to:
  - MuninnDB (GCP VM, working / ACT-R Activate) — product-correct REST
  - MemU (Cloud Run, long-term archive) — store / search

Does not touch any local Muninn or local MCP wiring.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

import functions_framework

# GCP Muninn (VPC internal) + MemU Cloud Run
MUNINN_VM_URL = os.environ.get("MUNINN_VM_URL", "http://10.128.0.3:8475").rstrip("/")
MEMU_URL = os.environ.get("MEMU_URL", "https://memu-757330161781.us-central1.run.app").rstrip("/")

MAX_TOTAL_TOKENS = int(os.environ.get("MAX_TOTAL_TOKENS", "2000"))
MUNINN_TOKEN_BUDGET = int(os.environ.get("MUNINN_TOKEN_BUDGET", "1500"))
MEMU_TOKEN_BUDGET = int(os.environ.get("MEMU_TOKEN_BUDGET", "500"))
MIN_CONFIDENCE_THRESHOLD = float(os.environ.get("MIN_CONFIDENCE", "0.3"))

# Daily / on-demand Muninn → MemU assimilation
CONSOLIDATE_MIN_CONFIDENCE = float(os.environ.get("CONSOLIDATE_MIN_CONFIDENCE", "0.5"))
CONSOLIDATE_MIN_CHARS = int(os.environ.get("CONSOLIDATE_MIN_CHARS", "80"))
CONSOLIDATE_MAX_ENGRAMS = int(os.environ.get("CONSOLIDATE_MAX_ENGRAMS", "200"))
# Cap per invocation so CF timeout + Gemini embed RPM stay healthy
CONSOLIDATE_BATCH = int(os.environ.get("CONSOLIDATE_BATCH", "12"))
# auto_page: process multiple batches in one CF call (scheduler primary path)
CONSOLIDATE_MAX_BATCHES = int(os.environ.get("CONSOLIDATE_MAX_BATCHES", "8"))
# Soft wall-clock budget (seconds) for auto_page loops inside a single invocation
CONSOLIDATE_TIME_BUDGET_S = int(os.environ.get("CONSOLIDATE_TIME_BUDGET_S", "240"))

# Transient markers — never promote these into MemU archive filing
_TRANSIENT_SOURCE_MARKERS = frozenset({
    "diagnostic_probe", "repair", "repair-probe", "probe", "test",
})
_TRANSIENT_CONTENT_RE = re.compile(
    r"(?i)^(BIOS_PROBE_|BIOS_MEMU_|ombudsman calderdale (dual-write|archive|complaint after)|"
    r"\[Working memory query:)"
)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(text) // 4


def truncate_to_token_budget(text: str, budget: int) -> str:
    if estimate_tokens(text) <= budget:
        return text
    return text[: budget * 4] + "..."


def call_endpoint(
    url: str,
    payload: Optional[dict] = None,
    timeout: int = 45,
    method: str = "POST",
) -> dict:
    try:
        method_u = method.upper()
        # Never attach a body on GET/DELETE — Cloud Run rejects GET-with-body as 400
        if method_u in ("GET", "DELETE", "HEAD"):
            data = None
            headers = {}
        else:
            data = json.dumps(payload if payload is not None else {}).encode("utf-8")
            headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method_u,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode()[:300]
        except Exception:
            pass
        return {"error": f"HTTP {e.code}: {e.reason}" + (f" — {err_body}" if err_body else ""), "results": []}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e}", "results": []}
    except Exception as e:
        return {"error": str(e), "results": []}


def apply_token_budget(results: list, budget: int) -> list:
    if not results:
        return []
    sorted_results = sorted(
        results,
        key=lambda x: x.get("confidence", x.get("score", x.get("relevance", 0))),
        reverse=True,
    )
    budgeted: list = []
    tokens_used = 0
    for result in sorted_results:
        content = result.get("content", "") or ""
        content_tokens = estimate_tokens(content)
        if tokens_used + content_tokens > budget:
            remaining = budget - tokens_used
            if remaining > 10:
                result = dict(result)
                result["content"] = truncate_to_token_budget(content, remaining)
                result["truncated"] = True
                budgeted.append(result)
            break
        budgeted.append(result)
        tokens_used += content_tokens
        if tokens_used >= budget * 0.9:
            break
    return budgeted


@functions_framework.http
def process_memory_request(request):
    """
    Dual-tier GCP gateway.

    Operations:
      search | recall | query  — Muninn Activate + MemU /search
      memorize                 — dual-write Muninn engrams + MemU store
      consolidate              — daily impart: non-transient Muninn → MemU filing
      inspect                  — backend health
      purge                    — Muninn DELETE /engrams/{id} + MemU /purge
    """
    request_json = request.get_json(silent=True)
    if not request_json:
        return (
            json.dumps({"status": "error", "error": "Invalid JSON payload"}),
            400,
            {"Content-Type": "application/json"},
        )

    operation = (request_json.get("operation") or "search").lower()

    if operation in ("search", "recall", "query") or (
        "query" in request_json and operation not in ("memorize", "consolidate", "purge", "inspect")
    ):
        return handle_search(request_json)
    if operation == "memorize" or ("content" in request_json and operation not in ("consolidate",)):
        return handle_memorize(request_json)
    if operation == "consolidate":
        return handle_consolidate(request_json)
    if operation == "inspect":
        return handle_inspect(request_json)
    if operation in ("purge", "delete"):
        return handle_purge(request_json)

    return (
        json.dumps({"status": "error", "error": f"Unknown operation: {operation}"}),
        400,
        {"Content-Type": "application/json"},
    )


def _is_transient_engram(eng: dict) -> bool:
    """Skip probes / noise — keep non-durable working traces out of MemU."""
    meta = eng.get("metadata") if isinstance(eng.get("metadata"), dict) else {}
    source = str(meta.get("source") or eng.get("source") or "").lower()
    if source in _TRANSIENT_SOURCE_MARKERS or any(m in source for m in _TRANSIENT_SOURCE_MARKERS):
        return True
    if meta.get("probe") is True:
        return True
    tags = meta.get("tags") or eng.get("tags") or []
    if isinstance(tags, list):
        low = {str(t).lower().lstrip("#") for t in tags}
        if low & _TRANSIENT_SOURCE_MARKERS:
            return True
    content = (eng.get("content") or "").strip()
    if not content or len(content) < CONSOLIDATE_MIN_CHARS:
        return True
    if _TRANSIENT_CONTENT_RE.match(content):
        return True
    return False


def _derive_memu_filing(eng: dict) -> dict:
    """
    Map a Muninn engram into MemU-compatible filing metadata.

    Aligns with MemU's conceptual layers:
      L0 source provenance · L1 durable memory record · lines chat|workspace|skill
    BiOS partitions (life, bios, arca, …) become filing categories.
    """
    meta = eng.get("metadata") if isinstance(eng.get("metadata"), dict) else {}
    tags = meta.get("tags") or eng.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    partitions = meta.get("partition") or []
    if isinstance(partitions, str):
        partitions = [partitions]
    primary = meta.get("partition_primary") or (partitions[0] if partitions else None)
    if not primary:
        # Infer from tags
        for t in tags:
            ts = str(t).lstrip("#")
            if ts.startswith("partition/"):
                primary = ts.split("/", 1)[1]
                break
    primary = primary or "life"

    # MemU memory lines
    line = "workspace"
    p = primary.lower()
    if p.startswith("life") or "email" in p or "personal" in p:
        line = "chat"
    elif "skill" in p or "tool" in p:
        line = "skill"

    # Typed memory for archive retrieval filters
    memory_type = "knowledge"
    blob = (eng.get("content") or "")[:400].lower()
    if any(k in blob for k in ("prefer", "always", "never use", "style")):
        memory_type = "profile"
    elif any(k in blob for k in ("deadline", "hearing", "ombudsman", "complaint", "appointment")):
        memory_type = "event"
    elif any(k in blob for k in ("how to", "workflow", "procedure", "runbook")):
        memory_type = "skill"
        line = "skill"

    concept = (eng.get("concept") or "").strip()
    if not concept:
        # First non-empty markdown heading or first line
        for line_txt in (eng.get("content") or "").splitlines():
            s = line_txt.strip().lstrip("#").strip()
            if s:
                concept = s[:120]
                break
    if not concept:
        concept = (eng.get("content") or "")[:80]

    return {
        "layer": "L1",
        "memory_line": line,
        "memory_type": memory_type,
        "partition": partitions or [primary],
        "partition_primary": primary,
        "filing_category": primary,
        "index_topic": concept,
        "source_system": "muninn_gcp",
        "source_engram_id": eng.get("id"),
        "source_vault": eng.get("vault") or meta.get("vault") or "default",
        "assimilated_at": datetime.now(timezone.utc).isoformat(),
        "promotion": "daily_consolidate",
        "tags": tags,
        # Keep original vault metadata for provenance
        "original_metadata": {k: v for k, v in meta.items() if k != "original_metadata"},
        "muninn_confidence": eng.get("confidence"),
        "muninn_score": eng.get("score"),
    }


def _promote_engram_to_memu(eng: dict, user_id: str, dry_run: bool) -> tuple[bool, Optional[str]]:
    """Store one engram into MemU with filing metadata. Returns (ok, error_or_None)."""
    filing = _derive_memu_filing(eng)
    content = eng.get("content") or ""
    topic = filing.get("index_topic") or "memory"
    archive_body = f"# {topic}\n\n{content}"
    if dry_run:
        return True, None
    store_res = call_endpoint(
        f"{MEMU_URL}/store",
        {
            "content": archive_body[:20000],
            "user_id": user_id,
            "metadata": filing,
            "tags": list({
                f"partition/{filing['partition_primary']}",
                f"memory_type/{filing['memory_type']}",
                f"line/{filing['memory_line']}",
                "source/muninn_consolidate",
                *([str(t) for t in (filing.get("tags") or [])][:20]),
            }),
        },
        timeout=60,
    )
    ok = "error" not in store_res and store_res.get("status") in (None, "stored", "success")
    if ok:
        return True, None
    return False, f"MemU store {eng.get('id')}: {store_res.get('error') or store_res.get('detail') or store_res}"


def handle_consolidate(payload: dict) -> tuple:
    """
    Daily impart: promote non-transient GCP Muninn engrams into MemU archive filing.

    Selection (durable / non-transient):
      - confidence >= threshold (default 0.5)
      - content length >= min chars
      - not probe/diagnostic markers

    Paging:
      - Single batch: offset + batch (default)
      - Multi-offset chain / full run: auto_page=true walks offsets until
        done, max_batches, or time_budget_s (scheduler primary path)

    Write path: MemU POST /store with filing metadata (layer, memory_line, type, partition).
    Does not delete Muninn engrams (working tier retains ACT-R dynamics).
    """
    threshold = float(payload.get("threshold", CONSOLIDATE_MIN_CONFIDENCE))
    limit = int(payload.get("limit", CONSOLIDATE_MAX_ENGRAMS))
    batch = int(payload.get("batch", CONSOLIDATE_BATCH))
    dry_run = bool(payload.get("dry_run", False))
    offset = int(payload.get("offset", 0))
    auto_page = bool(payload.get("auto_page", False))
    max_batches = int(payload.get("max_batches", CONSOLIDATE_MAX_BATCHES))
    time_budget_s = int(payload.get("time_budget_s", CONSOLIDATE_TIME_BUDGET_S))
    user_id = payload.get("user_id", "default")

    listed = call_endpoint(
        f"{MUNINN_VM_URL}/api/engrams?limit={limit}",
        None,
        method="GET",
        timeout=60,
    )
    if "error" in listed:
        return (
            json.dumps({
                "status": "failed",
                "operation": "consolidation",
                "errors": [f"MuninnDB list: {listed['error']}"],
            }),
            200,
            {"Content-Type": "application/json"},
        )

    engrams = listed.get("engrams") or []
    total = listed.get("total", len(engrams))
    candidates = []
    skipped_transient = 0
    skipped_low_conf = 0

    skipped_vault = 0
    for eng in engrams:
        if _is_transient_engram(eng):
            skipped_transient += 1
            continue
        meta = eng.get("metadata") if isinstance(eng.get("metadata"), dict) else {}
        if meta.get("tagged") or meta.get("source_system") == "vault_sync":
            skipped_vault += 1
            continue
        conf = eng.get("confidence")
        if conf is None:
            conf = 1.0  # Muninn often stores durable vault notes at conf=1
        try:
            conf_f = float(conf)
        except (TypeError, ValueError):
            conf_f = 0.0
        if conf_f < threshold:
            skipped_low_conf += 1
            continue
        candidates.append(eng)

    promoted = 0
    errors: list[str] = []
    sample_ids: list[str] = []
    batch_reports: list[dict] = []
    current_offset = offset
    batches_run = 0
    t0 = time.time()

    while True:
        batch_slice = candidates[current_offset : current_offset + batch]
        if not batch_slice:
            break

        batch_promoted = 0
        for eng in batch_slice:
            ok, err = _promote_engram_to_memu(eng, user_id, dry_run)
            if ok:
                batch_promoted += 1
                promoted += 1
                if eng.get("id") and len(sample_ids) < 8:
                    sample_ids.append(str(eng["id"]))
            else:
                errors.append(err or "unknown store error")
                if len(errors) >= 15:
                    break

        batches_run += 1
        next_off = current_offset + batch
        batch_reports.append({
            "offset": current_offset,
            "processed": len(batch_slice),
            "promoted": batch_promoted,
        })
        current_offset = next_off

        if len(errors) >= 15:
            break
        if not auto_page:
            break
        if current_offset >= len(candidates):
            break
        if batches_run >= max_batches:
            break
        if (time.time() - t0) >= time_budget_s:
            break

    status = "success" if promoted and not errors else (
        "partial" if promoted else ("no_action" if not candidates else "failed")
    )
    has_more = current_offset < len(candidates)
    response = {
        "status": status,
        "operation": "consolidation",
        "dry_run": dry_run,
        "auto_page": auto_page,
        "muninn_total": total,
        "candidates": len(candidates),
        "batch_size": batch,
        "start_offset": offset,
        "end_offset": current_offset,
        "batches_run": batches_run,
        "batch_reports": batch_reports,
        "batch_processed": sum(b["processed"] for b in batch_reports),
        "promoted_count": promoted,
        "skipped_transient": skipped_transient,
        "skipped_vault_already_filed": skipped_vault,
        "skipped_low_confidence": skipped_low_conf,
        "threshold": threshold,
        "elapsed_s": round(time.time() - t0, 2),
        "has_more": has_more,
        "next_offset": current_offset if has_more else None,
        "sample_engram_ids": sample_ids,
        "errors": errors,
    }
    return (json.dumps(response), 200, {"Content-Type": "application/json"})


def handle_inspect(payload: dict) -> tuple:
    """Diagnostic view of GCP backends (Muninn list + MemU /health)."""
    listed = call_endpoint(f"{MUNINN_VM_URL}/api/engrams?limit=1", None, method="GET")
    memu_status = call_endpoint(f"{MEMU_URL}/health", {}, method="GET")

    muninn_active = "error" not in listed
    firebase = (memu_status.get("firebase") or {}) if isinstance(memu_status, dict) else {}
    response = {
        "status": "success",
        "source": "memory_orchestrator",
        "backends": {
            "muninndb_working": {
                "active": muninn_active,
                "engram_count": listed.get("total", 0) if muninn_active else 0,
                "url": MUNINN_VM_URL,
                "error": listed.get("error"),
            },
            "memu_archive": {
                "active": memu_status.get("status") == "healthy",
                "version": memu_status.get("version"),
                "qdrant_url": memu_status.get("qdrant_url"),
                "qdrant_collection": memu_status.get("qdrant_collection"),
                "firestore_ready": firebase.get("ready", False),
                "embedding": memu_status.get("embedding"),
                "agent": memu_status.get("agent"),
                "error": memu_status.get("error"),
            },
        },
    }
    return (json.dumps(response), 200, {"Content-Type": "application/json"})


def search_muninn_working(query: str, limit: int = 20) -> tuple:
    """
    Product-correct Muninn Activate: context[] + max_results.
    Falls back to engram list + keyword score if Activate empty.
    """
    # Official MuninnDB Activate contract (context array, not query string)
    muninn_payload = {
        "context": [query],
        "vault": "default",
        "max_results": limit,
    }
    muninn_raw = call_endpoint(f"{MUNINN_VM_URL}/api/activate", muninn_payload)
    results: list = []
    err = muninn_raw.get("error")

    if "activations" in muninn_raw:
        for act in muninn_raw.get("activations") or []:
            score = act.get("score", act.get("confidence", 0.0))
            conf = act.get("confidence", score)
            results.append({
                "id": act.get("id"),
                "content": act.get("content"),
                "concept": act.get("concept"),
                "confidence": conf if conf is not None else 0.0,
                "score": score,
                "score_components": act.get("score_components"),
                "metadata": act.get("metadata") or {"vault": act.get("vault", "default")},
                "source": "muninn_working",
                "why": act.get("why") or act.get("score_components"),
            })

    # Secondary path if Activate returned nothing but list works
    if not results and not err:
        listed = call_endpoint(
            f"{MUNINN_VM_URL}/api/engrams?limit=200",
            None,
            method="GET",
        )
        if "error" in listed:
            err = listed["error"]
        else:
            terms = [t for t in query.lower().split() if len(t) > 2]
            for eng in listed.get("engrams") or []:
                content = eng.get("content") or ""
                if not terms:
                    continue
                text = content.lower()
                hits = sum(1 for t in terms if t in text)
                if hits <= 0:
                    continue
                score = hits / len(terms)
                results.append({
                    "id": eng.get("id"),
                    "content": content,
                    "confidence": max(score, float(eng.get("confidence") or 0.0)),
                    "metadata": eng.get("metadata") or {"vault": eng.get("vault")},
                    "source": "muninn_working",
                })
            results.sort(key=lambda r: r.get("confidence", 0), reverse=True)
            results = results[:limit]

    return results, err


def handle_search(payload: dict) -> tuple:
    """
    Unified recall: Muninn Activate (working) + MemU /search (archive).
    Working tier first (ACT-R), then archive within token budgets.

    Archive modes (payload archive_mode or mode):
      - embedding (default): MemU vector search
      - llm_assisted: MemU vector candidates + Gemma re-rank/synthesis via MemU /complete
    """
    query = payload.get("query") or payload.get("text") or ""
    user_id = payload.get("user_id", "default")
    limit = int(payload.get("limit") or payload.get("max_results") or 20)
    archive_mode = (
        payload.get("archive_mode")
        or payload.get("mode")
        or "embedding"
    ).lower()
    if archive_mode in ("llm", "llm-assisted", "assisted"):
        archive_mode = "llm_assisted"

    muninn_results, muninn_err = search_muninn_working(query, limit=min(limit, 20))
    muninn_budgeted = apply_token_budget(muninn_results, MUNINN_TOKEN_BUDGET)

    memu_payload = {
        "query": query,
        "user_id": user_id,
        "limit": min(limit, 10 if archive_mode != "llm_assisted" else 12),
        "min_confidence": float(payload.get("min_confidence", MIN_CONFIDENCE_THRESHOLD)),
        "mode": archive_mode,
    }
    memu_results = call_endpoint(f"{MEMU_URL}/search", memu_payload, timeout=90)
    memu_list = memu_results.get("results", []) or []
    # Optional synthesis block from LLM-assisted path
    archive_synthesis = memu_results.get("synthesis") or memu_results.get("llm_synthesis")
    memu_budgeted = apply_token_budget(memu_list, MEMU_TOKEN_BUDGET)

    all_results = muninn_budgeted + memu_budgeted
    if archive_synthesis and isinstance(archive_synthesis, str) and archive_synthesis.strip():
        all_results.append({
            "id": "memu_synthesis",
            "content": archive_synthesis.strip(),
            "confidence": 1.0,
            "source": "memu_archive_synthesis",
            "metadata": {"mode": "llm_assisted"},
        })

    total_tokens = sum(estimate_tokens(r.get("content", "")) for r in all_results)

    response = {
        "status": "success",
        "source": "unified",
        "operation": "recall",
        "query": query,
        "user_id": user_id,
        "archive_mode": archive_mode,
        "results": all_results,
        "token_usage": {
            "total": total_tokens,
            "budget": MAX_TOTAL_TOKENS,
            "muninn_working": sum(estimate_tokens(r.get("content", "")) for r in muninn_budgeted),
            "memu_archive": sum(estimate_tokens(r.get("content", "")) for r in memu_budgeted),
        },
        "sources": {
            "working": len(muninn_budgeted),
            "archive": len(memu_budgeted),
            "archive_synthesis": 1 if archive_synthesis else 0,
        },
        "errors": [],
    }
    if muninn_err:
        response["errors"].append(f"MuninnDB: {muninn_err}")
    if "error" in memu_results:
        response["errors"].append(f"MemU: {memu_results['error']}")
    elif memu_results.get("detail"):
        response["errors"].append(f"MemU: {memu_results.get('detail')}")

    return (json.dumps(response), 200, {"Content-Type": "application/json"})


def vault_source_tag(source: str) -> str:
    """Stable Muninn tag for a vault path. vs:<16 hex> stays well under tag limits."""
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return f"vs:{digest}"


def _engram_list(listed: dict) -> list:
    if not isinstance(listed, dict):
        return []
    return listed.get("engrams") or listed.get("results") or listed.get("items") or []


def _engram_matches_source(eng: dict, source: str, stag: str) -> bool:
    if not source or not isinstance(eng, dict):
        return False
    meta = eng.get("metadata") if isinstance(eng.get("metadata"), dict) else {}
    if meta.get("source") == source:
        return True
    if (eng.get("concept") or "") == source:
        return True
    tags = eng.get("tags") or meta.get("tags") or []
    if isinstance(tags, list) and stag and stag in tags:
        return True
    content = eng.get("content") or ""
    needle = f"source: {source}"
    for line in content.splitlines()[:12]:
        if line.strip() == needle:
            return True
    return False


def _delete_engram(engram_id: str, vault: str = "default") -> dict:
    if not engram_id:
        return {}
    q = urllib.parse.urlencode({"vault": vault})
    return call_endpoint(
        f"{MUNINN_VM_URL}/api/engrams/{urllib.parse.quote(str(engram_id), safe='')}?{q}",
        None,
        method="DELETE",
    )


def _purge_muninn_source(source: str, previous_id: Optional[str] = None, vault: str = "default") -> tuple:
    """Soft-delete prior catalog cards for this vault path (DELETE /engrams/{id}).

    Muninn has no /api/purge. Product path is archive-by-id (restorable 7 days).
    """
    deleted: list = []
    errors: list = []
    if not source and not previous_id:
        return deleted, errors
    seen = set()
    stag = vault_source_tag(source) if source else ""

    def _drop(eid):
        if not eid or eid in seen:
            return
        seen.add(eid)
        res = _delete_engram(str(eid), vault=vault)
        err = str(res.get("error") or "")
        if err and "404" not in err:
            errors.append(f"MuninnDB DELETE {eid}: {res['error']}")
        else:
            deleted.append(str(eid))

    if previous_id:
        _drop(previous_id)

    def _scan(url: str, max_pages: int, page_size: int) -> None:
        offset = 0
        for _ in range(max_pages):
            sep = "&" if "?" in url else "?"
            listed = call_endpoint(
                f"{url}{sep}limit={page_size}&offset={offset}&vault={urllib.parse.quote(vault)}",
                None,
                method="GET",
                timeout=60,
            )
            if "error" in listed:
                errors.append(f"MuninnDB list: {listed['error']}")
                return
            batch = _engram_list(listed)
            if not batch:
                return
            for eng in batch:
                if _engram_matches_source(eng, source, stag):
                    _drop(eng.get("id"))
            if len(batch) < page_size:
                return
            offset += page_size

    if source and stag:
        _scan(
            f"{MUNINN_VM_URL}/api/engrams?tags={urllib.parse.quote(stag)}",
            max_pages=4,
            page_size=50,
        )
    # Untagged stacks from before vs: stamps: page the vault and match concept/source line.
    if source and len(deleted) <= (1 if previous_id else 0):
        _scan(f"{MUNINN_VM_URL}/api/engrams", max_pages=8, page_size=100)

    return deleted, errors


def _purge_source_both(source: str, previous_id: Optional[str] = None) -> tuple:
    """Replace path: Muninn soft-delete by id/tag, MemU purge-by-source."""
    deleted, errors = _purge_muninn_source(source, previous_id=previous_id)
    if source:
        memu_res = call_endpoint(
            f"{MEMU_URL}/purge",
            {"source": source, "timeframe": "all"},
        )
        if "error" in memu_res:
            errors.append(f"MemU purge: {memu_res['error']}")
    return deleted, errors


def handle_memorize(payload: dict) -> tuple:
    """Dual-write: Muninn engram (working) + MemU store (archive filing).

    When upsert=true or metadata.source is a vault path, purge that source
    first so an edited note replaces the previous engram instead of stacking.
    """
    content = payload.get("content", "")
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {"raw_metadata": metadata}
    user_id = payload.get("user_id", "default")
    source = metadata.get("source") or payload.get("source")
    upsert = bool(payload.get("upsert") or source)
    previous_id = payload.get("previous_id") or metadata.get("previous_id")

    content_tokens = estimate_tokens(content)
    skip_budget = bool(payload.get("skip_token_budget") or metadata.get("tagged"))
    vault_token_cap = int(os.environ.get("VAULT_TOKEN_BUDGET", "8000"))
    memu_content = content
    if not skip_budget and content_tokens > MAX_TOTAL_TOKENS:
        memu_content = truncate_to_token_budget(content, MAX_TOTAL_TOKENS)
    elif skip_budget and content_tokens > vault_token_cap:
        memu_content = truncate_to_token_budget(content, vault_token_cap)

    catalog = payload.get("catalog")
    if isinstance(catalog, str) and catalog.strip():
        muninn_content = catalog.strip()[:4000]
    else:
        # Metadata layer: Muninn never holds the full vault note.
        muninn_content = truncate_to_token_budget(content, 400)

    # Product-shaped write: concept + content + tags when available
    concept = metadata.get("concept") or metadata.get("source") or ""
    if not concept and content:
        for line in content.splitlines():
            s = line.strip().lstrip("#").strip()
            if s:
                concept = s[:120]
                break
    tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags]
    stag = vault_source_tag(source) if source else ""
    if stag:
        tags = [stag] + [t for t in tags if t != stag]
    tags = tags[:30]

    pre_purge_deleted, pre_purge_errors = ([], [])
    if upsert and (source or previous_id):
        pre_purge_deleted, pre_purge_errors = _purge_source_both(
            source, previous_id=previous_id
        )

    muninn_payload = {
        "concept": concept or "memory",
        "content": muninn_content,
        "tags": tags,
        "vault": metadata.get("vault") or "default",
        "metadata": {**metadata, "memory_role": metadata.get("memory_role") or "catalog"},
    }
    muninn_result = call_endpoint(f"{MUNINN_VM_URL}/api/engrams", muninn_payload)

    # On the way in: also file durable vault notes into MemU with partition metadata
    memu_meta = dict(metadata)
    memu_meta.setdefault("source_system", "orchestrator_memorize")
    memu_meta.setdefault("layer", "L1")
    if metadata.get("partition_primary") or metadata.get("partition"):
        memu_meta.setdefault("memory_line", "workspace")
        memu_meta.setdefault("memory_type", "knowledge")

    memu_payload = {
        "content": memu_content,
        "user_id": user_id,
        "metadata": memu_meta,
        "tags": tags or None,
    }
    memu_result = call_endpoint(f"{MEMU_URL}/store", memu_payload)

    muninn_ok = "error" not in muninn_result
    # Fail closed: Firestore-only / no-vector MemU writes must not count as done.
    memu_ok = (
        "error" not in memu_result
        and memu_result.get("status") in ("stored", "success")
        and memu_result.get("embedded") is True
    )
    if muninn_ok and memu_ok:
        status = "success"
    elif muninn_ok or memu_ok:
        status = "partial"
    else:
        status = "failed"

    response = {
        "status": status,
        "source": "unified" if (muninn_ok and memu_ok) else ("muninndb" if muninn_ok else "memu"),
        "memory_id": muninn_result.get("id", muninn_result.get("memory_id")),
        "upsert": upsert,
        "replaced_ids": pre_purge_deleted,
        "token_usage": {
            "content": estimate_tokens(memu_content),
            "catalog": estimate_tokens(muninn_content),
            "budget": vault_token_cap if skip_budget else MAX_TOTAL_TOKENS,
        },
        "errors": list(pre_purge_errors),
    }
    if "error" in muninn_result:
        response["errors"].append(f"MuninnDB: {muninn_result['error']}")
    if "error" in memu_result:
        response["errors"].append(f"MemU: {memu_result['error']}")
    elif not memu_ok and memu_result.get("detail"):
        response["errors"].append(f"MemU: {memu_result.get('detail')}")
    elif not memu_ok:
        response["errors"].append("MemU: archive write missing embedding; not marking done")

    return (json.dumps(response), 200, {"Content-Type": "application/json"})


def handle_purge(payload: dict) -> tuple:
    source_filter = payload.get("source_filter") or payload.get("source")
    timeframe = payload.get("timeframe", "48h")
    previous_id = payload.get("previous_id") or payload.get("memory_id")
    deleted, errors = _purge_source_both(source_filter, previous_id=previous_id)

    response = {
        "status": "success" if not errors else ("partial" if deleted else "failed"),
        "operation": "purge",
        "source_filter": source_filter,
        "timeframe": timeframe,
        "deleted_ids": deleted,
        "deleted_counts": {
            "muninndb": len(deleted),
            "memu": 0 if any("MemU purge" in e for e in errors) else (1 if source_filter else 0),
            "total": len(deleted),
        },
        "errors": errors,
    }
    return (json.dumps(response), 200, {"Content-Type": "application/json"})
