import psutil
import logging
import asyncio

logger = logging.getLogger("phantom_monitor")

class ResourceMonitor:
    """Monitors system load to identify idle cycles for background development."""
    
    def __init__(self, cpu_threshold: float = 40.0, ram_threshold: float = 70.0):
        self.cpu_threshold = cpu_threshold
        self.ram_threshold = ram_threshold
        self.is_idle = True

    async def check_status(self):
        """Returns True if the system is considered idle."""
        cpu_usage = psutil.cpu_percent(interval=None)
        ram_usage = psutil.virtual_memory().percent
        
        # Check if CPU or RAM exceeds threshold
        if cpu_usage > self.cpu_threshold or ram_usage > self.ram_threshold:
            if self.is_idle:
                logger.info(f"System Busy: CPU {cpu_usage}%, RAM {ram_usage}%. Suspending sandbox.")
            self.is_idle = False
        else:
            if not self.is_idle:
                logger.info(f"System Idle: CPU {cpu_usage}%, RAM {ram_usage}%. Resuming sandbox.")
            self.is_idle = True
            
        return self.is_idle

    async def loop(self):
        """Continuous monitoring loop."""
        while True:
            await self.check_status()
            await asyncio.sleep(5)
