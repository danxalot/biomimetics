"""
ARCA Unified Logging Utility
Provides trace ID propagation and structured logging across all services.
"""

import logging
import json
from typing import Optional, Dict, Any
from opentelemetry.trace import get_current_span
from opentelemetry.baggage import get_baggage
import contextvars

# Context var for trace ID
trace_id_context = contextvars.ContextVar('trace_id', default=None)


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging with trace ID correlation."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with optional trace_id."""
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add trace_id if available
        trace_id = get_trace_id()
        if trace_id:
            log_data["trace_id"] = trace_id
        
        # Add extra fields if present
        if hasattr(record, 'trace_id'):
            log_data["trace_id"] = record.trace_id
        
        # Add any extra fields from the record
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'created', 'levelname', 'levelno', 
                              'pathname', 'filename', 'module', 'funcName', 'lineno', 
                              'exc_info', 'exc_text', 'stack_info', 'relativeCreated',
                              'thread', 'threadName', 'processName', 'process', 'message',
                              'asctime', 'taskName', 'trace_id']:
                    if not key.startswith('_'):
                        try:
                            log_data[key] = value
                        except (TypeError, ValueError):
                            pass
        
        return json.dumps(log_data)


def get_trace_id() -> Optional[str]:
    """
    Extract trace ID from current OpenTelemetry span context.
    Falls back to context var if span not available.
    
    Returns:
        Trace ID as hex string or None
    """
    # Try to get from context var first
    ctx_trace_id = trace_id_context.get()
    if ctx_trace_id:
        return ctx_trace_id
    
    # Try to get from OTEL span
    try:
        span = get_current_span()
        if span and span.is_recording():
            trace_id = span.get_span_context().trace_id
            if trace_id:
                return format(trace_id, '032x')
    except Exception:
        pass
    
    # Try to get from baggage (W3C trace context)
    try:
        baggage = get_baggage("traceparent")
        if baggage:
            # Extract trace-id from traceparent format: version-trace-id-parent-flags
            parts = baggage.split('-')
            if len(parts) >= 2:
                return parts[1]
    except Exception:
        pass
    
    return None


def set_trace_id(trace_id: str) -> None:
    """Set trace ID in context var."""
    trace_id_context.set(trace_id)


def configure_logging(service_name: str, log_level: str = "INFO", 
                     log_file: Optional[str] = None) -> logging.Logger:
    """
    Configure structured logging for a service with optional file output.
    
    Args:
        service_name: Name of the service for logging
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file (if None, only console)
    
    Returns:
        Configured logger instance
    """
    import os
    
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(StructuredFormatter())
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
    
    return logger


def add_trace_to_log(logger: logging.Logger, level: str = "INFO", **kwargs):
    """
    Log with automatic trace ID injection.
    
    Usage:
        from arca_logging import add_trace_to_log, configure_logging
        logger = configure_logging("my_service")
        add_trace_to_log(logger, "INFO", message="user.login", user_id="123")
    """
    extra = {"trace_id": get_trace_id()} if get_trace_id() else {}
    extra.update(kwargs)
    
    log_func = getattr(logger, level.lower(), logger.info)
    
    # Build message from kwargs
    message = kwargs.pop('message', '')
    if not message:
        message = json.dumps(kwargs)
    
    log_func(message, extra=extra)
