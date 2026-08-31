import os
import uvicorn
import logging
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dreamer")

app = FastAPI(title="Dreaming Consolidator", version="1.0.0")

class DreamJob(BaseModel):
    memory_ids: List[str]
    mode: str = "consolidation"

def process_dream(job: DreamJob):
    logger.info(f"Starting dream cycle: {job.mode} on {len(job.memory_ids)} memories")
    # Simulation of heavy processing
    import time
    time.sleep(2)
    logger.info("Dream cycle complete. New connections formed.")

@app.post("/dream")
async def trigger_dream(job: DreamJob, background_tasks: BackgroundTasks):
    """
    Triggers an offline consolidation process.
    """
    background_tasks.add_task(process_dream, job)
    return {"status": "dream_scheduled", "job": job.mode}

@app.get("/health")
def health():
    return {"status": "healthy"}

def start():
    port = int(os.environ.get("PORT", 8093))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    start()
