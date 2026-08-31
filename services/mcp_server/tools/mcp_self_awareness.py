
import os
import logging
import asyncio
import aiohttp
import json
from pathlib import Path
from typing import Dict, Any, List

from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_self_awareness")

# Configuration
MEMORY_SYSTEM_URL = os.getenv("MEMORY_SYSTEM_URL", "http://memory_system:8002")
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8000")
ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", "/app/bg_artifacts") # Mounted in docker-compose

# Initialize FastMCP
mcp = FastMCP("self_awareness")

class SelfAwarenessEngine:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _summarize_plan(self, content: str) -> str:
        """Ask LLM (Gemma-3-27b) to summarize the current system plan for memory injection."""
        session = await self._get_session()
        
        prompt = f"""
        You are the 'Silent Listener' and Self-Modeler for the ARCA system.
        Analyze the following 'Task List' and 'Implementation Plan'.
        EXTRACT the current:
        1. High-level Objective
        2. Active Task (What is happening right now?)
        3. Critical Constraints (e.g. Memory limits, Hardware)
        4. Upcoming Milestones

        Format as a concise JSON object ready for knowledge graph injection.
        
        DOCUMENT CONTENT:
        {content[:30000]} 
        """
        
        payload = {
            "model": "gemma-3-27b-it", # Targeted model for reflection
            "messages": [
                {"role": "system", "content": "You are the system's Meta-Cognitive observer."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        
        try:
            async with session.post(f"{LLM_GATEWAY_URL}/v1/chat/completions", json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"LLM Gateway Error: {text}")
                    return f"Error analyzing plan: {text}"
                
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Failed to call LLM Gateway: {e}")
            return f"Error calling LLM: {str(e)}"

    async def _push_to_memory(self, content: str, summary: str, source: str):
        """Push the analyzed plan to Semantic Memory."""
        session = await self._get_session()
        
        # 1. Store raw document with summary
        doc_payload = {
            "content": f"SYSTEM_PLAN_UPDATE:\n{summary}\n\nRAW_SOURCE:\n{content[:5000]}...",
            "source": source,
            "document_type": "system_state_snapshot"
        }
        
        try:
            async with session.post(f"{MEMORY_SYSTEM_URL}/document", json=doc_payload) as resp:
                if resp.status != 200:
                    logger.error(f"Memory System Error (Document): {await resp.text()}")
                else:
                    logger.info("Successfully pushed plan to Semantic Memory.")
        except Exception as e:
            logger.error(f"Failed to push to memory: {e}")

    async def ingest_file(self, file_path: str) -> str:
        """Read a file, analyze it, and store in memory."""
        try:
            path = Path(file_path)
            if not path.exists():
                return f"Error: File not found at {file_path}"
                
            content = path.read_text(encoding='utf-8')
            
            # Analyze
            summary = await self._summarize_plan(content)
            
            # Store
            await self._push_to_memory(content, summary, source=path.name)
            
            return f"Successfully ingested {path.name}. Analysis:\n{summary}"
            
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            return f"Ingestion failed: {str(e)}"

# Global instance
engine = SelfAwarenessEngine()

@mcp.tool()
async def reflect_on_plan(artifact_path: str) -> str:
    """
    Reads the specified artifact (e.g., task.md), summarizes the current system state,
    and injects it into Semantic Memory to update the system's self-model.
    
    Args:
        artifact_path: Absolute path to the artifact file (e.g. /app/artifacts/task.md)
    """
    return await engine.ingest_file(artifact_path)

if __name__ == "__main__":
    mcp.run()
