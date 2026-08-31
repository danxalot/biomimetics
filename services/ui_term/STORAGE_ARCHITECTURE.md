# Multi-Agent Terminal Storage Architecture

## Overview

The ARCA User Interaction Agent implements comprehensive persistent storage for all terminal interactions to ensure complete conversation continuity across multi-agent sessions (Dan, Workhorse Agent, Dev Agent).

## Storage Components

### 1. Google Cloud Firestore
**Primary persistent storage for all conversations**

#### Collections:
- **`terminal_messages`**: Individual messages with full context
  - `message_id`: Unique identifier
  - `session_id`: Session grouping
  - `content`: Message text
  - `role`: user/assistant/system
  - `agent_type`: user/workhorse_agent/dev_agent/genesis_crew/open_interpreter
  - `timestamp`: ISO format timestamp
  - `metadata`: Additional context (thread_ids, commands, etc.)

- **`terminal_sessions`**: Session metadata and state
  - `session_id`: Unique session identifier  
  - `user_email`: Associated user
  - `created_at`: Session start time
  - `last_activity`: Last interaction time
  - `context`: Session-specific data
  - `message_count`: Total messages in session

#### Query Patterns:
```python
# Load recent messages for session
messages_ref = firestore_client.collection('terminal_messages')
query = messages_ref.where('session_id', '==', session_id)\
                  .order_by('timestamp', direction=firestore.Query.DESCENDING)\
                  .limit(100)

# Get active sessions (last 24h)
sessions_ref = firestore_client.collection('terminal_sessions') 
query = sessions_ref.where('last_activity', '>=', cutoff_time)
```

### 2. Google Cloud Pub/Sub
**Real-time message distribution across agents**

#### Topics:
- **`arca-terminal-conversations`**: All terminal messages published here
  - Enables real-time synchronization between local/remote agents
  - Message format matches Firestore document structure
  - Allows multiple subscribers for monitoring/analytics

#### Message Flow:
```
User Message → Firestore (persist) → Pub/Sub (distribute) → Agent Subscribers
```

### 3. In-Memory Cache
**Performance optimization and fallback**

- Active sessions cached in memory for fast access
- Automatic fallback if Firestore unavailable  
- Session state synchronized with persistent storage

## Multi-Agent Access Patterns

### Agent Types Tracked:
- **`user`**: Direct user input (Dan)
- **`workhorse_agent`**: OCI instance agent
- **`dev_agent`**: GCP development agent
- **`genesis_crew`**: CrewAI agent responses
- **`open_interpreter`**: Code interpreter outputs
- **`llm_direct`**: Direct LLM API calls

### Message Metadata Examples:
```json
{
  "message_id": "msg_123456",
  "session_id": "session_789",
  "content": "Deploy the user interaction agent",
  "role": "user",
  "agent_type": "user", 
  "timestamp": "2025-10-25T10:30:00Z",
  "metadata": {
    "user": "danexall",
    "command_type": "deployment"
  }
}

{
  "message_id": "msg_123457",
  "session_id": "session_789", 
  "content": "Deployment initiated to Cloud Run...",
  "role": "assistant",
  "agent_type": "genesis_crew",
  "timestamp": "2025-10-25T10:30:05Z",
  "metadata": {
    "thread_id": "thread_abc123",
    "objective": "Deploy the user interaction agent"
  }
}
```

## API Endpoints for Storage Access

### Conversation History
```http
GET /api/conversation/{session_id}?limit=100
```
Returns paginated message history for session.

### Export Conversations  
```http
GET /api/conversation/{session_id}/export?format=json|txt
```
Full conversation export in JSON or text transcript format.

### Session Management
```http
GET /api/sessions
```
List all active sessions with metadata.

## Storage Reliability Features

### Automatic Fallback
- Firestore unavailable → In-memory storage
- Pub/Sub unavailable → Direct WebSocket only
- Graceful degradation with logging

### Data Durability
- All messages persisted immediately
- Session state updates on every interaction
- Cross-region Firestore replication
- Pub/Sub message retention (7 days)

### Performance Optimization
- Message batching for high-volume sessions
- Efficient Firestore indexes for chronological queries
- Session caching to minimize database reads
- Lazy loading of conversation history

## Security Considerations

### Data Protection
- Firestore security rules restrict access to authenticated users
- Pub/Sub IAM policies limit publisher/subscriber access
- Message content encrypted in transit and at rest
- Session tokens include conversation access validation

### Access Control
- Session-based message isolation
- Agent-type validation on message creation
- User-specific session filtering
- Audit logging of all storage operations

## Monitoring and Analytics

### Available Metrics
- Messages per session/agent type
- Session duration and activity patterns
- Storage operation latency and errors
- Cross-agent interaction frequency

### Cloud Logging Integration
- All storage operations logged with structured metadata
- Performance metrics exported to Cloud Monitoring
- Error alerting for storage failures
- Conversation analytics dashboard available

## Deployment Requirements

### Cloud Services
```bash
# Required APIs
gcloud services enable firestore.googleapis.com
gcloud services enable pubsub.googleapis.com
gcloud services enable secretmanager.googleapis.com

# Setup storage
./setup_storage.sh
```

### IAM Permissions
```yaml
Service Account Roles:
  - roles/datastore.user (Firestore read/write)
  - roles/pubsub.publisher (message distribution) 
  - roles/secretmanager.secretAccessor (credentials)
```

This architecture ensures that all terminal interactions between Dan, Workhorse Agent, and Dev Agent are completely preserved, searchable, and available for analysis or replay.