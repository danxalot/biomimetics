# ARCA MCP Client & Smart Interface

The **MCP Client Service** (`mcp_client`) is the **Authorized Gateway** for interacting with the ARCA Maintainer Agents and Data Hub. It provides a secure, monitored, and skills-aware interface for executing tasks.

## 🏗 Architecture

The service runs two key components:
1. **Client Interface Server (Port 8092)**: A FastAPI server that exposes high-level skills tools (like `delegate_task`). It enforces protocols and tracks skill usage.
2. **CLI (`cli.py`)**: A command-line tool that talks to the *local* Client Interface Server via RPC, allowing scripts to execute tools easily.

## 🧬 Autonomous Remediation & Supervision

ARCA features an autonomous health-monitoring and repair loop integrated with the orchestration layer:

1.  **Alert Manager**: Monitors container health and system metrics, publishing alerts to Redis (`arca:health:alerts`).
2.  **Serena Supervisor**: The Real Serena (`agent_service`) listens to a dedicated RabbitMQ `serena_supervisor_queue` for complex or migrated tasks.
3.  **Model Roles**:
    *   **Reasoning**: Serena uses `devstral-2` (via `llm_gateway`) for deep diagnosis.
    *   **Primary Execution**: `maintainer_agents` (Port 8090) uses `qwen3-vl-2b` for complex vision and code tasks.
    *   **Secondary Execution**: `maintainer_agents_secondary` (Port 8091) uses `qwen3-0.6b` for fast file/git ops. **(NO CODE JOBS)**.
    *   **Observer**: Monitors all activity via the `arca:activity` stream.

When Serena identifies a repair path, she dispatches tasks to the `maintainer_agents` using the standard protocols documented here.

## 🚀 Execution Protocol (CRITICAL)

**NEVER** call `maintainer_agents` directly via HTTP. The execution firewall will block you.
**ALWAYS** use the `mcp_client` to route tasks via RPC.

### Correct Dispatch Method (RPC)

From the host (or any script), execute the task inside the `mcp_client` container using the CLI:

```bash
# General Syntax
docker exec mcp_client python3 /app/cli.py \
  --tool delegate_task \
  --args '{"task": "<NATURAL_LANGUAGE_TASK>", "agent_hint": "<AGENT_TYPE>"}'

# Example: Verify Energy Endpoint
docker exec mcp_client python3 /app/cli.py \
  --tool delegate_task \
  --args '{"task": "Verify /energy endpoint in services/neural_system/api.py", "agent_hint": "code_maintainer"}'
```

> [!IMPORTANT]
> - **Tool Name**: Always use `delegate_task` (not `mcp_agent_dispatch` or `dispatch_agent`).
> - **Arguments**: Provide a natural language `task` and an optional `agent_hint` (`docker`, `git`, `code_maintainer`, `security`).


This ensures:
1. **Firewall Compliance**: The request originates from a trusted container.
2. **Skills Tracking**: The Client Interface logs skill usage and performance.
3. **Logic Routing**: `agent_hint` is used to route to the correct agent (Docker, Git, Code).

## 🛠 `cli.py` Usage

The CLI is a thin wrapper around the JSON-RPC protocol.

```bash
usage: cli.py [-h] --tool TOOL --args ARGS

MCP Client CLI

options:
  -h, --help   show this help message and exit
  --tool TOOL  Name of the MCP tool to call (e.g., delegate_task)
  --args ARGS  JSON string of arguments
```

## 🧠 Smart Routing logic

The `delegate_task` tool automatically routes your natural language request to the correct agent based on `agent_hint` or keyword analysis:

- **hint="docker"** -> `dispatch_agent(docker)`
- **hint="git"** -> `dispatch_agent(git)`
- **hint="code_maintainer"** -> `dispatch_agent(code_maintainer)` (Primary Agent Only)
- **hint="security"** -> `dispatch_agent(security)`

### Topology Mapping
The client interface understands the split-brain execution model. Jobs with `agent_hint="code_maintainer"` are always routed to the Primary Agent (Port 8090). Simple file/git operations without code analysis may be routed to the Secondary Agent (Port 8091) to maximize throughput.

## 📂 Service Structure

- `mcp_client.py`: The main service logic (FastAPI server + Logic).
- `cli.py`: The CLI entry point.
- `requirements.txt`: Dependencies (aiohttp, uvicorn, etc).
- `Dockerfile`: Deployment configuration.

## ⚠️ Troubleshooting

- **"RPC Error: Method not supported"**: You are likely trying to call lower-level MCP methods (like `initialize`) on the Client Interface. Use `delegate_task`.
- **"Connection Refused"**: Ensure the `mcp_client` container is running (`docker ps`).
- **"Execution Blocked"**: You are bypassing this client and hitting `maintainer_agents` directly. Don't do that.
