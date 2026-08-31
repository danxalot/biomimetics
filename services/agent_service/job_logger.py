
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("arca.job_logger")

class JobLogger:
    """
    Handles structured logging for Genesis jobs to ensure data sovereignty.
    Saves agent outputs, thoughts, and events to a dedicated job directory.
    """
    
    def __init__(self, job_id: str, shared_storage_path: str = "/app/shared_storage"):
        print(f"DEBUG: JobLogger __init__ for {job_id}")
        self.job_id = job_id
        self.shared_storage_path = shared_storage_path
        self.base_path = Path(shared_storage_path) / "jobs" / job_id
        
        # Initialize Redis for Observer broadcasting
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
            self.redis_client = redis.from_url(redis_url)
        except ImportError:
            self.redis_client = None
            print("Warning: redis package not installed, broadcasting disabled")
        except Exception as e:
            self.redis_client = None
            print(f"Warning: Failed to connect to Redis: {e}")

        self._ensure_job_directory()
        
    def _ensure_job_directory(self):
        """Creates the job directory structure if it doesn't exist."""
        try:
            print(f"DEBUG: Creating directories at {self.base_path}")
            self.responses_dir = Path(self.shared_storage_path) / "responses"
            self.responses_dir.mkdir(exist_ok=True, parents=True)
            print(f"DEBUG: Created responses dir at {self.responses_dir}")
            
            # Create sub-directory for events info
            (self.base_path / "events").mkdir(exist_ok=True, parents=True)
            logger.info(f"Initialized JobLogger for {self.job_id} at {self.base_path}")
        except Exception as e:
            print(f"DEBUG: FATAL ERROR in _ensure_job_directory: {e}")
            logger.error(f"Failed to create job directory {self.base_path}: {e}")

    def log_agent_output(self, agent_name: str, step_name: str, content: Any, metadata: Dict[str, Any] = None):
        """
        Logs the full output of an agent execution step.
        
        Args:
            agent_name: Name of the agent (e.g., 'architect', 'ops_orchestrator', 'local_docker')
            step_name: Name of the step or phase
            content: The main content (string, dict, or object)
            metadata: Additional metadata (model used, tokens, etc.)
        """
        try:
            agent_dir = self.base_path / agent_name
            agent_dir.mkdir(exist_ok=True)
            
            # Also save a human-readable copy to responses dir (User Request)
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                response_file = self.responses_dir / f"{agent_name}_{step_name}_{timestamp}.md"
                with open(response_file, "w") as f:
                    f.write(f"# {agent_name} - {step_name} Output\n\n")
                    f.write(f"**Job ID:** {self.job_id}\n")
                    f.write(f"**Timestamp:** {timestamp}\n\n")
                    f.write("---\n\n")
                    if isinstance(content, dict):
                        f.write(json.dumps(content, indent=2, default=str))
                    else:
                        f.write(str(content))
            except Exception as e:
                logger.error(f"Failed to write duplicate response: {e}")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{step_name}_{timestamp}.json"
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "agent": agent_name,
                "step": step_name,
                "content": content,
                "metadata": metadata or {}
            }
            
            with open(agent_dir / filename, 'w') as f:
                json.dump(log_entry, f, indent=2, default=str)
                
            logger.info(f"Logged {agent_name} output to {agent_dir / filename}")
            
            # Also append to the main event log
            self.log_event("agent_output", {
                "agent": agent_name, 
                "step": step_name, 
                "file": str(agent_dir / filename)
            })
            
        except Exception as e:
            logger.error(f"Failed to log agent output for {agent_name}: {e}")

    def log_event(self, event_type: str, details: Dict[str, Any]):
        """
        Logs a high-level system event to the central event log.
        """
        try:
            timestamp = datetime.now().isoformat()
            event_entry = {
                "timestamp": timestamp,
                "type": event_type,
                "details": details
            }
            
            event_log_path = self.base_path / "events.log"
            
            # Append as JSONL for reliability
            with open(event_log_path, 'a') as f:
                f.write(json.dumps(event_entry, default=str) + "\n")
                
        except Exception as e:
            logger.error(f"Failed to log event: {e}")

        # Broadcast to Observer Agent via Redis
        if self.redis_client:
            try:
                self.redis_client.publish("arca:activity", json.dumps(event_entry, default=str))
            except Exception as e:
                logger.error(f"Failed to publish event to Redis: {e}")

    def save_artifact(self, agent_name: str, filename: str, content: str):
        """
        Saves a specific artifact (code, plan, config) generated by an agent.
        """
        try:
            agent_dir = self.base_path / agent_name / "artifacts"
            agent_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = agent_dir / filename
            output_content = content
            
            # If content is a dict/list, dump as JSON
            if filename.endswith('.json') and not isinstance(content, str):
                output_content = json.dumps(content, indent=2)
                
            with open(file_path, 'w') as f:
                f.write(output_content)
                
            self.log_event("artifact_created", {
                "agent": agent_name,
                "artifact": filename,
                "path": str(file_path)
            })
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Failed to save artifact {filename}: {e}")
            return None
