# ARCA Memory System Service - Deployment Guide

## Overview

The ARCA Memory System Service provides a comprehensive four-tier memory architecture:
- **Working Memory**: Short-term conversation context with SQLite
- **Episodic Memory**: Long-term semantic memory with vector embeddings
- **Structural Memory**: Knowledge graph with Neo4j
- **ReasoningBank**: Agent learning and strategy development

## Prerequisites

- Docker and Docker Compose
- Access to container registry (GHCR recommended)
- Neo4j database (optional, service degrades gracefully without it)

## Quick Start

### Local Development

1. **Clone and navigate to the service directory:**
```bash
cd services/memory_system
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Run the service:**
```bash
python main.py
```

4. **Test the service:**
```bash
curl http://localhost:8001/health
```

### Docker Deployment

1. **Build the image:**
```bash
docker build -t arca-memory-system .
```

2. **Run the container:**
```bash
docker run -p 8001:8001 \
  -e NEO4J_URI="bolt://neo4j:7687" \
  -e NEO4J_USER="neo4j" \
  -e NEO4J_PASSWORD="your_password" \
  arca-memory-system
```

### Production Deployment

1. **Build multi-platform image:**
```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t ghcr.io/your-org/arca-memory-system:latest \
  --push .
```

2. **Deploy with Docker Compose:**
```yaml
version: '3.8'
services:
  memory-system:
    image: ghcr.io/your-org/arca-memory-system:latest
    ports:
      - "8001:8001"
    environment:
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
    volumes:
      - ./data/working_memory.db:/tmp/working_memory.db
      - ./data/episodic_memory.db:/tmp/episodic_memory.db
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKING_MEMORY_DB` | `/tmp/working_memory.db` | SQLite path for working memory |
| `EPISODIC_MEMORY_DB` | `/tmp/episodic_memory.db` | SQLite path for episodic memory |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `password` | Neo4j password |
| `PORT` | `8001` | Service port |
| `DEBUG` | `false` | Enable debug mode |
| `ORACLE_DSN` | `arcadb_high` | Oracle Database Service Name |
| `ORACLE_USER` | `admin` | Oracle Database User |
| `ORACLE_PASSWORD` | - | Oracle Database Password |

### Database Setup

#### SQLite (Required)
- Working and episodic memory use SQLite
- Databases are created automatically on first run
- Mount volumes for persistence in production

#### Neo4j (Optional)
- Required for structural memory and knowledge graphs
- Service continues to operate without Neo4j (with reduced functionality)
- Use official Neo4j Docker image for easy deployment

## API Usage

### Health Check
```bash
curl http://localhost:8001/health
```

### Add Conversation Turn
```bash
curl -X POST http://localhost:8001/conversation \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_123",
    "user_id": "user_456",
    "user_message": "Hello, how are you?",
    "assistant_response": "I am doing well, thank you!",
    "metadata": {"source": "chat"}
  }'
```

### Get Context
```bash
curl -X POST http://localhost:8001/context \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_123",
    "query": "previous conversation about weather",
    "user_id": "user_456"
  }'
```

### Record Agent Trajectory
```bash
curl -X POST http://localhost:8001/trajectory \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_001",
    "task_input": "Analyze user requirements",
    "task_type": "analysis",
    "actions_taken": ["read_document", "extract_entities", "generate_summary"],
    "context_used": {"document_id": "doc_123"},
    "outcome": "success",
    "execution_time": 2.5
  }'
```

### Get Learning Context
```bash
curl -X POST http://localhost:8001/learning \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_001",
    "task_context": "document analysis and summarization"
  }'
```

## Monitoring

### Health Endpoints
- `GET /health` - Overall service health
- `GET /stats` - Memory system statistics

### Logs
- Service logs are output to stdout/stderr
- Use Docker logging drivers for centralized logging
- Key metrics are logged for monitoring

### Metrics
- Request count and latency
- Memory usage statistics
- Database connection status
- ReasoningBank strategy count

## Troubleshooting

### Common Issues

1. **Neo4j Connection Failed**
   - Check Neo4j URI and credentials
   - Ensure Neo4j is running and accessible
   - Service continues with reduced functionality

2. **Embedding Model Issues**
   - Sentence transformers may fail to download
   - Service uses fallback deterministic embeddings
   - Check network connectivity for model downloads

3. **Database Permission Issues**
   - Ensure write permissions for SQLite database files
   - Check volume mounts in Docker deployments

4. **Memory Issues**
   - Monitor memory usage with large vector databases
   - Consider database optimization for production

### Debug Mode
Enable debug logging:
```bash
export DEBUG=true
python main.py
```

## Scaling Considerations

- **Horizontal Scaling**: Stateless service, can run multiple instances
- **Database Scaling**: Consider PostgreSQL for working/episodic memory at scale
- **Vector Search**: Consider dedicated vector databases (Pinecone, Weaviate) for large datasets
- **Neo4j Clustering**: Use Neo4j cluster for high availability

## Security

- Use environment variables for sensitive configuration
- Implement authentication/authorization for production
- Use HTTPS in production deployments
- Regular security updates for dependencies
- Network segmentation for database access

## Backup and Recovery

- SQLite databases can be backed up by copying files
- Neo4j provides built-in backup tools
- Implement regular backup schedules
- Test recovery procedures regularly