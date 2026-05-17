from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn
import httpx
import os

app = FastAPI(title="ARCA Command Deck [LAB]")

# Target the authoritative UI file
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
INDEX_PATH = os.path.join(STATIC_DIR, "index.html")

# Neural System Backend
# Use Docker DNS in OCI/Mesh, localhost otherwise
if os.environ.get("ARCA_ENV") == "oci":
    PYTHIA_CORE = "http://neural_system:8086"
else:
    PYTHIA_CORE = os.environ.get("PYTHIA_CORE_URL", "http://localhost:8086")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    if not os.path.exists(INDEX_PATH):
        return f"<html><body><h1>Error: Command Deck Source Not Found</h1><p>Expected: {INDEX_PATH}</p></body></html>"
    with open(INDEX_PATH, "r") as f:
        return f.read()

@app.get("/api/vitals")
async def proxy_vitals():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{PYTHIA_CORE}/system/vitals")
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "disconnected"}

@app.get("/api/manifold")
async def proxy_manifold():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{PYTHIA_CORE}/system/manifold_3d")
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "disconnected"}

@app.get("/api/status")
async def proxy_status():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{PYTHIA_CORE}/status")
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "disconnected"}

@app.post("/api/tick")
async def proxy_tick():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{PYTHIA_CORE}/tick")
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "disconnected"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8091)
