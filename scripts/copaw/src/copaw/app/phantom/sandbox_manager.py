import os
import signal
import subprocess
import logging
import asyncio
from pathlib import Path

logger = logging.getLogger("phantom_sandbox")

class SandboxManager:
    """Manages isolated development environments for agents with suspend/resume logic."""
    
    def __init__(self, sandbox_root: str = "/tmp/copaw_sandbox"):
        self.sandbox_root = Path(sandbox_root)
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self.active_processes = {}
        self.is_paused = False

    async def create_task_env(self, task_id: str, repo_path: str):
        """Prepares a mocked environment for a specific task."""
        task_path = self.sandbox_root / task_id
        task_path.mkdir(exist_ok=True)
        
        # Link live project for agent access (read-only for core, write for scratch)
        # Mocking services via ENV vars pointing to local proxies could happen here.
        logger.info(f"Sandbox created for task {task_id} at {task_path}")
        return task_path

    def suspend_all(self):
        """Sends SIGSTOP to all sandbox processes for instant pause."""
        if self.is_paused: return
        
        for tid, proc in self.active_processes.items():
            try:
                os.kill(proc.pid, signal.SIGSTOP)
                logger.info(f"Suspended task {tid} (PID {proc.pid})")
            except Exception as e:
                logger.error(f"Failed to suspend {tid}: {e}")
        self.is_paused = True

    def resume_all(self):
        """Sends SIGCONT to resume all sandbox processes."""
        if not self.is_paused: return
        
        for tid, proc in self.active_processes.items():
            try:
                os.kill(proc.pid, signal.SIGCONT)
                logger.info(f"Resumed task {tid} (PID {proc.pid})")
            except Exception as e:
                logger.error(f"Failed to resume {tid}: {e}")
        self.is_paused = False

    async def run_in_sandbox(self, task_id: str, command: list, env: dict = None):
        """Runs a command within the task's sandbox."""
        env = env or os.environ.copy()
        # Point agents to mock services
        env["ARCA_CREDENTIALS_URL"] = "http://localhost:8089/mock"
        env["ARCA_MEMORY_URL"] = "http://localhost:8001/mock"
        
        proc = subprocess.Popen(
            command,
            cwd=str(self.sandbox_root / task_id),
            env=env,
            preexec_fn=os.setsid # Create process group for clean signal handling
        )
        self.active_processes[task_id] = proc
        logger.info(f"Started task {task_id} in sandbox (PID {proc.pid})")
        return proc
