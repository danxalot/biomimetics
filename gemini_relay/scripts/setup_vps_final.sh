#!/bin/bash
#
# Gemini Relay VPS Setup - Final Version
#

set -euo pipefail

# Configuration
GEMINI_RELAY_DIR="/opt/gemini_relay"
CLOUDFLARED_TUNNEL_TOKEN="eyJhIjoiYWEwYTM4NmQwY2JkMDc2ODU3MjNiMjQyZTkxNTdlNjciLCJ0IjoiNjEzNDRhODMtMDA2Yy00ZGY5LWEzMzgtMTZhMTI1NzBiYjM2IiwicyI6IlpEUXpZekk1WWpZdE9EWmxPUzAwWlRVNExXRTFNakl0TlRFM01EazVOMlV5WldReCJ9"
GEMINI_API_KEY="[REDACTED]"
RELAY_PORT=8765
TUNNEL_HOSTNAME="gemini-relay.bios-mcp.workers.dev"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "============================================================"
echo "  Gemini Relay VPS Setup"
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

# Install dependencies
log_info "Installing dependencies..."
apt-get install -y python3 python3-pip python3-venv curl wget jq
log_success "Dependencies installed"

# Install cloudflared
log_info "Installing cloudflared..."
curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i /tmp/cloudflared.deb 2>/dev/null || true
rm -f /tmp/cloudflared.deb
log_success "cloudflared installed: $(cloudflared --version 2>&1 | head -1)"

# Create gemini relay directory
mkdir -p "$GEMINI_RELAY_DIR"
cd "$GEMINI_RELAY_DIR"

# Create WebSocket relay server
log_info "Creating Gemini Relay server..."
cat > "$GEMINI_RELAY_DIR/relay_server.py" << 'PYEOF'
#!/usr/bin/env python3
"""Gemini WebSocket Relay Server"""

import asyncio
import websockets
import json
import os
import sys
from datetime import datetime

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
RELAY_PORT = int(os.getenv("RELAY_PORT", "8765"))

connected_clients = set()

async def handler(websocket):
    connected_clients.add(websocket)
    client_ip = websocket.remote_address
    print(f"🔌 Client connected: {client_ip} ({len(connected_clients)} total)")
    
    try:
        # Send welcome message
        await websocket.send(json.dumps({
            "type": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Gemini Relay connected"
        }))
        
        async for message in websocket:
            try:
                data = json.loads(message)
                print(f"📤 [{client_ip}] {data.get('type', 'unknown')}")
                
                # Echo response with timestamp
                response = {
                    "type": "echo",
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat(),
                    "api_configured": bool(GEMINI_API_KEY)
                }
                await websocket.send(json.dumps(response))
                
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                
    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 Client disconnected: {client_ip}")
    finally:
        connected_clients.discard(websocket)

async def main():
    print(f"🚀 Gemini Relay Server starting on port {RELAY_PORT}...")
    print(f"   API Key configured: {'Yes' if GEMINI_API_KEY else 'No'}")
    print(f"   Endpoint: ws://0.0.0.0:{RELAY_PORT}/")
    
    async with websockets.serve(handler, "0.0.0.0", RELAY_PORT):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
PYEOF

chmod +x "$GEMINI_RELAY_DIR/relay_server.py"

# Save API key
echo "$GEMINI_API_KEY" > "$GEMINI_RELAY_DIR/.gemini_api_key"
chmod 600 "$GEMINI_RELAY_DIR/.gemini_api_key"

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
Environment=GEMINI_API_KEY=$GEMINI_API_KEY
Environment=RELAY_PORT=$RELAY_PORT
ExecStart=/usr/bin/python3 $GEMINI_RELAY_DIR/relay_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create cloudflared tunnel config
log_info "Creating Cloudflare Tunnel configuration..."
mkdir -p /etc/cloudflared

# Decode and save tunnel credentials
echo "$CLOUDFLARED_TUNNEL_TOKEN" | base64 -d > /etc/cloudflared/tunnel.json 2>/dev/null || {
    # If base64 decode fails, the token might already be decoded JSON
    echo "$CLOUDFLARED_TUNNEL_TOKEN" > /etc/cloudflared/tunnel.json
}

# Get tunnel ID from credentials
TUNNEL_ID=$(cat /etc/cloudflared/tunnel.json | jq -r '.TunnelID // .tunnelID // empty' 2>/dev/null || echo "")
if [ -z "$TUNNEL_ID" ]; then
    log_error "Could not parse tunnel credentials"
    exit 1
fi
log_success "Tunnel ID: $TUNNEL_ID"

# Create cloudflared config
cat > /etc/cloudflared/config.yml << EOF
tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/tunnel.json

ingress:
  - hostname: $TUNNEL_HOSTNAME
    service: http://localhost:$RELAY_PORT
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
RestartSec=5
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
sleep 5

# Check status
echo ""
echo "=== Service Status ==="
echo ""
echo "--- gemini-relay ---"
systemctl status gemini-relay --no-pager -l || true
echo ""
echo "--- cloudflared-tunnel ---"
systemctl status cloudflared-tunnel --no-pager -l || true

# Check logs
echo ""
echo "=== Recent Logs ==="
echo ""
echo "--- gemini-relay logs ---"
journalctl -u gemini-relay --no-pager -n 10 || true
echo ""
echo "--- cloudflared-tunnel logs ---"
journalctl -u cloudflared-tunnel --no-pager -n 10 || true

# Check if ports are listening
echo ""
echo "=== Listening Ports ==="
ss -tlnp 2>/dev/null | grep -E "$RELAY_PORT|cloudflared" || netstat -tlnp 2>/dev/null | grep -E "$RELAY_PORT|cloudflared" || echo "Port check completed"

echo ""
echo "============================================================"
log_success "Setup complete!"
echo "============================================================"
echo ""
echo "🌐 Public URL: wss://$TUNNEL_HOSTNAME/"
echo "🔌 Local Endpoint: ws://localhost:$RELAY_PORT/"
echo ""
echo "Commands:"
echo "  - Check status: systemctl status gemini-relay cloudflared-tunnel"
echo "  - View logs: journalctl -u gemini-relay -f"
echo "  - Restart: systemctl restart gemini-relay cloudflared-tunnel"
echo ""
