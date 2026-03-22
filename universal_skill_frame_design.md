# Universal Skill Frame (USF) Design

## 1. Objective
Enable agents to instantly retrieve a "Holographic Context" related to any subject (Service, File, Concept, Error). The USF aggregates **Infrastructure, Code, Configuration, and Workflow** data within a 4-hop graph radius, exposing it as a structured "Skill Frame".

## 2. The Unified Graph Schema

We will merge the isolated graphs into a single `KnowledgeGraph`:

### Nodes
- **Service** (`name`, `image`, `ports`) - *From Infra Discovery*
- **Module** (`path`, `name`, `language`) - *From Code Crawler*
- **Config** (`key`, `value`) - *From Infra EnvVars*
- **Workflow** (`path`, `trigger`) - *From `.agent/workflows`*
- **Concept** (`name`, `description`) - *From Documentation/Comments*

### Relationships (The "Glue")
- `(Service)-[:RUNS]->(Module)`: Links container to entrypoint code.
- `(Service)-[:CONFIGURED_BY]->(Config)`: Links container to env vars.
- `(Module)-[:IMPORTS]->(Module)`: Code dependencies.
- `(Workflow)-[:ORCHESTRATES]->(Service)`: Workflows targeting services.
- `(Workflow)-[:REFERENCES]->(Module)`: Docs citing code.

## 3. Implementation Components

### A. Data Ingesters (Existing & Enhanced)
1.  **`mcp_infra_discovery.py`**: Maps Docker Compose -> Services/Config.
2.  **`mcp_code_crawler.py`**: Maps FileSystem -> Modules/Imports.
3.  **`mcp_workflow_scanner.py` (NEW)**: Maps `.agent/workflows/*.md` -> Workflows. 
    - Extracts `@service` or file path references to create links.

### B. The "Linker" (The Missing Piece)
A heuristic engine to bridge the graphs:
- **Service -> Code**: Match `docker-compose.yml` `volumes` or `build.context` to find source directories.
- **Service -> Code**: Regex match `CMD` or `ENTRYPOINT` to find the main script.
- **Workflow -> Entity**: Parse markdown links `[file](...)` or `@mentions` to link Workflows to referenced nodes.

### C. The Universal Context Tool (`universal_skill_frame`)
**Signature**: `get_skill_frame(subject: str, radius: int = 4)`

**Logic**:
1.  **Resolution**: Fuzzy match `subject` to a Node (Service Name, Filename, Env Key).
2.  **Traversal**: Execute Cypher query for multi-hop expansion.
    ```cypher
    MATCH (start {name: $subject})
    CALL apoc.path.subgraphAll(start, {maxLevel: 4})
    YIELD nodes, relationships
    RETURN nodes, relationships
    ```
3.  **Formatting**: Convert subgraph to JSON/Markdown "Frame".

## 4. Execution Plan (Parallel Run)

As requested, we will run this **in parallel** with existing tools.

1.  **Phase 1: Ingestion Upgrade**:
    - Update `mcp_infra_discovery` to persist to the same Neo4j DB as Code Crawler.
    - Create `mcp_workflow_scanner`.

2.  **Phase 2: The Linker**:
    - Implement `mcp_graph_linker.py` to run periodically (after discovery).
    - Heuristics:
        - If Service `neural_system` mounts `./services/neural_system`, link `(Service:neural_system)-[:OWNS]->(Dir:services/neural_system)`.

3.  **Phase 3: The Tool**:
    - Implement `mcp_universal_context.py` exposing `get_skill_frame`.

4.  **Phase 4: Integration**:
    - Update `SystemAnalysisTool` (Observer) to use `get_skill_frame` for context gathering.

## 5. Example "Skill Frame" Output
For query "neural_system":

```json
{
  "subject": "neural_system (Service)",
  "context": {
    "config": {
      "PORT": "8085",
      "GENESIS_CHAIN_API_KEY": "..."
    },
    "code": [
      "services/neural_system/api.py (Entrypoint)",
      "services/neural_system/phenomenological_core.py (Imported)"
    ],
    "workflows": [
      "priority1_energy_endpoint_tasks.md (References)"
    ],
    "dependencies": [
      "redis (Service - Connected to)"
    ]
  }
}
```
