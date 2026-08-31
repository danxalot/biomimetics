import os
import time
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TelemetryCleaner")

RETENTION_HOURS = 72
RETENTION_SECONDS = RETENTION_HOURS * 3600
TARGET_DIR = Path("/app/shared_storage/tmp_dev_records/telemetry")

def cleanup_telemetry():
    """Removes files older than RETENTION_HOURS from the target directory."""
    if not TARGET_DIR.exists():
        logger.warning(f"Target directory {TARGET_DIR} does not exist. Skipping cleanup.")
        return

    logger.info(f"Starting cleanup for files older than {RETENTION_HOURS} hours in {TARGET_DIR}")
    
    deleted_count = 0
    now = time.time()

    for root, dirs, files in os.walk(TARGET_DIR):
        for name in files:
            file_path = Path(root) / name
            try:
                # Check metrics (modification time)
                mtime = file_path.stat().st_mtime
                if now - mtime > RETENTION_SECONDS:
                    file_path.unlink()
                    deleted_count += 1
                    logger.debug(f"Deleted old record: {file_path}")
            except Exception as e:
                logger.error(f"Error checking/deleting {file_path}: {e}")

    if deleted_count > 0:
        logger.info(f"Cleanup complete. Deleted {deleted_count} files.")
    else:
        logger.info("Cleanup complete. No files needed deletion.")

if __name__ == "__main__":
    cleanup_telemetry()
