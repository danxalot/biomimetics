# ARCA Memory System Service

A comprehensive memory management service that integrates four memory layers for the ARCA multi-agent system.

## Architecture

The memory system consists of four integrated layers:

1. **Working Memory** (SQLite): Short-term conversation context and session management
2. **Episodic Memory** (SQLite + Vector DB): Long-term semantic memory with embeddings
3. **Structural Memory** (Neo4j): Knowledge graph for relationships and concepts
4. **ReasoningBank**: Agent learning framework for trajectory analysis and strategy development

## Features

- RESTful API for all memory operations
- Rate limiting and health monitoring
- MCP integration support
- Automatic summarization and optimization
- Agent trajectory recording and learning
- Comprehensive context retrieval

## API Endpoints

### Health Check
- `GET /health` - Service health status

### Memory Operations
- `POST /conversation` - Add conversation turn
- `POST /document` - Add document to memory
- `POST /context` - Get comprehensive context
- `POST /trajectory` - Record agent trajectory
- `POST /learning` - Get learning context for agents
- `GET /strategies` - Get reasoning strategies
- `GET /stats` - Memory system statistics

## Environment Variables

- `WORKING_MEMORY_DB` - Path to working memory SQLite DB (default: `/tmp/working_memory.db`)
- `EPISODIC_MEMORY_DB` - Path to episodic memory SQLite DB (default: `/tmp/episodic_memory.db`)
- `NEO4J_URI` - Neo4j connection URI (default: `bolt://localhost:7687`)
- `NEO4J_USER` - Neo4j username (default: `neo4j`)
- `NEO4J_PASSWORD` - Neo4j password (default: `password`)
- `PORT` - Service port (default: `8001`)
- `DEBUG` - Enable debug mode (default: `false`)

## Running Locally

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables (optional):
```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"
```

3. Run the service:
```bash
python main.py
```

## Docker Deployment

Build and run with Docker:
```bash
docker build -t arca-memory-system .
docker run -p 8001:8001 arca-memory-system
```

## Testing

Test the health endpoint:
```bash
curl http://localhost:8001/health
```

Add a conversation turn:
```bash
curl -X POST http://localhost:8001/conversation \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session",
    "user_id": "user123",
    "user_message": "Hello",
    "assistant_response": "Hi there!",
    "metadata": {"source": "test"}
  }'
```

## Integration

This service integrates with:
- ARCA Orchestrator for agent coordination
- LLM Gateway for language model access
- MCP servers for tool integration
- Other ARCA services via REST APIs

## Development

The service uses FastAPI for the web framework and provides comprehensive logging and error handling. Memory operations are asynchronous for optimal performance.