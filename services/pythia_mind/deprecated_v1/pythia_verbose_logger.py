"""
Pythia Verbose Logger - Full Process Tracing
============================================
Tracks every step of the pipeline with detailed logging
"""

import logging
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import os


# Configure verbose logging
def setup_verbose_logging(log_dir: str = "/tmp/pythia_logs"):
    """Setup comprehensive logging for the entire pipeline"""

    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Create formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler for all logs
    all_logs_file = log_path / "pythia_all.log"
    file_handler = logging.FileHandler(all_logs_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)

    # Console handler (INFO level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(console_handler)

    # Specific module loggers
    module_loggers = {
        "pythia_verbose_logger": log_path / "pythia_verbose.log",
        "qwen3vl_integration": log_path / "qwen3vl.log",
        "geometry_onnx_interpreter_v2": log_path / "geometry.log",
        "cycle_consistent": log_path / "translation.log",
        "pythia_db_service": log_path / "database.log",
    }

    for module_name, log_file in module_loggers.items():
        module_logger = logging.getLogger(module_name)
        module_logger.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        module_logger.addHandler(file_handler)

    root_logger.info(f"Verbose logging initialized. Logs in: {log_dir}")
    return log_path


class PipelineTracer:
    """Trace pipeline execution with detailed logging"""

    def __init__(self, tracer_name: str):
        self.logger = logging.getLogger(tracer_name)
        self.start_time = None
        self.step_times = {}

    def start_trace(self, operation: str, data: Optional[Dict] = None):
        """Start tracing an operation"""
        self.start_time = time.time()
        self.logger.info(f"=== START: {operation} ===")
        if data:
            self.logger.debug(f"Input data: {json.dumps(data, default=str, indent=2)}")

    def trace_step(
        self,
        step_name: str,
        data: Optional[Dict] = None,
        duration_ms: Optional[float] = None,
    ):
        """Trace a specific step"""
        elapsed = (time.time() - self.start_time) * 1000 if self.start_time else 0
        self.step_times[step_name] = duration_ms or elapsed

        msg = f"Step {step_name}: {elapsed:.2f}ms"
        if duration_ms:
            msg += f" (actual: {duration_ms:.2f}ms)"
        self.logger.info(msg)

        if data:
            self.logger.debug(
                f"Step {step_name} data: {json.dumps(data, default=str, indent=2)}"
            )

    def end_trace(self, operation: str, result: Optional[Dict] = None):
        """End tracing an operation"""
        total_time = (time.time() - self.start_time) * 1000
        self.logger.info(f"=== END: {operation} (Total: {total_time:.2f}ms) ===")
        if result:
            self.logger.debug(f"Result: {json.dumps(result, default=str, indent=2)}")

        # Log step breakdown
        if self.step_times:
            self.logger.info("Step breakdown:")
            for step, duration in self.step_times.items():
                self.logger.info(f"  {step}: {duration:.2f}ms")

    def log_error(self, error: Exception, context: Optional[str] = None):
        """Log an error with context"""
        self.logger.error(f"ERROR in {context}: {error}", exc_info=True)


# Global tracer instance
_tracer: Optional[PipelineTracer] = None


def get_tracer() -> PipelineTracer:
    """Get or create global tracer"""
    global _tracer
    if _tracer is None:
        _tracer = PipelineTracer("pythia_pipeline")
    return _tracer


if __name__ == "__main__":
    # Test the logger
    setup_verbose_logging()
    tracer = get_tracer()

    tracer.start_trace("Test Operation", {"test": "data"})
    tracer.trace_step("step1", {"result": "ok"})
    tracer.trace_step("step2", {"result": "ok"}, duration_ms=50.5)
    tracer.end_trace("Test Operation", {"success": True})
