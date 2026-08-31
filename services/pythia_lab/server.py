from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import httpx
import os
from pathlib import Path

app = FastAPI(title="ARCA Command Deck [LAB]")

# ── Paths ────────────────────────────────────────────────────────────────────
STATIC_DIR = Path(os.path.dirname(__file__)) / "static"
ASSETS_DIR = STATIC_DIR / "assets"

# ── Backend target ───────────────────────────────────────────────────────────
if os.environ.get("ARCA_ENV") == "oci":
    PYTHIA_CORE = "http://neural_system:8086"
else:
    PYTHIA_CORE = os.environ.get("PYTHIA_CORE_URL", "http://localhost:8086")

# ── Mount hashed JS/CSS assets (/assets/index-*.js etc.) ────────────────────
# Must be mounted BEFORE any catch-all route so FastAPI's router sees it first.
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# ─────────────────────────────────────────────────────────────────────────────
# API proxy routes — all registered before the wildcard SPA fallback
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/vitals")
async def proxy_vitals():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{PYTHIA_CORE}/system/vitals")
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "disconnected"}

@app.get("/api/manifold")
async def proxy_manifold():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{PYTHIA_CORE}/system/manifold_3d")
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "disconnected"}

@app.get("/api/manifold_3d")
async def proxy_manifold_3d():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{PYTHIA_CORE}/system/manifold_3d")
            return r.json()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/status")
async def proxy_status():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{PYTHIA_CORE}/status")
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "disconnected"}

@app.post("/api/tick")
async def proxy_tick():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.post(f"{PYTHIA_CORE}/tick")
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "disconnected"}

@app.get("/api/config")
async def proxy_config_get():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{PYTHIA_CORE}/system/config")
            return r.json()
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/config")
async def proxy_config_post(request: Request):
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{PYTHIA_CORE}/system/config", json=body)
            return r.json()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/engine")
async def proxy_engine():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{PYTHIA_CORE}/engine/state")
            return r.json()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/poincare")
async def proxy_poincare():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{PYTHIA_CORE}/geometry/poincare")
            return r.json()
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# Static file routes — favicon and icons from Vite build root
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    p = STATIC_DIR / "favicon.svg"
    if p.exists():
        return FileResponse(str(p), media_type="image/svg+xml")
    raise HTTPException(status_code=404)

@app.get("/icons.svg", include_in_schema=False)
async def icons_svg():
    p = STATIC_DIR / "icons.svg"
    if p.exists():
        return FileResponse(str(p), media_type="image/svg+xml")
    raise HTTPException(status_code=404)

# ─────────────────────────────────────────────────────────────────────────────
# SPA entry point + catch-all (MUST be last)
# All non-api, non-asset GETs return index.html for client-side routing
# ─────────────────────────────────────────────────────────────────────────────

def _serve_index() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index), media_type="text/html")
    raise HTTPException(status_code=503, detail="Command Deck not built — run npm build and deploy to static/")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return _serve_index()

@app.get("/{full_path:path}", include_in_schema=False, response_class=HTMLResponse)
async def spa_fallback(full_path: str):
    return _serve_index()

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8091)
