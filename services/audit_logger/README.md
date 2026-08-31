# Audit Logger Service

This service provides a centralized audit logging facility for the ARCA system.

## API

### POST /log
Records an audit log entry.

**Payload:**
```json
{
  "timestamp": "2023-10-27T10:00:00Z",
  "service_name": "guardian_service",
  "event_type": "screening_result",
  "details": { ... },
  "severity": "INFO",
  "trace_id": "uuid..."
}
```

## Integration

Services should send logs to this service via HTTP.
Set `AUDIT_LOGGER_URL` environment variable in dependent services.

## Running

```bash
docker-compose up -d audit_logger
```
