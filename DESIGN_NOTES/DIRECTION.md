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

## Credentials Server — single authoritative instance (fixed 2026-06-10)

**Symptom:** email tools (`read_recent_emails`) returned empty — Credentials Server
404'd `gmail-app-password` / `proton-bridge-password` even though both exist in Azure
Key Vault (`arca-mcp-kv-dae`).

**Root cause:** TWO servers fought over host port 8089. (1) The real KV-backed launchd
Python server `scripts/secret_manager/credentials_server.py` (v3.0.0-strict, SP-auth, no
fallback) bound **127.0.0.1 only**. (2) An ARCA-compose container `bios_credentials_server`
ran the `arca-mcp_server:mount` image with **no Azure creds**, bound `[::]:8089` (IPv6 all
interfaces), and — because macOS resolves `localhost`→`::1` first — **shadowed** the real
server, 404ing any secret it didn't trivially have. The SP itself could read the secrets
fine (verified 200 direct to KV); the impostor was the problem.

**Fix (canonical = the host launchd Python server):**
1. Bind it `0.0.0.0:8089` (was 127.0.0.1) so Docker-network agents reach it via
   `host.docker.internal:8089`. (BiOS commit `0a338a4`.)
2. `docker stop/rm bios_credentials_server` — removed the no-Azure impostor.
3. ARCA `docker-compose.local.yml`: repoint both `CREDENTIALS_SERVER_URL` to
   `http://host.docker.internal:8089`, add `host.docker.internal:host-gateway` to
   `extra_hosts`, delete the dead `bios_credentials_server` service. (ARCA commit `9af62f2`.)

**Verified:** `localhost:8089/secrets/{gmail-app-password,proton-bridge-password}` → 200
(23/19 chars, matching local files); a running ARCA container reaches
`host.docker.internal:8089/health` → 200. Note `redis_connected:false` on the server is
unrelated (cache layer; live KV lookups work regardless).
**Follow-up:** running ARCA containers keep the old baked-in URL until next
`docker compose up` — harmless (old target was the now-gone impostor).

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

## Voice agent status (2026-06-10, branch `fix/voice-agent-serena-opencode`)

**Fixed & verified:**
- App startup crash (`arca_bridge` config missing from `ChannelConfig` Pydantic model →
  `AttributeError`). Added `ArcaBridgeConfig`. This was blocking `bios-voice.sh` entirely.
- `render_canvas` NameError (missing `tempfile`/`webbrowser` imports).
- `serena_mcp_server.py` missing `import asyncio`.
- Vision loop crash on `websockets` 16.0 (`.closed` attr removed).
- Audio engine: ran `swift <source>` (recompiled each launch; source had iOS-only
  AVAudioSession guarded `#if os(macOS)` → never compiled → silent hang). Now runs the
  PREBUILT binary; source `#if os(iOS)` fixed; binary rebuilt + reconciled with source.
- Mic capture: `select()`+`read(960)` dropped chunks (throughput ~1/5). Replaced with
  blocking read-exact loop. NOTE: VPIO/AEC engine takes ~4.7s to warm up — NOT a hang.
- **Playback pitch (deep/slow):** player node was connected to output at `playbackFormat`
  (24kHz) but fed `hwFormat` (hardware-rate) buffers → samples clocked at 24kHz → ~half
  speed. Fixed: connect player at `hwFormat`. Kept the 24kHz→hw converter (VPIO needs the
  output node at hardware rate; removing it caused CoreAudio `-10875`).

**End-to-end VERIFIED earlier (22:25 run):** mic → turn detection → `execute_opencode_task`
→ `200 OK` → tool response to Gemini. The voice agent CAN control opencode agents.

**No-response blocker — ROOT-CAUSED & FIXED 2026-06-10 (23:xx).** `[VAD DIAG]` showed
`is_speech=False rms=0` for *every* frame across a full 28s run — not low RMS, exactly **zero**.
The pipe moved data (silence_ticks climbed normally) but every PCM sample was 0. Bisected with
standalone Swift probes (from the same shell, so TCC/VPIO ruled out — probe captured maxAbs 0.99):
the mic, VPIO, permission, and arch were all fine. **Real cause:** this Mac's built-in mic
presents a **multichannel** input (3ch raw / **6ch with VPIO**) at **96 kHz**. The engine tapped
the raw multichannel `hwFormat` and asked a single `AVAudioConverter(from: hwFormat, to: mono16k)`
to downmix **and** resample — that combo **silently emits all-zero output, no error**. Probe proof:
raw tap maxAbs=0.99, converted maxAbs=0.0.
**Fix (in `bios_audio_engine.swift`):** added `hwMonoFormat` (mono @ hw rate); the tap now uses
`hwMonoFormat` so CoreAudio reduces channels, and the converter only resamples mono→mono.
Rebuilt the prebuilt binary. Verified end-to-end: **70,575 nonzero bytes / 96KB**, full range.
**CONFIRMED WORKING 2026-06-10** by Dan: voice agent hears speech, completes turns, and
responds — pitch correct by ear. The TEMP `[VAD DIAG]` block has been removed from `send_loop`.
Two earlier red herrings chased and cleared: pitch (already fixed), VPIO/AEC suppression (AEC
actually gives the *strongest* signal). Branch `fix/voice-agent-serena-opencode` merged to main.
BiOS only replies when addressed as **"BiOS"** (persona directive in `vultr_relay_client.py`).
The relay sends `goAway` after ~9 min idle (normal); the client auto-reconnects.

**Known cosmetic:** on Ctrl-C shutdown, MCP stdio clients log
`Attempted to exit cancel scope in a different task` — a teardown race in the agentscope MCP
stdio client cleanup; harmless (happens after the engine has stopped).

## Pending follow-ups (scoped out, NOT done)
1. Wire CoPaw voice/Serena agents into the shared **muninndb `:8750`** lifecycle hooks
   (pre-prompt inject + response track). Voice currently only has the `query_memory` tool.
2. Add ARCA **reasoning-bank** proxy tools (`consult_reasoning_bank`/`reasoning_search`) to
   omni_mcp for agent-PM task scoping.
3. Confirm playback pitch by ear; if still off, adjust the engine playback format.
4. Decide whether to map BiOS into its own representational/universal-context graph.
