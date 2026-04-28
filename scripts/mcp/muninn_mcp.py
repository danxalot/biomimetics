import sqlite3
import os
import json
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from mcp.server.fastmcp import FastMCP

# Path to the Muninn database
DB_PATH = "/Users/danexall/biomimetics/knowledge/muninn.db"

# Ensure the parent directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Initialize FastMCP server
mcp = FastMCP("MuninnDB")

# Initialize FastAPI for HTTP Sidecar
app = FastAPI(title="MuninnDB HTTP Bridge")

class MemoryItem(BaseModel):
    key: str
    value: str

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            key TEXT PRIMARY KEY,
            value TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

@mcp.tool()
def store_memory(key: str, value: str) -> str:
    """Store a persistent memory."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT OR REPLACE INTO memory (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        return f"✅ Stored memory for key: {key}"
    except Exception as e:
        return f"❌ Error storing memory: {str(e)}"
    finally:
        conn.close()

@mcp.tool()
def recall_memory(key: str) -> str:
    """Retrieve a persistent memory."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else "❌ Memory not found."

@mcp.tool()
def search_memories(query: str, limit: int = 5) -> str:
    """Search memories by keyword and return the most relevant ones."""
    conn = sqlite3.connect(DB_PATH)
    try:
        query_pattern = f"%{query}%"
        rows = conn.execute(
            "SELECT key, value, timestamp FROM memory WHERE key LIKE ? OR value LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (query_pattern, query_pattern, limit)
        ).fetchall()
        if not rows:
            return f"📭 No engrams found matching: {query}"
        
        results = ["🧠 High-Activation Engrams:"]
        for row in rows:
            results.append(f"[{row[2]}] {row[0]}: {row[1]}")
        return "\n".join(results)
    finally:
        conn.close()

@mcp.tool()
def list_memories() -> str:
    """List all stored memory keys."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT key FROM memory ORDER BY timestamp DESC").fetchall()
    conn.close()
    if not rows:
        return "📭 No memories stored."
    return "🧠 Stored Memories:\n" + "\n".join(f"- {row[0]}" for row in rows)

# --- FastAPI Endpoints for Relay Client ---

@app.get("/memory/search/{query}")
async def api_search_memory(query: str, limit: int = 5):
    res = search_memories(query, limit)
    return {"query": query, "results": res}

@app.post("/memory/store")
async def api_store_memory(item: MemoryItem):
    res = store_memory(item.key, item.value)
    if "❌" in res:
        raise HTTPException(status_code=500, detail=res)
    return {"status": "success", "message": res}

@app.get("/memory/recall/{key}")
async def api_recall_memory(key: str):
    res = recall_memory(key)
    if "❌" in res:
        raise HTTPException(status_code=404, detail=res)
    return {"key": key, "value": res}

async def run_servers():
    # Run uvicorn in a separate thread/task so MCP doesn't block it
    config = uvicorn.Config(app, host="127.0.0.1", port=8095, log_level="info")
    server = uvicorn.Server(config)
    
    # Run both servers
    await asyncio.gather(
        server.serve(),
        asyncio.to_thread(mcp.run)
    )

if __name__ == "__main__":
    init_db()
    asyncio.run(run_servers())
