#!/bin/bash
#
# install_credentials_server.sh
# Generates and installs the macOS LaunchAgent for the Azure Credentials Server.
#
# Prerequisites:
#   1. ~/.env (or .env in this directory) must contain:
#        AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
#        CREDENTIALS_API_KEY, AZURE_KEY_VAULT_NAME, CREDENTIALS_PORT
#   2. python3 (system) must have azure-identity installed:
#        pip3 install azure-identity fastapi uvicorn httpx python-dotenv

set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
SERVER_SCRIPT="${SCRIPT_DIR}/credentials_server.py"
PLIST_LABEL="com.bios.credentials-server"
PLIST_PATH="${HOME}/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_DIR="${HOME}/biomimetics/logs"

# Prefer the Python that has azure-identity; the local venv shim is broken
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if ! "${PYTHON_BIN}" -c "import azure.identity" 2>/dev/null; then
    PYTHON_BIN="$(which python3)"
fi

# ── Validate prerequisites ─────────────────────────────────────────────────
echo "▶ Checking prerequisites..."

if [ ! -f "${ENV_FILE}" ]; then
    echo "ERROR: .env file not found at ${ENV_FILE}"
    echo ""
    echo "Create it with the following content:"
    echo "  AZURE_TENANT_ID=<your-tenant-id>"
    echo "  AZURE_CLIENT_ID=<your-client-id>"
    echo "  AZURE_CLIENT_SECRET=<your-client-secret>"
    echo "  CREDENTIALS_API_KEY=<strong-random-api-key>"
    echo "  AZURE_KEY_VAULT_NAME=arca-mcp-kv-dae"
    echo "  CREDENTIALS_PORT=8089"
    exit 1
fi

if [ ! -f "${SERVER_SCRIPT}" ]; then
    echo "ERROR: Server script not found at ${SERVER_SCRIPT}"
    exit 1
fi

if ! "${PYTHON_BIN}" -c "from azure.identity import ClientSecretCredential" 2>/dev/null; then
    echo "ERROR: azure-identity not installed for ${PYTHON_BIN}"
    echo "  Fix: pip3 install azure-identity fastapi uvicorn httpx python-dotenv"
    exit 1
fi

echo "  ✓ .env found"
echo "  ✓ server script found"
echo "  ✓ azure-identity OK (${PYTHON_BIN})"

# ── Source .env to read values for embedding in plist ─────────────────────
echo "▶ Loading env vars from ${ENV_FILE}..."
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# Verify required vars are now set
for VAR in AZURE_TENANT_ID AZURE_CLIENT_ID AZURE_CLIENT_SECRET CREDENTIALS_API_KEY AZURE_KEY_VAULT_NAME; do
    if [ -z "${!VAR:-}" ]; then
        echo "ERROR: ${VAR} is missing from ${ENV_FILE}"
        exit 1
    fi
done

CREDENTIALS_PORT="${CREDENTIALS_PORT:-8089}"
mkdir -p "${LOG_DIR}"
echo "  ✓ All required env vars present"

# ── Write plist ────────────────────────────────────────────────────────────
echo "▶ Writing LaunchAgent plist to ${PLIST_PATH}..."

cat > "${PLIST_PATH}" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${SERVER_SCRIPT}</string>
    </array>

    <!-- All Azure + server credentials baked in so the daemon never needs az login -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>AZURE_KEY_VAULT_NAME</key>
        <string>${AZURE_KEY_VAULT_NAME}</string>
        <key>AZURE_TENANT_ID</key>
        <string>${AZURE_TENANT_ID}</string>
        <key>AZURE_CLIENT_ID</key>
        <string>${AZURE_CLIENT_ID}</string>
        <key>AZURE_CLIENT_SECRET</key>
        <string>${AZURE_CLIENT_SECRET}</string>
        <key>CREDENTIALS_API_KEY</key>
        <string>${CREDENTIALS_API_KEY}</string>
        <key>CREDENTIALS_PORT</key>
        <string>${CREDENTIALS_PORT}</string>
    </dict>

    <!-- Always restart on crash or after sleep/wake token expiry -->
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/credentials_server.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/credentials_server.err</string>

    <key>ProcessType</key>
    <string>Background</string>
    <key>LowPriorityIO</key>
    <true/>
</dict>
</plist>
PLIST

echo "  ✓ Plist written"

# ── Reload LaunchAgent ─────────────────────────────────────────────────────
echo "▶ Reloading LaunchAgent..."
launchctl unload "${PLIST_PATH}" 2>/dev/null && echo "  · Unloaded existing agent" || true
launchctl load "${PLIST_PATH}" && echo "  ✓ Loaded successfully"

# ── Verify ─────────────────────────────────────────────────────────────────
sleep 3
echo ""
echo "▶ Verifying server is up..."
if curl -sf "http://localhost:${CREDENTIALS_PORT}/health" | python3 -m json.tool; then
    echo ""
    echo "✓ Credentials Server is running on port ${CREDENTIALS_PORT}"
else
    echo ""
    echo "⚠ Server may still be starting. Check logs:"
    echo "  tail -50 ${LOG_DIR}/credentials_server.log"
    echo "  tail -20 ${LOG_DIR}/credentials_server.err"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  To check status:   launchctl list | grep bios.credentials"
echo "  To view logs:      tail -f ${LOG_DIR}/credentials_server.log"
echo "  To reload:         bash ${BASH_SOURCE[0]}"
echo "  To test a secret:  curl -H 'X-API-Key: \$CREDENTIALS_API_KEY' \\"
echo "                          http://localhost:${CREDENTIALS_PORT}/secrets/gemini-api-key"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
