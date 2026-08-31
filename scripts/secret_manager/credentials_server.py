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
from fastapi.concurrency import run_in_threadpool
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

# In-memory cache for the full secret-NAME listing (the /secrets endpoint).
# Listing paginates over ~7 Key Vault pages, so we cache the assembled list for
# a short TTL to avoid re-walking every page on every discovery call.
_list_lock  = threading.Lock()
_list_cache: Optional[tuple] = None   # (names: List[str], pages: int, timestamp)
LIST_CACHE_TTL = 60   # seconds

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

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(app_: "FastAPI"):
    # STARTUP: warm the /credentials/* cache in a daemon thread so the port
    # binds immediately and the first Oracle-wallet bootstrap (client timeout
    # 10s) hits a warm cache. _warm_credentials_cache is defined below; it is
    # resolved at call time, so the forward reference is fine.
    threading.Thread(
        target=_warm_credentials_cache, name="cred-cache-warmer", daemon=True
    ).start()
    yield
    # SHUTDOWN: nothing to clean up (stateless caches, no open pools).


app = FastAPI(
    title="Azure Credentials Server",
    description=(
        "API key-authenticated gateway to Azure Key Vault. "
        "Strict mode: no local fallbacks."
    ),
    version=SERVER_VER,
    lifespan=_lifespan,
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


# GENESIS_CHAIN_API_KEY — the token fleet services present via the X-Genesis-X-Chain
# header (shared/credentials_client.py). The removed in-network bios_credentials_server
# accepted this on /credentials/*; we honour it here so those callers keep working
# against the authoritative KV server. Falls back to the standard API key, then the
# documented dev key, so a service configured either way authenticates.
GENESIS_CHAIN_API_KEY = os.environ.get("GENESIS_CHAIN_API_KEY", "") or CREDENTIALS_API_KEY


async def verify_chain_or_api_key(
    x_api_key: str = Header(None),
    x_genesis_x_chain: str = Header(None),
) -> str:
    """
    Auth for the /credentials/* routes. Accepts EITHER the standard X-API-Key
    (matching CREDENTIALS_API_KEY) OR the X-Genesis-X-Chain token that fleet
    services already send (credentials_client.py). This keeps the client
    contract whole now that these routes live on the KV server.
    """
    global _request_count
    with _metrics_lock:
        _request_count += 1
        if time.time() - _last_reset > 3600:
            globals()["_request_count"] = 0
            globals()["_last_reset"]   = time.time()

    if not CREDENTIALS_API_KEY:
        return "unauthenticated"

    # Standard API key
    if x_api_key and secrets.compare_digest(x_api_key, CREDENTIALS_API_KEY):
        return x_api_key

    # Genesis chain token (fleet default). Also allow the documented dev key so a
    # locally-run service with GENESIS_CHAIN_API_KEY=local-dev-genesis-key works.
    if x_genesis_x_chain:
        if GENESIS_CHAIN_API_KEY and secrets.compare_digest(x_genesis_x_chain, GENESIS_CHAIN_API_KEY):
            return x_genesis_x_chain
        if secrets.compare_digest(x_genesis_x_chain, "local-dev-genesis-key"):
            return x_genesis_x_chain

    if not x_api_key and not x_genesis_x_chain:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key or X-Genesis-X-Chain header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    log.warning("Invalid credentials on /credentials/* route")
    raise HTTPException(status_code=403, detail="Invalid credentials token")


def _warm_credentials_cache() -> None:
    """
    Pre-fetch the Oracle wallet + db secrets into the cache so the FIRST client
    call to /credentials/* is already warm. Runs in a background daemon thread
    (started on app startup) so it NEVER delays the port bind. Best-effort:
    logs and returns on any failure (a client call will just pay the cold cost).
    """
    try:
        w = _wallet_files_b64()
        d = _database_credentials()
        log.info(
            f"cache warmed: wallet={len(w)} files, db={len(d)} keys (background)"
        )
    except Exception as e:  # noqa: BLE001 — best-effort warmer, never crash startup
        log.warning(f"background cache warm failed (non-fatal): {e}")


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
    # Azure Key Vault does not support underscores in secret names.
    azure_name = name.replace("_", "-")
    value = _get_cached_secret(azure_name)   # raises HTTPException on any failure
    log.info(f"Secret served: {azure_name} (source=azure_kv)")
    return {"name": name, "value": value, "source": "azure_kv"}


def _list_all_secret_names() -> tuple:
    """
    Return (names, pages) for EVERY secret in the vault, following Azure KV
    pagination to the end. Result is cached for LIST_CACHE_TTL seconds.

    Azure Key Vault paginates the list endpoint (default 25 items/page) and
    returns a `nextLink` for the following page. We MUST follow it to the end,
    or callers only ever see the first page. (This was the "only 25 secrets"
    bug: the handler used to return page 1 and stop, so /secrets reported 25
    while the vault actually holds ~174.)

    NOTE: this is a *synchronous* (blocking httpx) function. It MUST be called
    off the event loop (via run_in_threadpool) so a multi-page walk can never
    starve /health or /secrets/{name}.
    """
    global _list_cache

    # serve from cache if fresh
    with _list_lock:
        if _list_cache is not None:
            names, pages, ts = _list_cache
            if time.time() - ts < LIST_CACHE_TTL:
                return names, pages

    access_token = _get_access_token()   # raises HTTPException on failure

    names: List[str] = []
    url: Optional[str] = f"{VAULT_BASE_URL}/secrets?api-version={KV_API_VER}"
    pages = 0
    MAX_PAGES = 1000  # hard safety cap against a pathological nextLink loop

    try:
        with httpx.Client(timeout=15.0) as client:
            while url and pages < MAX_PAGES:
                resp = client.get(
                    url, headers={"Authorization": f"Bearer {access_token}"}
                )
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"Key Vault returned HTTP {resp.status_code} "
                            f"when listing secrets (page {pages + 1})."
                        ),
                    )
                body = resp.json()
                names.extend(
                    item["id"].split("/")[-1] for item in body.get("value", [])
                )
                url = body.get("nextLink")   # None on the final page → loop ends
                pages += 1
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Key Vault network error: {e}")

    with _list_lock:
        _list_cache = (names, pages, time.time())

    return names, pages


@app.get("/secrets")
async def list_secrets(api_key: str = Depends(verify_api_key)):
    """List ALL secret names in the vault. Returns 503 if Azure is unreachable."""
    # Run the blocking, multi-page walk in a worker thread so it never blocks
    # the event loop (otherwise a 7-page fetch stalls every other request).
    names, pages = await run_in_threadpool(_list_all_secret_names)
    return {"count": len(names), "secrets": names, "source": "azure_kv", "pages": pages}


@app.post("/secrets/batch", response_model=BatchResponse)
async def get_secrets_batch(request: BatchRequest, api_key: str = Depends(verify_api_key)):
    """
    Fetch multiple secrets.  Per-secret errors (e.g. 404) are captured in `errors`;
    auth/network failures raise 503 immediately.
    """
    results: Dict[str, Optional[str]] = {}
    errors:  Dict[str, str]           = {}

    for name in request.secrets:
        azure_name = name.replace("_", "-")
        try:
            results[name] = _get_cached_secret(azure_name)
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
    global _list_cache
    if name:
        with _secret_lock:
            _secret_cache.pop(name, None)
        # a single-secret rotate may add/remove a name → drop the list cache too
        with _list_lock:
            _list_cache = None
        return {"status": "cleared", "secret": name}
    with _secret_lock:
        count = len(_secret_cache)
        _secret_cache.clear()
    with _list_lock:
        _list_cache = None
    return {"status": "cleared", "count": count}


# ── Oracle wallet + database credentials ────────────────────────────────────
# (2026-07-01) These routes were RE-ADDED. The prior note said this server did
# not expose them and the wallet was consumed via "direct wallet reads" — but
# services/oracle_utils/connection.py actually calls GET /credentials/wallet at
# runtime (via shared/credentials_client.fetch_and_write_wallet) to bootstrap a
# cold ORACLE_WALLET_DIR, and GET /credentials/database for connection details.
# Those routes lived on the removed in-network `bios_credentials_server`, which
# had NO Azure creds; the authoritative KV server never implemented them, so the
# client 404'd on a cold box. Since the wallet + db config are ALREADY in Key
# Vault, we serve them from there — the single source of truth stays intact.

# Map: Oracle wallet FILENAME → the Key Vault secret that holds its contents.
# Secrets suffixed "-b64" already store base64 of the binary file; plain ones
# store UTF-8 text. The client (fetch_and_write_wallet) base64-DECODES every
# value it receives, so we return base64 for BOTH kinds (pass through for the
# already-b64 secrets, encode for the text ones) — see _wallet_files_b64().
WALLET_SECRET_MAP = {
    "cwallet.sso":       ("oracle-wallet-cwallet-sso-b64",    True),   # (secret, already_b64)
    "ewallet.p12":       ("oracle-wallet-ewallet-p12-b64",    True),
    "keystore.jks":      ("oracle-wallet-keystore-jks-b64",   True),
    "truststore.jks":    ("oracle-wallet-truststore-jks-b64", True),
    "ewallet.pem":       ("oracle-wallet-ewallet-pem",        False),
    "ojdbc.properties":  ("oracle-wallet-ojdbc-properties",   False),
    "sqlnet.ora":        ("oracle-wallet-sqlnet-ora",         False),
    "tnsnames.ora":      ("oracle-wallet-tnsnames-ora",       False),
}


def _get_many_secrets(secret_names: List[str]) -> Dict[str, Optional[str]]:
    """
    Fetch several Key Vault secrets CONCURRENTLY (thread pool over the blocking
    _get_cached_secret). Returns {name: value or None-if-404}. Re-raises the
    first non-404 HTTPException (auth/network) so failures still surface as 503.

    This is what keeps the cold /credentials/* paths fast: the wallet is 8
    secrets and the db is ~9 — fetched serially that's ~27-30s (> the client's
    10s/5s timeouts). Fetched concurrently it collapses to ~one round-trip.
    """
    from concurrent.futures import ThreadPoolExecutor

    results: Dict[str, Optional[str]] = {}
    errors: List[HTTPException] = []

    def _one(nm: str):
        try:
            return nm, _get_cached_secret(nm), None
        except HTTPException as exc:
            return nm, None, exc

    # small pool — these are I/O-bound KV GETs; cap so we don't hammer KV
    with ThreadPoolExecutor(max_workers=min(10, max(1, len(secret_names)))) as ex:
        for nm, val, exc in ex.map(_one, secret_names):
            if exc is not None:
                if exc.status_code == 404:
                    results[nm] = None
                else:
                    errors.append(exc)
            else:
                results[nm] = val

    if errors:
        raise errors[0]   # first auth/network failure → 503
    return results


def _wallet_files_b64() -> Dict[str, str]:
    """
    Build {filename: base64_of_file_bytes} for the Oracle wallet, sourced from
    Key Vault. Synchronous (blocking httpx via _get_many_secrets) — call it off
    the event loop. Missing individual secrets are skipped (logged), not fatal,
    so a partially-populated vault still yields a usable wallet if the essentials
    are present. Raises HTTPException(503) only on an auth/network failure.
    """
    import base64
    wanted = {fn: (nm, b64) for fn, (nm, b64) in WALLET_SECRET_MAP.items()}
    fetched = _get_many_secrets([nm for (nm, _) in wanted.values()])

    files: Dict[str, str] = {}
    for filename, (secret_name, already_b64) in wanted.items():
        value = fetched.get(secret_name)
        if value is None:
            log.warning(f"wallet: secret '{secret_name}' not in vault — skipping {filename}")
            continue
        if already_b64:
            files[filename] = value.strip()            # already base64 of the binary
        else:
            files[filename] = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return files


@app.get("/credentials/wallet")
async def get_database_wallet(auth: str = Depends(verify_chain_or_api_key)):
    """
    Serve the Oracle wallet as {"files": {filename: base64}} — the exact shape
    shared/credentials_client.fetch_and_write_wallet expects (it b64-decodes each
    value and writes it to ORACLE_WALLET_DIR, chmod 600 for .pem/.p12/.sso).
    Sourced from Azure Key Vault (oracle-wallet-* secrets).
    """
    files = await run_in_threadpool(_wallet_files_b64)
    if not files:
        raise HTTPException(
            status_code=500,
            detail="No Oracle wallet secrets found in Key Vault (oracle-wallet-*).",
        )
    # The two files oracle_utils actually gates on must be present, else the
    # bootstrap would write a broken wallet and fail confusingly downstream.
    for essential in ("tnsnames.ora", "cwallet.sso"):
        if essential not in files:
            raise HTTPException(
                status_code=500,
                detail=f"Wallet incomplete: '{essential}' missing from Key Vault.",
            )
    log.info(f"Wallet served from Key Vault ({len(files)} files, source=azure_kv)")
    return {"wallet_dir_served": "azure_kv:oracle-wallet-*", "files": files}


def _database_credentials() -> Dict[str, str]:
    """
    Assemble Oracle connection details from Key Vault. Prefers the single
    `database-config-env` blob (parsed KEY=VALUE), overlaid with the individual
    `database-config-env-*` secrets. Synchronous — call off the event loop.
    """
    creds: Dict[str, str] = {}

    # 1) the whole .env blob, if present
    try:
        blob = _get_cached_secret("database-config-env")
        for raw in blob.splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                creds[k.strip()] = v.strip().strip('"').strip("'")
    except HTTPException as exc:
        if exc.status_code != 404:
            raise

    # 2) individual keys (authoritative if both exist). KV lower-cases + hyphenates,
    #    so e.g. WALLET_PASSWORD lives at database-config-env-WALLET-PASSWORD.
    #    Fetched concurrently (see _get_many_secrets) to stay under client timeouts.
    individual = {
        "PRIMARY_DB_NAME":     "database-config-env-PRIMARY-DB-NAME",
        "PRIMARY_DB_OCID":     "database-config-env-PRIMARY-DB-OCID",
        "SECONDARY_DB_NAME":   "database-config-env-SECONDARY-DB-NAME",
        "SECONDARY_DB_OCID":   "database-config-env-SECONDARY-DB-OCID",
        "SCHEMA_PASSWORD":     "database-config-env-SCHEMA-PASSWORD",
        "DB_ADMIN_PASSWORD":   "database-config-env-DB-ADMIN-PASSWORD",
        "WALLET_PASSWORD":     "database-config-env-WALLET-PASSWORD",
        "WALLET_DIR":          "database-config-env-WALLET-DIR",
    }
    fetched = _get_many_secrets(list(individual.values()))
    for key, secret_name in individual.items():
        val = fetched.get(secret_name)
        if val is not None:
            creds[key] = val
    return creds


@app.get("/credentials/database")
async def get_database_credentials(auth: str = Depends(verify_chain_or_api_key)):
    """Oracle connection details, sourced from Key Vault (database-config-env*)."""
    creds = await run_in_threadpool(_database_credentials)
    if not creds:
        raise HTTPException(
            status_code=500,
            detail="No database config found in Key Vault (database-config-env*).",
        )
    return creds


@app.get("/")
async def root():
    return {
        "service": "Azure Credentials Server",
        "version": SERVER_VER,
        "azure_status": "online" if _azure_healthy else "offline",
        "fallback_mode": "disabled",
        "docs": "/docs",
        "endpoints": [
            "GET  /health                - Health check (always 200)",
            "GET  /secrets/{name}       - Fetch secret (503 if Azure unreachable)",
            "GET  /secrets              - List secret names (paginated → all)",
            "POST /secrets/batch        - Batch fetch",
            "POST /secrets/rotate       - Clear in-memory cache",
            "GET  /credentials/wallet   - Oracle wallet files (base64) from KV",
            "GET  /credentials/database - Oracle connection details from KV",
            "GET  /metrics              - Usage metrics",
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

    # Bind all interfaces so Docker-network agents (ARCA containers) can reach
    # the single authoritative KV-backed server via host.docker.internal:8089,
    # not just host-local clients. Access is still gated by the X-API-Key header
    # (verify_api_key) and CORS is restricted to localhost origins.
    uvicorn.run(
        app,
        host=os.environ.get("CREDENTIALS_HOST", "0.0.0.0"),
        port=CREDENTIALS_PORT,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
