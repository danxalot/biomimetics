import logging
import asyncio
from .resource_monitor import ResourceMonitor
from .sandbox_manager import SandboxManager

logger = logging.getLogger("phantom_controller")

class PhantomController:
    """Orchestrates Resource Monitoring and Sandbox Execution for CoPaw Agents."""
    
    def __init__(self):
        self.monitor = ResourceMonitor()
        self.sandbox = SandboxManager()
        self._voice_active = False
        self._running = False

    async def start(self):
        self._running = True
        logger.info("👻 Phantom Sandbox Controller Online.")
        asyncio.create_task(self._main_loop())

    async def stop(self):
        self._running = False
        self.sandbox.suspend_all()
        logger.info("👻 Phantom Sandbox Controller Offline.")

    def set_voice_active(self, active: bool):
        """Called by the Voice Relay when user input is detected."""
        if active and not self._voice_active:
            logger.info("🎤 Voice Input Detected: Instant Freeze triggered.")
            self.sandbox.suspend_all()
        elif not active and self._voice_active:
            logger.info("🎤 Voice Input Ended: Checking system load for resume.")
            # Resume logic will be handled by the main loop check
        self._voice_active = active

    async def _main_loop(self):
        while self._running:
            is_idle = await self.monitor.check_status()
            
            if self._voice_active:
                self.sandbox.suspend_all()
            elif not is_idle:
                self.sandbox.suspend_all()
            else:
                self.sandbox.resume_all()
                
            await asyncio.sleep(2)

_phantom_instance = None

def get_phantom_controller():
    global _phantom_instance
    if _phantom_instance is None:
        _phantom_instance = PhantomController()
    return _phantom_instance
