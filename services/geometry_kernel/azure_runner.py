
import os
import sys
import logging
import time
import requests
import threading
import signal

# Ensure correct path for imports
sys.path.append("/app") 
sys.path.append("/app/services/geometry_kernel")

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AzureRunner")

# Global Shutdown Flag
shutdown_flag = threading.Event()

def poll_metadata_service():
    """Poll Azure Metadata Service for Scheduled Events (Eviction)"""
    url = "http://169.254.169.254/metadata/scheduledevents?api-version=2020-07-01"
    headers = {"Metadata": "true"}
    
    logger.info("📡 Starting Eviction Monitor...")
    while not shutdown_flag.is_set():
        try:
            resp = requests.get(url, headers=headers, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                for event in data.get("Events", []):
                    if event["EventType"] in ["Preempt", "Terminate"] and event["ResourceType"] == "VirtualMachine":
                        logger.warning(f"🚨 SPOT EVICTION DETECTED: {event}")
                        logger.warning("🚨 30-SECOND COUNTDOWN STARTED. INITIATING SHUTDOWN.")
                        shutdown_flag.set()
                        # Acknowledge? (Optional, but good practice to ack immediately to buy time?)
                        # Actually standard practice is just react.
                        return
        except Exception as e:
            # Connection error expected if not on Azure VM (e.g. local dev)
            pass
        time.sleep(5)

def signal_handler(signum, frame):
    logger.info(f"🛑 Signal {signum} received. Shutting down...")
    shutdown_flag.set()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

try:
    from modal_apps.geometry_heavy_lifter import HeavyGeometryIngester
except ImportError as e:
    logger.error(f"Failed to import HeavyGeometryIngester: {e}")
    sys.exit(1)

def main():
    logger.info("🚀 Azure Runner Starting...")
    
    # Start Eviction Monitor in Daemon Thread
    if os.getenv("AZURE_SPOT", "true") == "true": # Default true for this script
        monitor_thread = threading.Thread(target=poll_metadata_service, daemon=True)
        monitor_thread.start()
    
    # Mock Volume Paths (Docker Volumes should be mounted here)
    # On Azure Spot, /app/shared_storage should be a mount to Azure Files
    os.makedirs("/app/shared_storage", exist_ok=True)
    os.makedirs("/models", exist_ok=True)
    
    # Instantiate
    try:
        ingester = HeavyGeometryIngester()
        logger.info("✅ Ingester Instantiated")
    except Exception as e:
        logger.error(f"❌ Failed to instantiate: {e}")
        sys.exit(1)
        
    # Run Setup
    if hasattr(ingester, "setup"):
        logger.info("🔧 Running Setup...")
        ingester.setup()
    
    logger.info("✅ Ready for Processing.")
    
    # Execution Loop
    # In V2, we listen to MCP or Queue. For now, simple file polling loop.
    job_target = "/app/shared_storage/inbox/pending_job.json"
    
    while not shutdown_flag.is_set():
        if os.path.exists(job_target):
            logger.info("📂 Found Pending Job...")
            # (Process logic here)
            # Simulate work
            time.sleep(5)
            # Remove job
            # os.remove(job_target)
        else:
            time.sleep(5)
            
    logger.info("🛑 Graceful Shutdown Complete.")

if __name__ == "__main__":
    main()
