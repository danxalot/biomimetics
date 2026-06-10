# BiOS ⇄ ARCA — Architecture & Boundary Decisions

> Status: **active** — decisions recorded 2026-06-10. Owner: Dan. Agents (Claude, Antigravity,
> CoPaw swarm) MUST read this before changing cross-project wiring.

## Core principle

**BiOS is the master / personal-assistant layer. ARCA is an independently-deployable product
that happens to be the first project BiOS manages.**

- ARCA **never** imports or depends on BiOS. ARCA must stay shippable on its own.
- BiOS depends on ARCA through **one narrow, explicit contract**, and that contract lives
  entirely inside the BiOS gateway (`omni_mcp`) as a set of **proxy tools**.
- ARCA's MCP server (`:8086 /mcp`) may expose 150+ tools for ARCA's own product use; BiOS only
  ever calls the **whitelisted subset** it proxies. Adding an ARCA capability to BiOS = adding a
  proxy tool to `omni_mcp`, nothing more.

## The three rings

```
┌─ BiOS (master / personal assistant) ───────────────────────────────┐
│  omni_mcp  ← THE BiOS gateway. All agents talk to this.             │
│   ├─ Native BiOS: email, gdrive, whatsapp, secrets, GCP memory     │
│   ├─ serena_opencode: dispatch dev tasks to OpenCode models (local) │
│   └─ ARCA contract (proxy tools) ──────────┐                        │
│  Shared local muninndb (:8750) ────────────┼─ Hebbian engram store, │
│   (pre-prompt injection + response track)  │  shared by all agents  │
└─────────────────────────────────────────────┼──────────────────────┘
                                              │ narrow, versioned surface
┌─ ARCA (independently deployable product) ───┼──────────────────────┐
│  mcp_server (:8086 /mcp, streamable-HTTP)   ▼                       │
│   BiOS consumes ONLY: serena_* , get_universal_context,            │
│   reasoning bank (consult_reasoning_bank / reasoning_search),      │
│   dispatch_agent. Everything else is ARCA-internal.                │
└────────────────────────────────────────────────────────────────────┘
```

## Decisions (2026-06-10)

1. **ARCA boundary mechanism: proxy-via-`omni_mcp` only.**
   The `arca_mcp` SSE client in `config_copaw/config.json` is **removed** — it pointed at
   `:8086/sse` but the container speaks streamable-HTTP at `/mcp`, so it 404'd on every boot,
   and it was redundant (omni_mcp already reaches `:8086/mcp` and works). Single chokepoint =
   clean, auditable boundary.

2. **ARCA memory layers BiOS may read** (for agent-PM task scoping):
   - **Representational / universal context** — `get_universal_context` + `arca_system_query`.
     Note: today this surfaces *system-related* info only. Whether to widen it is open (see below).
   - **Reasoning bank** — `consult_reasoning_bank` / `reasoning_search` (ARCA's accumulated
     strategies/trajectories). *Proxy tools to be added in a follow-up — not done this session.*

3. **Shared local muninndb** is NOT a queryable DB you bolt on as an MCP client. It is a
   **Hebbian engram store wired into the agent lifecycle via two hooks**:
   - `UserPromptSubmit` → `muninn_prompt_inject.sh` (recall + where-left-off → inject context)
   - post-response → `muninn_response_track.sh` (`muninn_remember` the turn)
   `omni_mcp.query_memory` already reads both muninn (`:8750`) AND GCP memory-orchestrator via
   one `query` facility — that is the manual/secondary path. The **lifecycle hooks** are the
   primary path. Claude Code has them installed (`~/.claude/settings.json` + project
   `.claude/settings.json`). **Gap:** the CoPaw voice agent only has the `query_memory` tool, no
   inject/track lifecycle — so it does not yet participate in the shared Hebbian loop. Wiring
   Serena + CoPaw agents into the same `:8750` lifecycle is a **follow-up**.

## Open questions (not yet decided)

- **Map the BiOS project into a representational/universal-context graph too?** ARCA has one
  (system-scoped). A symmetric BiOS graph would let the agent-PM reason over BiOS structure the
  same way. Worth doing once the cross-project contract stabilizes — deferred.
- How much non-system ARCA context (episodic/graph beyond `get_universal_context`) BiOS actually
  needs — unknown at this stage; add proxies on demand rather than speculatively.

## Verified-working as of 2026-06-10

- `omni_mcp` serena proxy → ARCA `:8086/mcp` `serena_chat` returns correctly.
- `serena_opencode` local MCP client → `execute_opencode_task` (model `deepseek-v4-pro`) returns.
  (`qwen-3.7-max` is NOT supported on the OpenCode `go` endpoint — use deepseek/kimi.)
- muninndb `:8750` alive, 34 tools; Claude Code hooks installed.

## Real path for the voice agent (NOT the React app)

`scripts/sys/bios-voice.sh` → `copaw app --port 8090` (voice channel) → `vultr_relay_client`
→ Vultr relay (`ws://…:8765`) → Gemini Live → tools via `POST /api/mcp/tool/execute`.
Tools declared to Gemini in `…/channels/voice/mcp_tool_definitions.py::get_all_declarations()`.
The browser React app `gemini-live-voice/` was an orphan (referenced by nothing) and was **deleted**.
