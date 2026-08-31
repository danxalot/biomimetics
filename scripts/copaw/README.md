# CoPaw: Agent Execution Gateway

CoPaw (Collaborative Persona Assistant) is the central orchestration hub for the BiOS ecosystem. It manages agent execution, tool approvals, and multi-channel communication (Voice, WhatsApp, iMessage, etc.).

## Core Features

- **Multi-Channel Support**: Integrated support for Voice (Gemini Live), WhatsApp, and console interactions.
- **MCP Integration**: Direct connection to the Model Context Protocol (MCP) for tool execution (Notion, Email, GDrive).
- **Voice Interface (Puck)**: Low-latency, multimodal voice interaction using the Vultr Gemini 3.1 Live Relay.
- **Tool Guard**: Security layer for monitoring and approving sensitive tool executions.
- **Memory Sync**: Automated archiving of sessions and tasks to GCP (MemU) and local vector storage (MuninnDB).

## Getting Started

1. **Installation**:
   ```bash
   pip install -e .
   ```

2. **Configuration**:
   Modify `config_copaw/config.json` to enable/disable channels and configure API keys.

3. **Running Services**:
   - Standard Gateway: `python3 launch_copaw_services.py`
   - Voice Only (Puck): `./scripts/sys/bios-voice.sh`

## Documentation

- [Voice Instructions](VOICE_INSTRUCTIONS.md) - Setup and operation of the Puck voice interface.
- [Architecture Report](MASTER_ARCHITECTURE_REPORT.md) - Current development status and discrepancies.
- [Project Wiki](../../PROJECT_WIKI.md) - Deep dive into system internals.
