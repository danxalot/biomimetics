"""
OTel Ingester for HSE Encoder

Subscribes to OpenTelemetry Collector metrics and traces,
encodes them to hypervectors, and updates the global state.

Integration Flow:
    OTel Collector → OTel Ingester → HSE Encoder → Redis → Geometry Kernel
                                          ↓
                          Global_State_Vector (V_State)

This module can be run standalone or imported into main.py.
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass

import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

OTEL_COLLECTOR_URL = os.environ.get("OTEL_COLLECTOR_URL", "http://otel_collector:4318")
HSE_ENCODER_URL = os.environ.get("HSE_ENCODER_URL", "http://localhost:8095")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
POLL_INTERVAL_SECONDS = int(os.environ.get("OTEL_POLL_INTERVAL", "5"))

# Service mappings for metric extraction
SERVICE_METRICS = {
    "redis": ["used_memory", "connected_clients", "ops_per_sec"],
    "postgres": ["active_connections", "transactions", "cache_hit_ratio"],
    "agent_service": ["requests_total", "latency_p99", "errors"],
    "llm_gateway": ["requests_total", "tokens_processed", "model_errors"],
    "memory_system": ["queries_total", "embedding_latency", "cache_hits"],
}


@dataclass
class OTelMetric:
    """Parsed OTel metric."""
    service: str
    metric_name: str
    value: float
    labels: Dict[str, str]
    timestamp: datetime


class OTelIngester:
    """
    Polls OTel Collector and Loki for telemetry data,
    sends encoded events to HSE Encoder.
    """
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
    
    async def start(self):
        """Start the ingester polling loop."""
        self.session = aiohttp.ClientSession()
        self.running = True
        logger.info(f"OTel Ingester started, polling every {POLL_INTERVAL_SECONDS}s")
        
        while self.running:
            try:
                await self._poll_and_encode()
            except Exception as e:
                logger.error(f"Polling error: {e}")
            
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    
    async def stop(self):
        """Stop the ingester."""
        self.running = False
        if self.session:
            await self.session.close()
    
    async def _poll_and_encode(self):
        """Poll metrics and encode to HSE."""
        metrics = await self._fetch_container_metrics()
        
        if metrics:
            await self._send_to_hse(metrics)
    
    async def _fetch_container_metrics(self) -> list[OTelMetric]:
        """Fetch metrics from container stats or OTel."""
        metrics = []
        
        try:
            # Try OTel Collector metrics endpoint
            async with self.session.get(f"{OTEL_COLLECTOR_URL}/metrics") as resp:
                if resp.status == 200:
                    # Parse Prometheus-format metrics
                    text = await resp.text()
                    metrics.extend(self._parse_prometheus_metrics(text))
        except Exception as e:
            logger.debug(f"OTel Collector unavailable: {e}")
        
        # Fallback: Query Loki for recent logs
        try:
            logs = await self._fetch_loki_logs()
            metrics.extend(logs)
        except Exception as e:
            logger.debug(f"Loki unavailable: {e}")
        
        return metrics
    
    def _parse_prometheus_metrics(self, text: str) -> list[OTelMetric]:
        """Parse Prometheus-format metrics text."""
        metrics = []
        
        for line in text.strip().split("\n"):
            if line.startswith("#") or not line:
                continue
            
            try:
                # Parse metric line: name{labels} value
                if " " in line:
                    name_labels, value_str = line.rsplit(" ", 1)
                    value = float(value_str)
                    
                    # Extract name and labels
                    if "{" in name_labels:
                        name = name_labels.split("{")[0]
                        labels_str = name_labels.split("{")[1].rstrip("}")
                        labels = self._parse_labels(labels_str)
                    else:
                        name = name_labels
                        labels = {}
                    
                    # Determine service from labels or name
                    service = labels.get("service", labels.get("job", "unknown"))
                    
                    metrics.append(OTelMetric(
                        service=service,
                        metric_name=name,
                        value=value,
                        labels=labels,
                        timestamp=datetime.utcnow()
                    ))
            except Exception:
                continue
        
        return metrics
    
    def _parse_labels(self, labels_str: str) -> Dict[str, str]:
        """Parse Prometheus-style labels."""
        labels = {}
        for part in labels_str.split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                labels[key.strip()] = value.strip('"')
        return labels
    
    async def _fetch_loki_logs(self) -> list[OTelMetric]:
        """Fetch recent logs from Loki for log-based metrics."""
        metrics = []
        
        try:
            # Query last 5 minutes of logs
            query = '{job=~".+"}'  # All jobs
            params = {
                "query": query,
                "limit": 100,
                "direction": "backward"
            }
            
            async with self.session.get(
                f"{LOKI_URL}/loki/api/v1/query_range",
                params=params
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    for stream in data.get("data", {}).get("result", []):
                        labels = stream.get("stream", {})
                        service = labels.get("service", labels.get("container", "unknown"))
                        
                        for entry in stream.get("values", []):
                            ts, log_line = entry
                            
                            # Extract error indicators
                            if "error" in log_line.lower():
                                metrics.append(OTelMetric(
                                    service=service,
                                    metric_name="error_event",
                                    value=1.0,
                                    labels={"text": log_line[:200]},
                                    timestamp=datetime.utcnow()
                                ))
        except Exception as e:
            logger.debug(f"Loki query failed: {e}")
        
        return metrics
    
    async def _send_to_hse(self, metrics: list[OTelMetric]):
        """Send metrics batch to HSE Encoder."""
        events = []
        
        for m in metrics:
            events.append({
                "type": "metric",
                "service": m.service,
                "metric_name": m.metric_name,
                "value": m.value,
                "labels": m.labels,
                "text": m.labels.get("text")
            })
        
        if not events:
            return
        
        try:
            async with self.session.post(
                f"{HSE_ENCODER_URL}/encode/batch",
                json={"events": events}
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(
                        f"Encoded {result.get('events_processed', 0)} events, "
                        f"velocity={result.get('velocity', 0):.3f}"
                    )
                else:
                    logger.warning(f"HSE encode failed: {resp.status}")
        except Exception as e:
            logger.error(f"Failed to send to HSE: {e}")


# =============================================================================
# Standalone entrypoint
# =============================================================================

async def main():
    """Run the OTel ingester standalone."""
    ingester = OTelIngester()
    try:
        await ingester.start()
    except KeyboardInterrupt:
        await ingester.stop()


if __name__ == "__main__":
    asyncio.run(main())
