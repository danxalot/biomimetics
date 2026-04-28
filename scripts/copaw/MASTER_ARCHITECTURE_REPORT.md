# BiOS Full Stack Architecture Map (Phase 1.5.2)

## 1. Trigger-to-Execution Pipeline
- **Input**: User Voice (Puck) / User GitHub (Issue).
- **Middle-Brain**: Cloudflare PM Agent (Gemma 4 31b) expands issues into Notion Task Briefs status: 'Ready for Dev'.
- **Local Dispatch**: Swarm Dispatcher polls Notion, claims tasks, and routes to Serena MCP.
- **Execution**: OpenCode Go (Subscription) agents execute deep analysis and code edits.

## 2. 'Puck' Voice Orchestrator
- **Status**: Stranded (Local tunnels missing).
- **Identity**: 'Puck' persona missing from launch script.
- **Delegation**: Lacks tools to feed the PM Agent.

## 3. Discrepancy Log
- [ ] bios-voice.sh lacks ssh -R 8089:8090 bridge.
- [ ] serena_notion_poller.py is missing (requires reconstruction).
- [ ] execute_opencode_task in serena_mcp_server.py is a placeholder.

## 4. Integration Blueprint
[Mermaid Diagram here - see Implementation Plan]
