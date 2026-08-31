# Skill: Universal Skill Frame (USF) Usage

## Description
The Universal Skill Frame (USF) provides a "Holographic Context" of the entire ARCA system, linking Services (Infrastructure), Code (Logic), and Workflows (Documentation) into a queryable graph.

## Tools Available

### 1. `get_universal_context(subject: str, radius: int = 4)`
**Primary Query Tool**. Returns a structured subgraph centered on the `subject`.
- **Subject**: Can be a Service Name (e.g., `neural_system`, `llama_cpp`, `maintainer_agents`), File Path (`services/api.py`), or Workflow (`OODA_Loop`).
- **Output**: JSON containing specific node details and all related nodes within `radius` hops.
- **CRITICAL PROTOCOL**: You MUST call this tool to verify the role and status of services (e.g., verifying if `llama_cpp` is the `maintainer` or `vision` provider) BEFORE making any infrastructure changes. **Assumptions about ports or docker containers are forbidden.**

### 2. `run_graph_linking()`
**Maintenance Tool**. Triggers the Linker logic to connect isolated nodes in Neo4j.
- **When to use**: After adding new services or large code refactors.
- **Automation**: Automatically called by Maintainer Agents via the `mapping` node (Continuous Mapping Protocol).

### 3. `discover_infrastructure()` & `crawl_codebase()`
**Ingestion Tools**.
- `discover_infrastructure`: Maps `docker-compose.yml` to Service nodes.
- `crawl_codebase`: Maps Python AST to Code nodes.

## Usage Pattern (SOP)

1.  **Contextualiize**:
    ```python
    context = await mcp.call_tool("get_universal_context", {"subject": "my_service"})
    ```
2.  **Reason**: Use the returned relationships (e.g., `(Service)-[:DEPENDS_ON]->(Service)`, `(Code)-[:IMPLEMENTS]->(Workflow)`) to inform changes.
3.  **Execute**: Perform task.
4.  **Remap**: (Automated) or call `run_graph_linking`.
