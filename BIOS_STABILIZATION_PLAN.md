# BiOS System Stabilization & Implementation Plan

## Objective
The CoPaw Voice Agent (BiOS) is currently experiencing tool failures due to brittle credential handling, disabled local file access, and mismatched frontend rendering types. This implementation plan is designed for the Gemini Flash agent to systematically execute, ensuring 100% tool availability, graceful error handling, and robust local/cloud file access.

---

## Phase 1: Hardening the Credential Pipeline (GDrive & Comm Tools)
**Problem:** The `search_gdrive` and `read_gdrive_file` tools crash because `fetch_secret("gdrive-oauth-token")` returns `None` when Azure sync fails, causing `json.loads(None)` to throw a fatal `TypeError`. This instantly breaks the voice agent's tool execution loop.
**Implementation Steps:**
1. Open `scripts/copaw/copaw_omni_mcp.py`.
2. Locate the `get_drive_service()` function and all tools that call `fetch_secret` directly (e.g., WhatsApp, Email).
3. Implement a strict null-check. If `fetch_secret` returns `None`, the function MUST immediately return a graceful error string: `return "❌ Error: Missing [Tool] credentials. Please run Azure Sync."`
4. Do **not** allow `json.loads()` or API clients to execute with null tokens.

## Phase 2: Restoring Omniscient File Access (Local Disk)
**Problem:** When we disabled the `arca_mcp` client to fix the `405 Method Not Allowed` initialization crash, we inadvertently severed the agent's access to the ARCA MCP's file tools (`read_file`, `write_file`, `list_files`, `list_directory`). BiOS is currently blind to the local disk.
**Implementation Steps (Choose Route A or B):**
*   **Route A (Recommended - CoPaw Built-ins):** Open `config_copaw/config.json`. Under the `tools -> builtin_tools` section, change `"enabled": false` to `"enabled": true` for `read_file`, `write_file`, and `execute_shell_command`. This instantly restores safe, native file access to BiOS without relying on the external ARCA server.
*   **Route B (Omni Proxy):** Alternatively, add native Python implementations of `read_file` and `list_directory` directly into the `copaw_omni_mcp.py` consolidated gateway. 

## Phase 3: Resolving HUD Canvas Rendering
**Problem:** The `render_canvas` tool succeeds silently because it pushes `{ "type": "html" }` to the `/console/push` endpoint. The CoPaw frontend's Markdown parser (seen in `index-C7_Q4S16.js`) ignores or improperly sanitizes unrecognized message types, causing the canvas to never appear.
**Implementation Steps:**
1. Open `scripts/copaw/src/copaw/app/channels/voice/vultr_relay_client.py`.
2. Locate the `render_canvas` tool intercept logic.
3. Change the push payload `type` back to the universally supported `"text"`.
4. Wrap the canvas content inside a standard Markdown block (e.g., ````html ... ```` or ````markdown ... ````) so the frontend's Markdown lexer natively renders it as a structured UI component within the chat feed.

## Phase 4: Exhaustive Testing Routine
Once the Flash agent implements the above changes, it MUST execute the following testing routine using `run_shell_command`:
1. **GDrive Test:** Attempt to run `copaw_omni_mcp.py` or trigger the GDrive tool manually to ensure it returns the graceful `❌ Error` string instead of a Python traceback when credentials are missing.
2. **Local File Test:** Trigger the newly enabled `read_file` tool against a known local file (e.g., `README.md`) to verify local disk access is restored.
3. **Canvas Test:** Push a test message to `http://localhost:8090/console/push` formatted with the new Markdown structure and verify the API accepts it with a 200 OK.

---
**Flash Agent Directive:** Execute Phases 1 through 3 sequentially. Do not stop until all vulnerabilities are patched and the testing routine confirms stability.