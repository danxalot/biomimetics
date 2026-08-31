---
title: BiOS Self-Updating Memory System
status: design (v0.1)
owner: Dan
maintained_by: derived — do not treat as hand-updated truth
partition: bios
---

# BiOS Self-Updating Memory System

## The core principle

Documentation goes stale because a human has to update it. Every hand-maintained
doc (Notion pages, the MOCs, even DIRECTION.md's NOW section) rots the moment the
project moves — and this project moves daily.

So the system does not *store* the current state as hand-written prose. It
**derives** the current state, on a schedule, from the primary sources that are
already changing (emails, code, commits, agent artifacts, service registries).
Nothing that represents "how things are right now" is written by hand; it is
regenerated. Hand-editing is reserved for *intent* (what we're trying to do),
never for *state* (what currently exists).

This is what makes it self-updating: the truth lives in the sources, and every
higher layer is a projection that rebuilds itself.

## The five layers

**Layer 0 — Primary sources (the only truth).**
Emails, git repos + commits, agent artifacts (Claude Code / Antigravity /
opencode output), the `services/_registry/` YAML, SAR documents, infra state.
Everything else is derived from these and can be thrown away and rebuilt.

**Layer 1 — Extraction & bounding.**
Small, typed extractors — one per source kind — that pull *only durable signal*
and drop noise. This is where the "how is information bounded and formatted"
problem is solved, concretely, per type:

- *Email* → subject, sender, date, one bounded summary paragraph, action items,
  partition. The raw body is not carried forward.
- *Commit / code change* → what changed, why (message + diff summary), which
  service, resulting state. Not the full diff.
- *Agent artifact* → decisions made, state changed, next steps. Not the
  transcript. (This is the fix for the "surplus data from artifacts" problem.)
- *Service registry* → services, ports, images, status — straight from the YAML.
- *SAR / legal* → parties, dates, references, the specific factual finding.

Every extract carries structured frontmatter (`partition`, `project`, `type`,
`source_link`, `date`, `status`, `source_hash`) and a provenance link back to
Layer 0. Extraction is incremental and idempotent via `source_hash` — unchanged
sources are never reprocessed.

**Layer 2 — Knowledge graph (Obsidian vault).**
The bounded extracts land here as partitioned markdown with `[[links]]` and
`#partition/*` tags. Human- and agent-readable, navigable. Partitions:
`life`, `life/email`, `life/legal`, `life/legal/sar`, `arca`, `bios`, `grants`,
`pythia`. (The refactored tagger now guarantees every note gets a partition,
prose or not.)

**Layer 3 — Vector memory (the retrieval layer).**
Daily, after tagging: everything is vectorised into MuninnDB (fast working
memory) + MemU (Qdrant vectors + Firestore records), with ARCA's heavy technical
corpus embedded into the OCI vector DB. Agents retrieve here **semantically** —
this is how an agent gets "current state," never from a static doc.

**Layer 4 — Self-generating overview (the "4th layer" / the wiki).**
Scheduled jobs regenerate the navigable overview *from* Layers 2–3 + git + the
service registry: per-project auto-MOCs, current-state summaries, open-item and
task indices, dashboards. This **replaces** hand-written docs. The MOCs and the
DIRECTION.md NOW section become generated outputs, not manual chores.

## The loop (autonomous, daily)

```
ingest → extract/bound (L1) → graph (L2) → vectorise (L3) → regenerate overview (L4)
```

Each arrow is a scheduled launchd job. The chain is incremental (only changed
sources) so it stays cheap as the corpus grows. Agents read from L3; humans read
L2 (Obsidian) and L4 (dashboards).

## Notion — role and guardrails

Notion is a **derived, read-only human dashboard. It is never a source of truth
and no agent ever reads it for current state.** (The old "fetch six Notion docs
at session start" rule was the exact anti-pattern — it fed agents stale state.)

Guardrails, non-negotiable:

1. **One-way only:** memory system → Notion. Never Notion → agent truth.
2. **Every generated page is stamped:** "AUTO-GENERATED — do not edit. Source:
   <link>. Generated: <timestamp>." Hand edits are overwritten on next run.
3. **Agents are forbidden** from treating Notion as current state; they read L3.
4. **Provenance:** every Notion block links back to its Layer-0/2 source.

Under those rails Notion is genuinely useful: a clean, shareable, always-there
human view of project status, the issue tracker, and the life/task tracker —
without becoming another thing that rots.

## Dashboards & task tracking

- **Task/issue tracking is derived too:** tasks are *extracted* (from emails,
  agent handoffs, code TODOs, and life/legal deadlines) into a partitioned task
  index in the graph, then projected to the dashboards. No manual task entry
  required for anything the system can already see.
- **Cloudflare (free):** host the human dashboards as a static site regenerated
  from the graph — always-on, zero dependency on the Mac being awake.
- **The life/legal tracker** (ombudsman deadlines, SAR status) is the first
  dashboard, because it's the highest-stakes and time-critical.

## Why this is robust to speed

Because no layer above L0 is authoritative, the system can be wrong for a day and
self-correct on the next run. Break a projection and it rebuilds. Add a new source
kind and you write one extractor. The faster the project moves, the more this
beats hand-maintained docs — which is exactly the regime we're in.

## Build order

1. **Delineation** (done): tagger now partitions every note. ✅
2. **Decouple + broaden sync:** vectorise the whole partitioned vault daily, not
   just emails, not gated on prose-tagging.
3. **Extractors:** email + agent-artifact extractors first (highest volume /
   highest noise), with bounded summaries + provenance.
4. **Overview generation (L4):** auto-MOCs + the life/legal tracker.
5. **Dashboards:** Notion projection (guardrailed) + Cloudflare static site.
6. **OCI link-through** for the ARCA technical corpus (Dan is provisioning OCI).
