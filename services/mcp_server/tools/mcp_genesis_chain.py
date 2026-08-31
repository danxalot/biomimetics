"""
ARCA Genesis Chain MCP Tools
Provides authenticated Genesis Chain job management with quota protection
"""

import json
import logging
import os
import pika
import redis
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class GenesisChainManager:
    """Manages Genesis Chain job submission, monitoring, and quota protection"""
    
    def __init__(self):
        # Use environment variable for Docker/local compatibility
        self.shared_storage = Path(os.getenv('SHARED_STORAGE_PATH', '/app/shared_storage'))
        self.jobs_dir = self.shared_storage / "jobs"
        self.responses_dir = self.shared_storage / "responses"
        
        # Ensure directories exist
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        
        # RabbitMQ connection parameters
        self.rabbitmq_params = {
            'host': os.getenv('RABBITMQ_HOST', 'rabbitmq'),
            'port': int(os.getenv('RABBITMQ_PORT', 5672)),
            'user': os.getenv('RABBITMQ_USER', 'arca'),
            'password': os.getenv('RABBITMQ_PASSWORD', 'arca_password'),
            'vhost': os.getenv('RABBITMQ_VHOST', 'arca_vhost')
        }
        
        # Redis connection
        self.redis_host = os.getenv('REDIS_HOST', 'redis')
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))

    def submit_genesis_job(self, genesis_prompt: str, user_authorized: bool = False, 
                          session_id: str = None, priority: str = "normal") -> Dict[str, Any]:
        """
        Submit Genesis Chain job with mandatory authorization
        
        Args:
            genesis_prompt: The architectural prompt for Genesis processing
            user_authorized: REQUIRED - Must be True with explicit user consent
            session_id: Optional tracking ID
            priority: Job priority (normal|high|urgent)
        """
        # CRITICAL: Enforce authorization
        if not user_authorized:
            return {
                "status": "rejected",
                "error": "AUTHORIZATION_REQUIRED",
                "message": "Genesis Chain requires explicit user authorization due to quota limits",
                "help": "Set user_authorized=True only after explicit user consent"
            }
        
        if not genesis_prompt or len(genesis_prompt) < 50:
            return {
                "status": "rejected",
                "error": "INVALID_PROMPT",
                "message": "Genesis prompt too short - minimum 50 characters for meaningful architecture work"
            }
        
        # Generate job ID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        job_id = f"genesis_{timestamp}_{session_id or str(uuid.uuid4())[:8]}"
        
        try:
            # RabbitMQ connection
            credentials = pika.PlainCredentials(
                self.rabbitmq_params['user'], 
                self.rabbitmq_params['password']
            )
            parameters = pika.ConnectionParameters(
                self.rabbitmq_params['host'],
                self.rabbitmq_params['port'], 
                self.rabbitmq_params['vhost'],
                credentials
            )
            
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            # Prepare message
            message = {
                "job_id": job_id,
                "routing_key": "tier3.architect.genesis",
                "genesis_prompt": genesis_prompt,
                "session_id": session_id or str(uuid.uuid4()),
                "submitted_at": datetime.now().isoformat(),
                "user_authorized": True,
                "quota_acknowledged": True,
                "priority": priority,
                "estimated_cost": "high",
                "expected_models": ["gemini-2.5-pro", "gemini-2.5-flash"]
            }
            
            # Publish to arca.tier3 exchange
            channel.basic_publish(
                exchange='arca.tier3',
                routing_key='tier3.architect.genesis',
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2)  # Persistent
            )
            
            connection.close()
            
            # Log submission for quota tracking
            self._log_genesis_submission(job_id, genesis_prompt, session_id)
            
            return {
                "job_id": job_id,
                "status": "submitted",
                "message": f"Genesis job {job_id} submitted to tier3.architect queue",
                "expected_completion": "5-10 minutes",
                "quota_impact": "high",
                "models_used": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash-lite"],
                "output_location": str(self.jobs_dir),
                "monitoring_command": f"python monitor_genesis.py --tail jobs",
                "submission_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Genesis job submission failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to submit Genesis job",
                "help": "Check RabbitMQ connectivity and queue health"
            }

    def monitor_genesis_jobs(self, job_id: str = None, max_age_hours: int = 24) -> Dict[str, Any]:
        """
        Monitor Genesis jobs and their outputs
        
        Args:
            job_id: Specific job to monitor (None for all recent)
            max_age_hours: How far back to look for jobs
        """
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        
        # Monitor jobs directory
        job_files = []
        if self.jobs_dir.exists():
            for file_path in self.jobs_dir.glob("*.json"):
                if job_id and job_id not in file_path.name:
                    continue
                
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime > cutoff:
                    job_files.append({
                        "file": file_path.name,
                        "size": file_path.stat().st_size,
                        "modified": mtime.isoformat(),
                        "path": str(file_path),
                        "age_minutes": int((datetime.now() - mtime).total_seconds() / 60)
                    })
        
        # Monitor responses directory  
        response_files = []
        if self.responses_dir.exists():
            for file_path in self.responses_dir.glob("*.json"):
                if job_id and job_id not in file_path.name:
                    continue
                    
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime > cutoff:
                    response_files.append({
                        "file": file_path.name,
                        "size": file_path.stat().st_size,
                        "modified": mtime.isoformat(),
                        "path": str(file_path),
                        "age_minutes": int((datetime.now() - mtime).total_seconds() / 60)
                    })
        
        # Check Redis genesis keys
        redis_status = self._check_redis_genesis_keys()
        
        # Check RabbitMQ queue status
        queue_status = self._check_rabbitmq_queues()
        
        return {
            "job_id_filter": job_id,
            "recent_jobs": sorted(job_files, key=lambda x: x['modified'], reverse=True),
            "recent_responses": sorted(response_files, key=lambda x: x['modified'], reverse=True),
            "redis_status": redis_status,
            "queue_status": queue_status,
            "summary": {
                "total_jobs_found": len(job_files),
                "total_responses_found": len(response_files),
                "most_recent_activity": max([f['modified'] for f in job_files + response_files]) if job_files or response_files else None
            },
            "monitoring_tip": "Use 'python monitor_genesis.py --watch' for real-time monitoring"
        }

    def get_genesis_output(self, job_id: str, output_type: str = "all") -> Dict[str, Any]:
        """
        Retrieve Genesis job outputs
        
        Args:
            job_id: Job identifier to retrieve
            output_type: 'jobs'|'responses'|'complete'|'all'
        """
        outputs = {
            "job_id": job_id,
            "outputs_found": [],
            "architecture_plan": None,
            "execution_results": None,
            "completion_status": "unknown"
        }
        
        # Find job files
        if output_type in ["jobs", "all"]:
            job_files = list(self.jobs_dir.glob(f"*{job_id}*.json"))
            for job_file in job_files:
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                    
                    outputs["outputs_found"].append({
                        "type": "job",
                        "file": job_file.name,
                        "path": str(job_file),
                        "size": job_file.stat().st_size,
                        "modified": datetime.fromtimestamp(job_file.stat().st_mtime).isoformat()
                    })
                    
                    # Extract key data
                    if "architecture_plan" in job_data:
                        outputs["architecture_plan"] = job_data["architecture_plan"]
                    if "genesis_execution_results" in job_data:
                        outputs["execution_results"] = job_data["genesis_execution_results"]
                    if "completion_status" in job_data:
                        outputs["completion_status"] = job_data["completion_status"]
                        
                except Exception as e:
                    logger.error(f"Error reading job file {job_file}: {e}")
        
        # Find response files
        if output_type in ["responses", "all"]:
            response_files = list(self.responses_dir.glob(f"*{job_id}*.json"))
            for response_file in response_files:
                try:
                    with open(response_file, 'r') as f:
                        response_data = json.load(f)
                    
                    outputs["outputs_found"].append({
                        "type": "response",
                        "file": response_file.name,
                        "path": str(response_file),
                        "size": response_file.stat().st_size,
                        "modified": datetime.fromtimestamp(response_file.stat().st_mtime).isoformat(),
                        "routing_key": response_data.get("response_metadata", {}).get("routing_key")
                    })
                    
                except Exception as e:
                    logger.error(f"Error reading response file {response_file}: {e}")
        
        # Get completion files specifically
        if output_type in ["complete", "all"]:
            complete_files = list(self.jobs_dir.glob(f"genesis_complete_*{job_id}*.json"))
            for complete_file in complete_files:
                try:
                    with open(complete_file, 'r') as f:
                        complete_data = json.load(f)
                    
                    outputs["outputs_found"].append({
                        "type": "completion",
                        "file": complete_file.name,
                        "path": str(complete_file),
                        "size": complete_file.stat().st_size,
                        "modified": datetime.fromtimestamp(complete_file.stat().st_mtime).isoformat()
                    })
                    
                    # This is the authoritative completion status
                    outputs["completion_status"] = complete_data.get("completion_status", "success")
                    if not outputs["architecture_plan"]:
                        outputs["architecture_plan"] = complete_data.get("architecture_plan")
                    if not outputs["execution_results"]:
                        outputs["execution_results"] = complete_data.get("genesis_execution_results")
                        
                except Exception as e:
                    logger.error(f"Error reading completion file {complete_file}: {e}")
        
        outputs["total_outputs_found"] = len(outputs["outputs_found"])
        outputs["search_completed"] = datetime.now().isoformat()
        
        return outputs

    def check_genesis_quota(self) -> Dict[str, Any]:
        """Check Genesis Chain quota usage and limits"""
        try:
            # Count Genesis submissions in the last 24 hours
            daily_jobs = self._count_recent_genesis_jobs(24)
            
            # Estimate token usage (rough calculation)
            estimated_tokens = daily_jobs * 500000  # ~500k tokens per Genesis job
            
            # Check Redis for quota tracking
            quota_data = self._get_quota_from_redis()
            
            warnings = []
            if daily_jobs >= 10:
                warnings.append("High daily Genesis usage - consider rate limiting")
            if estimated_tokens > 5000000:
                warnings.append("High token consumption - approaching quota limits")
            
            recommended_action = "proceed"
            if daily_jobs >= 15:
                recommended_action = "wait"
            elif daily_jobs >= 20:
                recommended_action = "upgrade"
            
            return {
                "daily_genesis_jobs": daily_jobs,
                "estimated_tokens_used": estimated_tokens,
                "quota_warnings": warnings,
                "recommended_action": recommended_action,
                "quota_data": quota_data,
                "limits": {
                    "recommended_daily_max": 10,
                    "tokens_per_job_estimate": 500000,
                    "models_affected": ["gemini-2.5-pro", "gemini-2.5-flash"]
                },
                "last_checked": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Quota check failed: {e}")
            return {
                "error": str(e),
                "message": "Unable to check Genesis quota",
                "recommended_action": "proceed_with_caution"
            }

    def diagnose_genesis_failure(self, job_id: str) -> Dict[str, Any]:
        """Diagnose Genesis job failures and provide recovery steps"""
        try:
            diagnosis = {
                "job_id": job_id,
                "diagnosis_timestamp": datetime.now().isoformat(),
                "issues_found": [],
                "recovery_steps": [],
                "system_health": {}
            }
            
            # Check if job exists in any form
            job_found = any(self.jobs_dir.glob(f"*{job_id}*"))
            response_found = any(self.responses_dir.glob(f"*{job_id}*"))
            
            if not job_found and not response_found:
                diagnosis["issues_found"].append("No job or response files found for this job_id")
                diagnosis["recovery_steps"].append("Check if job_id is correct")
                diagnosis["recovery_steps"].append("Verify job was actually submitted")
            
            # Check RabbitMQ queue health
            queue_health = self._check_rabbitmq_queues()
            diagnosis["system_health"]["rabbitmq"] = queue_health
            
            if any(q.get("consumers", 0) == 0 for q in queue_health.values() if isinstance(q, dict)):
                diagnosis["issues_found"].append("RabbitMQ queues have no consumers")
                diagnosis["recovery_steps"].append("Restart agent_service to restore consumers")
            
            # Check Redis connectivity
            redis_health = self._check_redis_genesis_keys()
            diagnosis["system_health"]["redis"] = redis_health
            
            if "error" in redis_health:
                diagnosis["issues_found"].append("Redis connectivity issues")
                diagnosis["recovery_steps"].append("Check Redis service health")
            
            # Check shared storage mount
            storage_accessible = self.shared_storage.exists()
            diagnosis["system_health"]["shared_storage"] = {
                "accessible": storage_accessible,
                "path": str(self.shared_storage)
            }
            
            if not storage_accessible:
                diagnosis["issues_found"].append("Shared storage not accessible")
                diagnosis["recovery_steps"].append("Verify shared_storage volume mount in docker-compose")
                diagnosis["recovery_steps"].append("Restart agent_service with proper volume mounts")
            
            # Overall assessment
            if not diagnosis["issues_found"]:
                diagnosis["status"] = "healthy"
                diagnosis["message"] = "No obvious issues found - job may still be processing"
            else:
                diagnosis["status"] = "issues_detected"
                diagnosis["message"] = f"Found {len(diagnosis['issues_found'])} potential issues"
            
            return diagnosis
            
        except Exception as e:
            logger.error(f"Genesis diagnosis failed: {e}")
            return {
                "job_id": job_id,
                "error": str(e),
                "message": "Diagnosis failed",
                "status": "diagnosis_error"
            }

    def restart_genesis_chain(self) -> Dict[str, Any]:
        """Restart Genesis Chain components safely"""
        try:
            restart_log = {
                "restart_timestamp": datetime.now().isoformat(),
                "steps_completed": [],
                "errors": [],
                "final_status": "unknown"
            }
            
            # Step 1: Restart agent_service (primary Genesis processor)
            try:
                result = subprocess.run([
                    "docker-compose", "-f", "/Users/danexall/Documents/VS Code Projects/ARCA/docker-compose.local.yml",
                    "restart", "agent_service"
                ], capture_output=True, text=True, cwd="/Users/danexall/Documents/VS Code Projects/ARCA")
                
                if result.returncode == 0:
                    restart_log["steps_completed"].append("agent_service restarted successfully")
                else:
                    restart_log["errors"].append(f"agent_service restart failed: {result.stderr}")
            except Exception as e:
                restart_log["errors"].append(f"agent_service restart error: {e}")
            
            # Step 2: Verify RabbitMQ consumers are active
            try:
                import time
                time.sleep(5)  # Wait for consumers to register
                
                queue_status = self._check_rabbitmq_queues()
                active_consumers = sum(q.get("consumers", 0) for q in queue_status.values() if isinstance(q, dict))
                
                if active_consumers > 0:
                    restart_log["steps_completed"].append(f"RabbitMQ consumers restored: {active_consumers} active")
                else:
                    restart_log["errors"].append("RabbitMQ consumers not restored after restart")
            except Exception as e:
                restart_log["errors"].append(f"Consumer verification error: {e}")
            
            # Step 3: Test shared storage access
            try:
                test_file = self.shared_storage / "restart_test.txt"
                test_file.write_text(f"Genesis restart test: {datetime.now().isoformat()}")
                test_file.unlink()  # Clean up
                restart_log["steps_completed"].append("Shared storage access verified")
            except Exception as e:
                restart_log["errors"].append(f"Shared storage test failed: {e}")
            
            # Final status
            if not restart_log["errors"]:
                restart_log["final_status"] = "success"
                restart_log["message"] = "Genesis Chain restart completed successfully"
            else:
                restart_log["final_status"] = "partial"
                restart_log["message"] = f"Genesis Chain restart completed with {len(restart_log['errors'])} issues"
            
            return restart_log
            
        except Exception as e:
            logger.error(f"Genesis restart failed: {e}")
            return {
                "error": str(e),
                "message": "Genesis Chain restart failed",
                "final_status": "error"
            }

    # Helper methods
    
    def _log_genesis_submission(self, job_id: str, prompt: str, session_id: str):
        """Log Genesis submission for quota tracking"""
        try:
            log_entry = {
                "job_id": job_id,
                "submitted_at": datetime.now().isoformat(),
                "session_id": session_id,
                "prompt_length": len(prompt),
                "estimated_cost": "high"
            }
            
            log_file = self.shared_storage / "genesis_submissions.jsonl"
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to log Genesis submission: {e}")

    def _count_recent_genesis_jobs(self, hours: int) -> int:
        """Count Genesis jobs in the last N hours"""
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            count = 0
            
            log_file = self.shared_storage / "genesis_submissions.jsonl"
            if log_file.exists():
                with open(log_file, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            submitted_at = datetime.fromisoformat(entry["submitted_at"])
                            if submitted_at > cutoff:
                                count += 1
                        except:
                            continue
            
            return count
        except Exception as e:
            logger.warning(f"Failed to count recent jobs: {e}")
            return 0

    def _check_redis_genesis_keys(self) -> Dict[str, Any]:
        """Check Redis for Genesis-related keys"""
        try:
            r = redis.Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
            genesis_keys = r.keys('genesis:*')
            
            redis_data = {}
            for key in genesis_keys[:20]:  # Limit to prevent overflow
                try:
                    value = r.get(key)
                    redis_data[key] = value
                except:
                    redis_data[key] = "Error reading key"
            
            return {
                "connected": True,
                "total_genesis_keys": len(genesis_keys),
                "sample_keys": redis_data,
                "redis_health": "healthy"
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "redis_health": "error"
            }

    def _check_rabbitmq_queues(self) -> Dict[str, Any]:
        """Check RabbitMQ queue status"""
        try:
            result = subprocess.run([
                "docker", "exec", "rabbitmq", 
                "rabbitmqctl", "list_queues", "name", "messages", "consumers"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                queues = {}
                for line in result.stdout.strip().split('\n')[1:]:  # Skip header
                    parts = line.split('\t')
                    if len(parts) >= 3 and ('tier' in parts[0] or 'response' in parts[0]):
                        queues[parts[0]] = {
                            "messages": int(parts[1]),
                            "consumers": int(parts[2]),
                            "status": "active" if int(parts[2]) > 0 else "no_consumers"
                        }
                return queues
            else:
                return {"error": f"rabbitmqctl failed: {result.stderr}"}
        except Exception as e:
            return {"error": str(e)}

    def _get_quota_from_redis(self) -> Dict[str, Any]:
        """Get quota information from Redis if available"""
        try:
            r = redis.Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
            quota_keys = r.keys('quota:*')
            
            quota_data = {}
            for key in quota_keys:
                try:
                    value = r.get(key)
                    quota_data[key] = value
                except:
                    continue
            
            return quota_data
        except:
            return {}

# Instantiate the manager
genesis_manager = GenesisChainManager()

# MCP Tool Functions (required by MCP server)

def genesis_submit(genesis_prompt: str, user_authorized: bool = False, 
                  session_id: str = None, priority: str = "normal") -> Dict[str, Any]:
    """Submit Genesis Chain job with mandatory user authorization"""
    return genesis_manager.submit_genesis_job(genesis_prompt, user_authorized, session_id, priority)

def genesis_monitor(job_id: str = None, max_age_hours: int = 24) -> Dict[str, Any]:
    """Monitor Genesis job progress and outputs"""
    return genesis_manager.monitor_genesis_jobs(job_id, max_age_hours)

def genesis_output(job_id: str, output_type: str = "all") -> Dict[str, Any]:
    """Retrieve Genesis job outputs"""
    return genesis_manager.get_genesis_output(job_id, output_type)

def genesis_quota() -> Dict[str, Any]:
    """Check Genesis Chain quota usage and limits"""
    return genesis_manager.check_genesis_quota()

def genesis_diagnose(job_id: str) -> Dict[str, Any]:
    """Diagnose Genesis job failures"""
    return genesis_manager.diagnose_genesis_failure(job_id)

def genesis_restart() -> Dict[str, Any]:
    """Restart Genesis Chain components"""
    return genesis_manager.restart_genesis_chain()