import os
import uvicorn
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

# Log Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("amygdala")

app = FastAPI(title="Reflexive Amygdala", version="1.0.0")

class ReflexRequest(BaseModel):
    input_vector: list
    context: str

@app.post("/reflex")
async def trigger_reflex(req: ReflexRequest):
    """
    Fast-path decision making.
    Mock implementation: Returns 'FREEZE', 'FIGHT', or 'FLIGHT' based on simple vector properties.
    """
    # Simple Mock Logic
    # In V2, this uses the HDC Memory storage for O(1) matching
    logger.info(f"Processing reflex for context: {req.context}")
    return {"action": "OBSERVE", "confidence": 0.9}

@app.get("/health")
def health():
    return {"status": "healthy"}

def start():
    port = int(os.environ.get("PORT", 8092))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    start()
