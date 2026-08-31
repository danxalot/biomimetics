from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any
import logging
import logging.handlers
import os
import json

# Configure logging - both console and file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("audit_logger")

# Add file handler to persist logs
log_dir = os.environ.get("LOG_DIR", "/app/logs")
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(log_dir, "audit.jsonl"),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5  # Keep 5 backups
)
file_handler.setFormatter(logging.Formatter("%(message)s"))  # Just JSON, no timestamp prefix
logger.addHandler(file_handler)

app = FastAPI(title="ARCA Audit Logger Service")

class AuditLogEntry(BaseModel):
    timestamp: datetime = datetime.now()
    service_name: str
    event_type: str
    details: Dict[str, Any]
    severity: str = "INFO"
    user_id: Optional[str] = None
    trace_id: Optional[str] = None

@app.post("/log")
async def log_event(entry: AuditLogEntry):
    """
    Receives an audit log entry and records it.
    Logs are persisted to disk in JSONL format with optional trace_id for correlation.
    """
    try:
        # Structured logging with trace correlation
        log_data = entry.dict()
        log_data['timestamp'] = log_data['timestamp'].isoformat()
        
        # Ensure trace_id is present for correlation
        if not log_data.get('trace_id'):
            from opentelemetry.trace import get_current_span
            span = get_current_span()
            if span.is_recording():
                log_data['trace_id'] = format(span.get_span_context().trace_id, '032x')
        
        # Log to file (persisted) and console (for Docker)
        logger.info(json.dumps(log_data))
        
        # --- SILENT LISTENER INTEGRATION ---
        # asynchronously commit to Memory System for permanent record
        try:
            memory_url = os.getenv("MEMORY_SYSTEM_URL", "http://memory_system:8001")
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # Create a concise memory string
                memory_text = f"Audit Log [{entry.severity}] {entry.service_name}: {entry.event_type} - {str(entry.details)[:500]}"
                
                # Use the /document endpoint which accepts {content, source, document_type}
                payload = {
                    "content": memory_text,
                    "source": f"audit_logger_{entry.service_name}",
                    "document_type": "system_log"
                }
                
                async with session.post(f"{memory_url}/document", json=payload, timeout=2) as resp:
                     if resp.status >= 400:
                         logger.warning(f"Memory push failed: {resp.status} {await resp.text()}")
        except Exception as mem_err:
             # Do not fail request if memory push fails, just log error
            logger.warning(f"Failed to push to memory system: {mem_err}")
        # -----------------------------------

        return {"status": "logged", "trace_id": log_data.get('trace_id')}
    except Exception as e:
        logger.error(f"Failed to log event: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", "9092"))
    uvicorn.run(app, host="0.0.0.0", port=port)
