# BiOS Full Stack Architecture Map (Phase 1.5.2)

## 1. Trigger-to-Execution Pipeline
- **Input**: User Voice (Puck) / User GitHub (Issue).
- **Middle-Brain**: Cloudflare PM Agent (Gemma 4 31b) expands issues into Notion Task Briefs status: 'Ready for Dev'.
- **Local Dispatch**: Swarm Dispatcher polls Notion, claims tasks, and routes to Serena MCP.
- **Execution**: OpenCode Go (Subscription) agents execute deep analysis and code edits.

## 2. 'Puck' Voice Orchestrator
- **Status**: Operational (via Vultr Gemini 3.1 Live Relay).
- **Identity**: 'Puck' persona fully implemented in `vultr_relay_client.py`.
- **Delegation**: Integrated with MCP tools (Notion, Email, GDrive) via `/api/mcp/tool/execute`.

## 3. Discrepancy Log
- [x] 'Puck' persona and identity implemented.
- [x] Multi-modal tool support for Voice enabled.
- [x] `bios-voice.sh` activation script optimized for terminal use.
- [ ] serena_notion_poller.py is missing (requires reconstruction).
- [ ] execute_opencode_task in serena_mcp_server.py is a placeholder.

## 4. Integration Blueprint
[Mermaid Diagram here - see Implementation Plan]
