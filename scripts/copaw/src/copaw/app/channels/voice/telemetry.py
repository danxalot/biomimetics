import asyncio
import json
import logging
import time
import httpx
from typing import Dict, Any, Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

class VoiceTelemetry:
    def __init__(self, service_name="bios_voice_agent"):
        self.service_name = service_name
        self.loki_url = "http://100.70.0.13:3100/loki/api/v1/push"
        self.otel_traces_url = "http://100.70.0.13:4318/v1/traces"
        self.otel_metrics_url = "http://100.70.0.13:4318/v1/metrics"
        
        self.log_queue = asyncio.Queue(maxsize=1000)
        self.http_client = httpx.AsyncClient(timeout=5.0)
        self.running = False
        self.task = None
        
        self._setup_otel()
        
        self.tracer = trace.get_tracer(__name__)
        self.meter = metrics.get_meter(__name__)
        
        self.audio_latency_histogram = self.meter.create_histogram(
            name="voice.audio.latency",
            description="Latency of audio frames",
            unit="ms"
        )
        self.audio_rms_histogram = self.meter.create_histogram(
            name="voice.audio.rms",
            description="RMS of audio frames",
            unit="1"
        )
        
        self.current_turn_span = None
    
    def _setup_otel(self):
        try:
            resource = Resource.create({"service.name": self.service_name})
            
            # Traces
            trace_provider = TracerProvider(resource=resource)
            span_exporter = OTLPSpanExporter(endpoint=self.otel_traces_url)
            trace_provider.add_span_processor(BatchSpanProcessor(span_exporter))
            trace.set_tracer_provider(trace_provider)
            
            # Metrics
            metric_exporter = OTLPMetricExporter(endpoint=self.otel_metrics_url)
            reader = PeriodicExportingMetricReader(metric_exporter)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
        except Exception as e:
            logger.error(f"Failed to setup OTEL: {e}")

    async def start(self):
        self.running = True
        self.task = asyncio.create_task(self._log_worker())

    async def stop(self):
        self.running = False
        if self.task:
            await self.task
        await self.http_client.aclose()

    def log_event(self, event_name: str, **kwargs):
        if not self.running: return
        log_entry = {
            "event": event_name,
            "timestamp": time.time_ns(),
            **kwargs
        }
        try:
            self.log_queue.put_nowait(log_entry)
        except asyncio.QueueFull:
            pass
            
    def record_audio_frame(self, latency_ms: float, rms: float):
        try:
            self.audio_latency_histogram.record(latency_ms)
            self.audio_rms_histogram.record(rms)
        except Exception:
            pass

    def start_turn(self):
        try:
            if self.current_turn_span:
                self.current_turn_span.end()
            self.current_turn_span = self.tracer.start_span("agent_turn")
        except Exception:
            pass
        self.log_event("start_turn")

    def end_turn(self):
        try:
            if self.current_turn_span:
                self.current_turn_span.end()
                self.current_turn_span = None
        except Exception:
            pass
        self.log_event("end_turn")
        
    def tool_execution(self, tool_name: str, args: Dict[str, Any]):
        try:
            span = self.tracer.start_span(f"tool_execution: {tool_name}")
            span.set_attribute("tool.name", tool_name)
            span.set_attribute("tool.args", json.dumps(args))
            span.end()
        except Exception:
            pass
        self.log_event("tool_execution", tool_name=tool_name, args=args)

    async def _log_worker(self):
        while self.running or not self.log_queue.empty():
            try:
                logs = []
                try:
                    if not self.log_queue.empty() or self.running:
                        log = await asyncio.wait_for(self.log_queue.get(), timeout=1.0)
                        logs.append(log)
                        self.log_queue.task_done()
                        
                        while len(logs) < 50:
                            try:
                                log = self.log_queue.get_nowait()
                                logs.append(log)
                                self.log_queue.task_done()
                            except asyncio.QueueEmpty:
                                break
                except (asyncio.TimeoutError, asyncio.QueueEmpty):
                    pass
                
                if logs:
                    values = []
                    for log in logs:
                        ts = str(log.pop("timestamp"))
                        values.append([ts, json.dumps(log)])
                    
                    payload = {
                        "streams": [
                            {
                                "stream": {"service": self.service_name},
                                "values": values
                            }
                        ]
                    }
                    try:
                        await self.http_client.post(self.loki_url, json=payload)
                    except Exception as e:
                        logger.error(f"Failed to push to Loki: {e}")
            except Exception as e:
                logger.error(f"Error in log worker: {e}")
                await asyncio.sleep(1)
