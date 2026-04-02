#!/bin/bash
# Setup permanent Cloudflare Tunnel for Gemini Relay

set -euo pipefail

TUNNEL_NAME="gemini-relay-tunnel"
TUNNEL_HOSTNAME="gemini-relay.arca-vsa.tech"
RELAY_PORT=8765

echo "=== Setting up Permanent Cloudflare Tunnel ==="
echo ""

# Stop existing cloudflared service
systemctl stop cloudflared-tunnel 2>/dev/null || true

# Login to Cloudflare (this requires manual auth URL visit)
echo "Step 1: Authenticate with Cloudflare"
echo "Running cloudflared login..."
cloudflared tunnel login 2>&1

# Create the tunnel
echo ""
echo "Step 2: Creating tunnel '$TUNNEL_NAME'..."
cloudflared tunnel create "$TUNNEL_NAME" 2>&1

# Get tunnel ID
TUNNEL_ID=$(cloudflared tunnel list --output json 2>/dev/null | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Tunnel ID: $TUNNEL_ID"

# Create config
echo ""
echo "Step 3: Creating tunnel configuration..."
cat > /etc/cloudflared/config.yml << EOF
tunnel: $TUNNEL_ID
credentials-file: /root/.cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: $TUNNEL_HOSTNAME
    service: http://localhost:$RELAY_PORT
  - service: http_status:404
EOF

# Route DNS
echo ""
echo "Step 4: Creating DNS route..."
cloudflared tunnel route dns "$TUNNEL_NAME" "$TUNNEL_HOSTNAME" 2>&1

# Update systemd service
echo ""
echo "Step 5: Updating systemd service..."
cat > /etc/systemd/system/cloudflared-tunnel.service << EOF
[Unit]
Description=Cloudflare Tunnel - $TUNNEL_NAME
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

systemctl daemon-reload
systemctl enable cloudflared-tunnel
systemctl start cloudflared-tunnel

echo ""
echo "=== Tunnel Setup Complete ==="
echo "Public URL: https://$TUNNEL_HOSTNAME"
echo "WebSocket URL: wss://$TUNNEL_HOSTNAME/"
echo ""
echo "Check status: systemctl status cloudflared-tunnel"
