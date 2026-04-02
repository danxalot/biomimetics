#!/Library/Frameworks/Python.framework/Versions/3.13/bin/python3
"""
Azure Credentials Server — Strict Mode
Single Source of Truth: Azure Key Vault ONLY.

Authentication: ClientSecretCredential (headless service principal).
Credentials loaded from: /Users/danexall/biomimetics/scripts/secret_manager/.env

POLICY: No local fallbacks. If Azure Key Vault is unreachable or the requested
secret does not exist, the server returns a clear error. Serving stale or rotated
keys is worse than failing loudly.

Usage:
    python3 /Users/danexall/biomimetics/scripts/secret_manager/credentials_server.py

API Endpoints:
    GET  /secrets/{name}     - Fetch a single secret from Azure Key Vault
    GET  /secrets            - List all secret names
    POST /secrets/batch      - Fetch multiple secrets
    POST /secrets/rotate     - Invalidate in-memory cache
    GET  /health             - Health check (always 200; reports azure_status)
    GET  /metrics            - Usage metrics

Authentication:
    Header: X-API-Key: <CREDENTIALS_API_KEY>

Required Environment Variables (set in .env):
    AZURE_KEY_VAULT_NAME     - e.g. arca-mcp-kv-dae
    AZURE_TENANT_ID          - Azure AD tenant ID
    AZURE_CLIENT_ID          - Service principal application ID
    AZURE_CLIENT_SECRET      - Service principal secret value
    CREDENTIALS_API_KEY      - API key clients must present
    CREDENTIALS_PORT         - Port (default: 8089)
"""

import os
import sys
import json
import time
import logging
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

# ── azure-identity (required — hard fail if missing) ───────────────────────
try:
    from azure.identity import ClientSecretCredential, CredentialUnavailableError
    from azure.core.exceptions import ClientAuthenticationError
except ImportError:
    print(
        "FATAL: azure-identity is not installed.\n"
        "  Fix: pip install azure-identity\n"
        "  Then restart the server.",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Constants ──────────────────────────────────────────────────────────────
ENV_FILE    = Path("/Users/danexall/biomimetics/scripts/secret_manager/.env")
LOG_DIR     = Path("/Users/danexall/biomimetics/logs")
SERVER_VER  = "3.0.0-strict"

KV_SCOPE    = "https://vault.azure.net/.default"
KV_API_VER  = "7.4"
CACHE_TTL   = 300   # seconds; short-lived to minimise staleness window

# ── Logging ────────────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "credentials_server.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("credentials_server")


# ── Load .env explicitly before touching os.getenv ────────────────────────
def _load_env_file(path: Path) -> None:
    """Manually parse KEY=VALUE lines from .env; works without python-dotenv."""
    if not path.exists():
        log.error(f"FATAL: .env file not found at {path}")
        log.error("  Create it with AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,")
        log.error("  CREDENTIALS_API_KEY, AZURE_KEY_VAULT_NAME, CREDENTIALS_PORT")
        sys.exit(1)

    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:   # don't override inherited env
                os.environ[key] = value

    log.info(f"Loaded env from {path}")

    # Also try python-dotenv for richer .env syntax if available
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)
    except ImportError:
        pass


_load_env_file(ENV_FILE)

# ── Read config (after .env is loaded) ────────────────────────────────────
AZURE_KEY_VAULT_NAME = os.environ.get("AZURE_KEY_VAULT_NAME", "arca-mcp-kv-dae")
AZURE_TENANT_ID      = os.environ.get("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID      = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET  = os.environ.get("AZURE_CLIENT_SECRET", "")
CREDENTIALS_API_KEY  = os.environ.get("CREDENTIALS_API_KEY", "")
CREDENTIALS_PORT     = int(os.environ.get("CREDENTIALS_PORT", "8089"))

VAULT_BASE_URL = f"https://{AZURE_KEY_VAULT_NAME}.vault.azure.net"


# ── Validate required config at startup ───────────────────────────────────
def _require_env() -> None:
    """Hard-fail if any required Azure credential is missing."""
    required = {
        "AZURE_TENANT_ID":     AZURE_TENANT_ID,
        "AZURE_CLIENT_ID":     AZURE_CLIENT_ID,
        "AZURE_CLIENT_SECRET": AZURE_CLIENT_SECRET,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        log.error("=" * 60)
        log.error("FATAL: Missing required Azure Service Principal credentials:")
        for k in missing:
            log.error(f"  {k} — not set in {ENV_FILE}")
        log.error("")
        log.error("Add them to your .env file:")
        log.error(f"  {ENV_FILE}")
        log.error("=" * 60)
        sys.exit(1)

    if not CREDENTIALS_API_KEY:
        log.warning("CREDENTIALS_API_KEY not set — authentication disabled (dev mode only!)")


# ── Credential + token state ───────────────────────────────────────────────
_credential: Optional[ClientSecretCredential] = None
_token_lock  = threading.Lock()
_token_cache: Dict[str, tuple] = {}   # {scope: (token_str, expires_at)}

# In-memory secret cache
_secret_lock  = threading.Lock()
_secret_cache: Dict[str, tuple] = {}  # {name: (value, timestamp)}

# Metrics
_metrics_lock   = threading.Lock()
_request_count  = 0
_error_count    = 0
_last_reset     = time.time()

# Azure connectivity status (updated on each token refresh)
_azure_healthy  = False


# ── Azure token refresh ────────────────────────────────────────────────────

def _get_access_token() -> str:
    """
    Return a valid Bearer token for Key Vault using ClientSecretCredential.
    Raises CredentialUnavailableError / ClientAuthenticationError on failure —
    callers must propagate these as 503 to the client.
    """
    global _azure_healthy

    with _token_lock:
        cached = _token_cache.get(KV_SCOPE)
        if cached:
            token_str, expires_at = cached
            if time.time() < expires_at:
                return token_str

    # get_token() raises on failure — let it propagate
    token = _credential.get_token(KV_SCOPE)

    with _token_lock:
        _token_cache[KV_SCOPE] = (token.token, token.expires_on - 60)

    _azure_healthy = True
    log.info("Azure AD token refreshed via ClientSecretCredential")
    return token.token


# ── Key Vault fetch ────────────────────────────────────────────────────────

def _fetch_from_keyvault(secret_name: str) -> str:
    """
    Fetch a secret directly from Azure Key Vault.
    Raises HTTPException with appropriate status codes — NO local fallback.
    """
    try:
        access_token = _get_access_token()
    except (ClientAuthenticationError, CredentialUnavailableError) as e:
        global _azure_healthy
        _azure_healthy = False
        log.error(f"[AZURE AUTH FAILED] Cannot authenticate to Key Vault: {e}")
        raise HTTPException(
            status_code=503,
            detail=(
                "Azure Key Vault unreachable: service principal authentication failed. "
                "Local fallbacks are disabled. Check AZURE_CLIENT_SECRET in .env."
            ),
        )
    except Exception as e:
        _azure_healthy = False
        log.error(f"[AZURE TOKEN ERROR] Unexpected error getting token: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Azure Key Vault unreachable: {e}. Local fallbacks are disabled.",
        )

    url = f"{VAULT_BASE_URL}/secrets/{secret_name}?api-version={KV_API_VER}"

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                url, headers={"Authorization": f"Bearer {access_token}"}
            )
    except httpx.TimeoutException:
        _azure_healthy = False
        log.error(f"[AZURE TIMEOUT] Key Vault timed out for secret '{secret_name}'")
        raise HTTPException(
            status_code=503,
            detail=(
                "Azure Key Vault request timed out. "
                "Local fallbacks are disabled."
            ),
        )
    except httpx.RequestError as e:
        _azure_healthy = False
        log.error(f"[AZURE NETWORK ERROR] {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Azure Key Vault network error: {e}. Local fallbacks are disabled.",
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Secret '{secret_name}' not found in Azure Key Vault.",
        )

    if response.status_code == 401 or response.status_code == 403:
        _azure_healthy = False
        raise HTTPException(
            status_code=503,
            detail=(
                f"Azure Key Vault access denied (HTTP {response.status_code}). "
                "Check service principal permissions on the vault."
            ),
        )

    if response.status_code != 200:
        _azure_healthy = False
        log.error(f"[AZURE KV ERROR] {response.status_code}: {response.text[:200]}")
        raise HTTPException(
            status_code=503,
            detail=(
                f"Azure Key Vault returned HTTP {response.status_code}. "
                "Local fallbacks are disabled."
            ),
        )

    _azure_healthy = True
    return response.json()["value"]


def _get_cached_secret(secret_name: str) -> str:
    """Return secret from in-memory cache (CACHE_TTL seconds) or fetch from Key Vault."""
    with _secret_lock:
        hit = _secret_cache.get(secret_name)
        if hit:
            value, ts = hit
            if time.time() - ts < CACHE_TTL:
                return value

    # Cache miss — fetch from Key Vault (raises on any failure)
    value = _fetch_from_keyvault(secret_name)

    with _secret_lock:
        _secret_cache[secret_name] = (value, time.time())
        # Evict oldest if cache grows large
        if len(_secret_cache) > 500:
            oldest_key = min(_secret_cache, key=lambda k: _secret_cache[k][1])
            del _secret_cache[oldest_key]

    return value


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Azure Credentials Server",
    description=(
        "API key-authenticated gateway to Azure Key Vault. "
        "Strict mode: no local fallbacks."
    ),
    version=SERVER_VER,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """API key authentication dependency."""
    global _request_count

    with _metrics_lock:
        _request_count += 1
        if time.time() - _last_reset > 3600:
            globals()["_request_count"] = 0
            globals()["_last_reset"]   = time.time()

    if not CREDENTIALS_API_KEY:
        return "unauthenticated"

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(x_api_key, CREDENTIALS_API_KEY):
        log.warning("Invalid API key attempt")
        raise HTTPException(status_code=401, detail="Invalid API key")

    return x_api_key


@app.get("/health")
async def health_check():
    """
    Health check — always returns HTTP 200.
    azure_status reflects last known Key Vault connectivity.
    """
    return {
        "status": "healthy",
        "version": SERVER_VER,
        "vault": AZURE_KEY_VAULT_NAME,
        "azure_status": "online" if _azure_healthy else "offline",
        "cache_size": len(_secret_cache),
        "fallback_mode": "disabled",
    }


@app.get("/metrics")
async def metrics(api_key: str = Depends(verify_api_key)):
    return {
        "requests": _request_count,
        "cache_size": len(_secret_cache),
        "cached_secrets": list(_secret_cache.keys()),
        "azure_status": "online" if _azure_healthy else "offline",
        "vault": AZURE_KEY_VAULT_NAME,
        "fallback_mode": "disabled",
    }


class BatchRequest(BaseModel):
    secrets: List[str]


class BatchResponse(BaseModel):
    secrets: Dict[str, Optional[str]]
    errors:  Dict[str, str]


@app.get("/secrets/{name}")
async def get_secret(name: str, api_key: str = Depends(verify_api_key)):
    """
    Fetch a single secret from Azure Key Vault.
    Returns 503 if Azure is unreachable. Returns 404 if the secret does not exist.
    No local fallback.
    """
    value = _get_cached_secret(name)   # raises HTTPException on any failure
    log.info(f"Secret served: {name} (source=azure_kv)")
    return {"name": name, "value": value, "source": "azure_kv"}


@app.get("/secrets")
async def list_secrets(api_key: str = Depends(verify_api_key)):
    """List all secret names in the vault. Returns 503 if Azure is unreachable."""
    access_token = _get_access_token()   # raises HTTPException on failure

    url = f"{VAULT_BASE_URL}/secrets?api-version={KV_API_VER}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Key Vault network error: {e}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=503,
            detail=f"Key Vault returned HTTP {resp.status_code} when listing secrets.",
        )

    names = [item["id"].split("/")[-1] for item in resp.json().get("value", [])]
    return {"count": len(names), "secrets": names, "source": "azure_kv"}


@app.post("/secrets/batch", response_model=BatchResponse)
async def get_secrets_batch(request: BatchRequest, api_key: str = Depends(verify_api_key)):
    """
    Fetch multiple secrets.  Per-secret errors (e.g. 404) are captured in `errors`;
    auth/network failures raise 503 immediately.
    """
    results: Dict[str, Optional[str]] = {}
    errors:  Dict[str, str]           = {}

    for name in request.secrets:
        try:
            results[name] = _get_cached_secret(name)
        except HTTPException as exc:
            if exc.status_code == 404:
                results[name] = None
                errors[name]  = exc.detail
            else:
                # Surface auth / network failures immediately
                raise

    log.info(
        f"Batch: {len(request.secrets)} requested, "
        f"{len(errors)} missing/errored"
    )
    return BatchResponse(secrets=results, errors=errors)


@app.post("/secrets/rotate")
async def rotate_cache(name: Optional[str] = None, api_key: str = Depends(verify_api_key)):
    """Invalidate in-memory cache to force a fresh Key Vault fetch."""
    with _secret_lock:
        if name:
            _secret_cache.pop(name, None)
            return {"status": "cleared", "secret": name}
        count = len(_secret_cache)
        _secret_cache.clear()
    return {"status": "cleared", "count": count}


@app.get("/")
async def root():
    return {
        "service": "Azure Credentials Server",
        "version": SERVER_VER,
        "azure_status": "online" if _azure_healthy else "offline",
        "fallback_mode": "disabled",
        "docs": "/docs",
        "endpoints": [
            "GET  /health              - Health check (always 200)",
            "GET  /secrets/{name}     - Fetch secret (503 if Azure unreachable)",
            "GET  /secrets            - List secret names",
            "POST /secrets/batch      - Batch fetch",
            "POST /secrets/rotate     - Clear in-memory cache",
            "GET  /metrics            - Usage metrics",
        ],
    }


# ── Boot sequence ──────────────────────────────────────────────────────────

def _boot() -> None:
    """
    Validate config, build credential, and probe Azure connectivity.
    Hard-fails (sys.exit) only when service principal credentials are missing.
    If credentials are present but Azure is temporarily unreachable, the server
    starts and will retry on the first client request.
    """
    global _credential, _azure_healthy

    # Validate required env vars — exits if any are missing
    _require_env()

    # Build credential object
    _credential = ClientSecretCredential(
        tenant_id=AZURE_TENANT_ID,
        client_id=AZURE_CLIENT_ID,
        client_secret=AZURE_CLIENT_SECRET,
    )
    log.info(
        f"ClientSecretCredential built for tenant={AZURE_TENANT_ID[:8]}... "
        f"client={AZURE_CLIENT_ID[:8]}..."
    )

    # Probe connectivity (non-fatal if Azure is temporarily unavailable at boot)
    log.info("Probing Azure Key Vault connectivity...")
    try:
        _get_access_token()
        log.info("✓ Azure AD authentication successful — Key Vault is reachable")
        _azure_healthy = True
    except (ClientAuthenticationError, CredentialUnavailableError) as e:
        log.error("=" * 60)
        log.error("✗ Azure authentication FAILED at boot.")
        log.error(f"  {e}")
        log.error("  This usually means AZURE_CLIENT_SECRET is wrong or expired.")
        log.error("  The server will start but ALL secret requests will return 503")
        log.error("  until the credential is fixed and the daemon restarted.")
        log.error("=" * 60)
        _azure_healthy = False
        # Do NOT sys.exit here — let the server start so /health is queryable
    except Exception as e:
        log.warning(f"⚠ Azure probe failed (may be transient): {e}")
        log.warning("  Server will start; first client request will retry.")
        _azure_healthy = False


def main():
    import uvicorn

    log.info("=" * 60)
    log.info(f"Azure Credentials Server {SERVER_VER}")
    log.info(f"  Vault    : {AZURE_KEY_VAULT_NAME}")
    log.info(f"  Port     : {CREDENTIALS_PORT}")
    log.info(f"  Fallback : DISABLED — Azure Key Vault is the single source of truth")
    log.info("=" * 60)

    _boot()

    log.info("Starting uvicorn...")

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=CREDENTIALS_PORT,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
