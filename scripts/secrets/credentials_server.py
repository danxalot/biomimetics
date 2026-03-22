#!/usr/bin/env python3
"""
Azure Credentials Server
Single source of truth for all secrets - fetches from Azure Key Vault.
Runs locally on macOS, provides API key-authenticated access to secrets.

Usage:
    python3 credentials_server.py

API Endpoints:
    GET  /secrets/{name}           - Fetch a single secret
    GET  /secrets                   - List all secret names (not values)
    POST /secrets/batch             - Fetch multiple secrets
    GET  /health                   - Health check
    GET  /metrics                  - Usage metrics

Authentication:
    Header: X-API-Key: <your-api-key>

Environment Variables:
    AZURE_KEY_VAULT_NAME    - Key vault name (default: arca-mcp-kv-dae)
    AZURE_TENANT_ID          - Azure AD tenant ID
    AZURE_CLIENT_ID           - Service principal app ID
    AZURE_CLIENT_SECRET       - Service principal secret
    CREDENTIALS_API_KEY       - API key for clients (generate a strong random string)
    CREDENTIALS_PORT         - Port to listen on (default: 8089)
"""

import os
import sys
import json
import time
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.expanduser("~/biomimetics/logs/credentials_server.log")
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("credentials_server")

# Configuration from environment
AZURE_KEY_VAULT_NAME = os.getenv("AZURE_KEY_VAULT_NAME", "arca-mcp-kv-dae")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
CREDENTIALS_API_KEY = os.getenv("CREDENTIALS_API_KEY", "")
CREDENTIALS_PORT = int(os.getenv("CREDENTIALS_PORT", "8089"))

# Token cache
_access_token: Optional[str] = None
_access_token_expires: datetime = datetime.min

# Secret cache (5 min TTL)
_secret_cache: Dict[str, tuple] = {}
_CACHE_TTL = 300

# Usage metrics
_request_count = 0
_last_reset = time.time()

app = FastAPI(
    title="Azure Credentials Server",
    description="API key-authenticated gateway to Azure Key Vault",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _get_access_token() -> str:
    """Get Azure AD access token using service principal."""
    global _access_token, _access_token_expires

    if _access_token and datetime.now() < _access_token_expires:
        return _access_token

    if not all([AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET]):
        raise HTTPException(
            status_code=500,
            detail="Azure credentials not configured. Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET",
        )

    token_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token"
    scope = "https://vault.azure.net/.default"

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": AZURE_CLIENT_ID,
                "client_secret": AZURE_CLIENT_SECRET,
                "scope": scope,
            },
        )

    if response.status_code != 200:
        log.error(f"Azure auth failed: {response.status_code} {response.text}")
        raise HTTPException(status_code=500, detail="Azure authentication failed")

    token_data = response.json()
    _access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)
    _access_token_expires = datetime.now() + timedelta(seconds=expires_in - 60)

    log.info("Azure AD token refreshed")
    return _access_token


def _get_secret_from_azure(secret_name: str) -> str:
    """Fetch a secret directly from Azure Key Vault."""
    access_token = _get_access_token()

    url = f"https://{AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/{secret_name}?api-version=7.4"

    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Secret '{secret_name}' not found")

    if response.status_code != 200:
        log.error(f"Key Vault error: {response.status_code} {response.text}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch secret from Key Vault"
        )

    return response.json()["value"]


def _get_cached_secret(secret_name: str) -> str:
    """Get secret with 5-min cache."""
    global _secret_cache

    if secret_name in _secret_cache:
        value, timestamp = _secret_cache[secret_name]
        if time.time() - timestamp < _CACHE_TTL:
            return value

    value = _get_secret_from_azure(secret_name)
    _secret_cache[secret_name] = (value, time.time())

    if len(_secret_cache) > 500:
        oldest = min(_secret_cache.items(), key=lambda x: x[1][1])
        del _secret_cache[oldest[0]]

    return value


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Dependency to verify API key."""
    global _request_count, _last_reset

    _request_count += 1

    if time.time() - _last_reset > 3600:
        _request_count = 0
        _last_reset = time.time()

    if not CREDENTIALS_API_KEY:
        log.warning("No API key configured - authentication disabled!")
        return "unauthenticated"

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(x_api_key, CREDENTIALS_API_KEY):
        log.warning(f"Invalid API key attempt from IP lookup")
        raise HTTPException(status_code=401, detail="Invalid API key")

    return x_api_key


@app.get("/health")
async def health_check():
    """Health check endpoint (no auth required)."""
    return {
        "status": "healthy",
        "vault": AZURE_KEY_VAULT_NAME,
        "cache_size": len(_secret_cache),
    }


@app.get("/metrics")
async def metrics(api_key: str = Depends(verify_api_key)):
    """Usage metrics."""
    return {
        "requests_since_reset": _request_count,
        "cache_size": len(_secret_cache),
        "cached_secrets": list(_secret_cache.keys()),
        "azure_token_valid": _access_token is not None
        and datetime.now() < _access_token_expires,
    }


class BatchRequest(BaseModel):
    secrets: List[str]


class BatchResponse(BaseModel):
    secrets: Dict[str, Optional[str]]
    missing: List[str]


@app.get("/secrets/{name}")
async def get_secret(
    name: str,
    api_key: str = Depends(verify_api_key),
):
    """Fetch a single secret by name."""
    try:
        value = _get_cached_secret(name)
        log.info(f"Secret fetched: {name}")
        return {"name": name, "value": value}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error fetching {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/secrets")
async def list_secrets(
    api_key: str = Depends(verify_api_key),
):
    """List all secret names in the vault (not values)."""
    try:
        access_token = _get_access_token()
        url = f"https://{AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets?api-version=7.4"

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to list secrets")

        data = response.json()
        names = [item["id"].split("/")[-1] for item in data.get("value", [])]
        return {"count": len(names), "secrets": names}

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error listing secrets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/secrets/batch", response_model=BatchResponse)
async def get_secrets_batch(
    request: BatchRequest,
    api_key: str = Depends(verify_api_key),
):
    """Fetch multiple secrets at once."""
    results = {}
    missing = []

    for name in request.secrets:
        try:
            results[name] = _get_cached_secret(name)
        except HTTPException as e:
            if e.status_code == 404:
                missing.append(name)
                results[name] = None
            else:
                raise

    log.info(f"Batch fetch: {len(request.secrets)} requested, {len(missing)} missing")
    return BatchResponse(secrets=results, missing=missing)


@app.post("/secrets/rotate")
async def rotate_secret_cache(
    name: Optional[str] = None,
    api_key: str = Depends(verify_api_key),
):
    """Invalidate cache for a secret (forces re-fetch on next request)."""
    global _secret_cache

    if name:
        if name in _secret_cache:
            del _secret_cache[name]
        return {"status": "cleared", "secret": name}
    else:
        count = len(_secret_cache)
        _secret_cache.clear()
        return {"status": "cleared", "count": count}


@app.get("/")
async def root():
    """Root endpoint with usage info."""
    return {
        "service": "Azure Credentials Server",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "GET /health - Health check",
            "GET /secrets/{name} - Fetch secret",
            "GET /secrets - List secret names",
            "POST /secrets/batch - Batch fetch secrets",
            "POST /secrets/rotate - Clear cache",
        ],
    }


def generate_api_key() -> str:
    """Generate a new random API key."""
    return secrets.token_urlsafe(32)


def main():
    import uvicorn

    log.info("=" * 60)
    log.info("Azure Credentials Server")
    log.info("=" * 60)
    log.info(f"Key Vault: {AZURE_KEY_VAULT_NAME}")
    log.info(f"Port: {CREDENTIALS_PORT}")

    if not CREDENTIALS_API_KEY:
        log.warning("⚠️  CREDENTIALS_API_KEY not set - generating temporary key")
        log.warning(
            "⚠️  Authentication DISABLED - set CREDENTIALS_API_KEY in environment"
        )
        temp_key = generate_api_key()
        log.warning(f"⚠️  Temporary API key: {temp_key}")
        log.warning(
            "⚠️  Add to your environment: export CREDENTIALS_API_KEY='" + temp_key + "'"
        )
    else:
        key_hint = CREDENTIALS_API_KEY[:4] + "..." + CREDENTIALS_API_KEY[-4:]
        log.info(f"API Key: {key_hint} (set)")

    if not all([AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET]):
        log.error("✗ Azure credentials missing!")
        log.error("  Set: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET")
        log.error("  Or run: az login && az account set --subscription <sub-id>")
        sys.exit(1)
    else:
        log.info("✓ Azure credentials configured")

    # Test Azure connection
    try:
        _get_access_token()
        log.info("✓ Azure AD authentication successful")
    except Exception as e:
        log.error(f"✗ Azure AD authentication failed: {e}")
        sys.exit(1)

    log.info("=" * 60)
    log.info("Starting server...")
    log.info("=" * 60)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=CREDENTIALS_PORT,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
