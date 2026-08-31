# COLD-START AGENT TASK — Repair the BiOS Memory Layer (GCP)

**For:** grok build (or any agent with GCP `arca-471022` + gcloud access)
**Written by:** Cowork architect · 2026-07-11 · all findings verified live via the agent bridge
**You can start cold — everything you need is below.**

---

## What this system is

The BiOS memory system ingests a partitioned Obsidian vault into a two-tier store
fronted by a **GCP Cloud Function orchestrator**:
- **MuninnDB** = fast working memory (GCP-hosted, reached by the orchestrator over the VPC)
- **MemU** = deep archive (Cloud Run + Qdrant vectors + Firebase)

A nightly sync POSTs `{operation:"memorize"}` to the orchestrator for every vault
note. Retrieval is `{operation:"search"}`. **Right now retrieval returns nothing.**

> NOTE: there is ALSO a *local* MuninnDB on the Mac at `127.0.0.1:8475/8750`. That
> is the **agents-only** instance (fed into IDEs per conversation turn) and is
> SEPARATE from the GCP Muninn the orchestrator uses. Do **not** conflate them and
> do **not** modify the local one for this task.

## Verified faults (live probes, 2026-07-11)

1. **Orchestrator → GCP Muninn write is refused.** A test memorize returned:
   `{"status":"partial","source":"muninndb","memory_id":null,
   "errors":["MuninnDB: Connection failed: [Errno 111] Connection refused"]}`.
   The orchestrator cannot reach its configured Muninn. Every sync write has been
   silently failing as "partial". **This is the primary break.**
2. **MemU archive search 500s.** MemU `/health` is healthy (v1.3.1, gemini-embedding-2-preview
   1536-dim, Firebase ready), but `/search` fails: `Unexpected Response: 404 ... 404 page
   not found` — i.e. its **Qdrant collection is missing** (`memu_archive_1536`).
3. **Stale sync state.** `~/.arca/tagged_sync_state.json` records ~350 files as synced.
   It's fiction, and it blocks recovery (unchanged hashes are skipped on re-sync).

## Environment / access

- GCP project **arca-471022**; gcloud at `~/google-cloud-sdk/bin/gcloud`.
- Orchestrator (Cloud Function): `https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator`
  — ops via POST `{operation: search|memorize|consolidate|purge}`.
- MemU (Cloud Run): `https://memu-757330161781.us-central1.run.app` (/health OK, /search 500).
  Backs onto Qdrant cloud (collection `memu_archive_1536`, 1536-dim) + Firebase (arca-471022).
- GCP Muninn: orchestrator env **MUNINN_VM_URL** — source default `http://10.128.0.3:8475`
  (a GCP VPC-internal IP). **VERIFY the actual deployed value** — do not assume the default.
- Credentials Server (local): `http://127.0.0.1:8089`, header `X-API-Key` from
  `~/biomimetics/secrets/credentials_api_key`. Relevant secrets exist for GCP, OCI, Cloudflare.
- Sync/tagger code: `~/biomimetics/scripts/archivist/` (`tagged_memory_sync.py`,
  `semantic_llm_tagger.py`). Vault: `~/Google Drive/My Drive/Obsidian-life` (source of truth).

## Goals (in order — verify each before moving on)

1. **Restore orchestrator → GCP Muninn writes.**
   - Read the *deployed* orchestrator env (`gcloud functions describe memory-orchestrator
     --region us-central1`) to get the real `MUNINN_VM_URL` and VPC connector.
   - Determine whether the target GCP Muninn instance is running and reachable from the
     Cloud Function (VM up? service up? VPC connector healthy? firewall on :8475?).
   - Fix whichever is broken (start/redeploy Muninn, correct the URL, repair the connector).
   - **Success:** a test memorize returns `status:"success"` with a non-null `memory_id`.

2. **Restore MemU archive search.**
   - Recreate/repair the Qdrant collection `memu_archive_1536` (1536-dim, cosine) so MemU
     `/search` returns 200 (empty result is fine; a 500 is not).
   - **Success:** `POST {MEMU}/search {"query":"test","limit":1}` → HTTP 200.

3. **Re-populate from the vault.**
   - Delete the stale `~/.arca/tagged_sync_state.json`.
   - Re-run `~/biomimetics/scripts/archivist/tagged_memory_sync.py` (it POSTs memorize for
     every partitioned note). Confirm the summary shows notes actually *synced*, 0 errors.

4. **Verify retrieval end-to-end.**
   - `POST {orchestrator} {"operation":"search","query":"ombudsman calderdale","limit":3}`
     returns real results with non-zero `sources.working` and/or `sources.archive`.

## Guardrails

- Do NOT touch the local Muninn (`127.0.0.1`) or the `neural_system` / `traffic_cop`
  containers — separate live systems.
- Never hardcode secrets; fetch from the cred server / gcloud at runtime.
- Prefer non-destructive fixes; the Obsidian vault is the repopulation source of truth.

## Deliverable

A short report: what was *actually* broken (deployed config vs the source default), what
you changed, and a final verification transcript showing the orchestrator search returning
real results from both tiers.
