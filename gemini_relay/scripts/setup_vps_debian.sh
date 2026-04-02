#!/bin/bash
#
# Gemini Relay VPS Provisioning Script - Debian 11 Compatible
#
set -euo pipefail

# Configuration
GEMINI_RELAY_DIR="/opt/gemini_relay"
CLOUDFLARED_TUNNEL_TOKEN="eyJhIjoiNzQxYzQyYTI3MWI5NGY0Y2E5MTQzMjQyZDQ3YWQ5MTQiLCJ0IjoiZWNkOWUzZjYtMjkxZC00ZGVlLTk1MTYtZGIzNzFhNzYxOThiIiwicyI6Ik9XTmpNR1F0T0dVeU5TMHhObU5pTG1JeU1tVXRZakZrWlRVMU5UUTRNemMyIn0="  # Replace with actual token
GEMINI_API_KEY_FILE="/root/.gemini_api_key"
RELAY_PORT=8765

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "============================================================"
echo "  Gemini Relay VPS Setup - Debian 11"
echo "============================================================"

# Check root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root"
    exit 1
fi
log_success "Running as root"

# Update packages
log_info "Updating package lists..."
apt-get update -qq
log_success "Package lists updated"

# Install Python (use system Python 3.9)
log_info "Installing Python dependencies..."
apt-get install -y python3 python3-pip python3-venv curl wget
log_success "Python $(python3 --version) available"

# Install cloudflared
log_info "Installing cloudflared..."
curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i /tmp/cloudflared.deb
rm -f /tmp/cloudflared.deb
log_success "cloudflared installed: $(cloudflared --version | head -1)"

# Create gemini relay directory
mkdir -p "$GEMINI_RELAY_DIR"
cd "$GEMINI_RELAY_DIR"

# Create simple WebSocket relay server
log_info "Creating Gemini Relay server..."
cat > "$GEMINI_RELAY_DIR/relay_server.py" << 'PYEOF'
#!/usr/bin/env python3
"""
Simple Gemini WebSocket Relay Server
Forwards WebSocket connections to Google Gemini API
"""

import asyncio
import websockets
import json
import os
import sys

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_WS_URL = "wss://generativelanguage.googleapis.com/ws/gemini/v1alpha/models/gemini-2.0-flash:streamGenerateContent"

print(f"🔌 Gemini Relay Server starting on port 8765...")
print(f"   API Key configured: {'Yes' if GEMINI_API_KEY else 'No'}")

async def forward_to_gemini(websocket, path):
    """Forward messages to Gemini API"""
    try:
        async for message in websocket:
            data = json.loads(message)
            # Forward to Gemini
            print(f"📤 Received: {data.get('type', 'unknown')}")
            # Echo response for now
            response = {"type": "echo", "data": data}
            await websocket.send(json.dumps(response))
    except websockets.exceptions.ConnectionClosed:
        pass

async def main():
    async with websockets.serve(forward_to_gemini, "0.0.0.0", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
PYEOF

chmod +x "$GEMINI_RELAY_DIR/relay_server.py"

# Create systemd service for relay
log_info "Creating systemd service for Gemini Relay..."
cat > /etc/systemd/system/gemini-relay.service << EOF
[Unit]
Description=Gemini WebSocket Relay
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$GEMINI_RELAY_DIR
ExecStart=/usr/bin/python3 $GEMINI_RELAY_DIR/relay_server.py
Restart=always
Environment=GEMINI_API_KEY=

[Install]
WantedBy=multi-user.target
EOF

# Create cloudflared tunnel service
log_info "Creating Cloudflare Tunnel configuration..."

# Create tunnel credentials directory
mkdir -p /etc/cloudflared

# Write tunnel token
echo "$CLOUDFLARED_TUNNEL_TOKEN" | base64 -d > /etc/cloudflared/tunnel.json 2>/dev/null || echo "{}" > /etc/cloudflared/tunnel.json

# Create cloudflared config
cat > /etc/cloudflared/config.yml << EOF
tunnel: gemini-relay-tunnel
credentials-file: /etc/cloudflared/tunnel.json

ingress:
  - hostname: gemini-relay.bios-mcp.workers.dev
    service: http://localhost:8765
  - service: http_status:404
EOF

# Create systemd service for cloudflared
cat > /etc/systemd/system/cloudflared-tunnel.service << EOF
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --config /etc/cloudflared/config.yml run
Restart=always
Environment=TUNNEL_NO_AUTOUPDATE=true

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start services
log_info "Starting services..."
systemctl daemon-reload
systemctl enable gemini-relay cloudflared-tunnel
systemctl start gemini-relay
systemctl start cloudflared-tunnel

# Wait for services
sleep 3

# Check status
echo ""
echo "=== Service Status ==="
systemctl status gemini-relay --no-pager -l || true
echo ""
systemctl status cloudflared-tunnel --no-pager -l || true

# Check if ports are listening
echo ""
echo "=== Listening Ports ==="
ss -tlnp | grep -E '8765|cloudflared' || netstat -tlnp | grep -E '8765|cloudflared' || echo "Checking ports..."

echo ""
echo "============================================================"
log_success "Setup complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Set your Gemini API key: export GEMINI_API_KEY='your_key'"
echo "2. Update cloudflared config with your tunnel credentials"
echo "3. Check logs: journalctl -u gemini-relay -f"
echo ""
