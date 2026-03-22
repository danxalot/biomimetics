#!/bin/bash
# MuninnDB Go Binary Startup Script for Debian 12 (Bookworm)

set -e

echo "=== MuninnDB Go Binary Setup ==="
date

# Stop any existing processes
pkill -9 -f muninn-server.py 2>/dev/null || true
pkill -9 -f 'python.*8097' 2>/dev/null || true

# Create persistent data directory
mkdir -p /home/danexall/muninn/data

# Download MuninnDB Go binary if not exists
if [ ! -f /usr/local/bin/muninn ]; then
    echo "Downloading MuninnDB Go binary..."
    curl -sL 'https://github.com/scrypster/muninndb/releases/download/v0.4.2-alpha/muninn_v0.4.2-alpha_linux_amd64.tar.gz' -o /tmp/muninn.tar.gz
    tar -xzf /tmp/muninn.tar.gz -C /tmp/
    mv /tmp/muninn /usr/local/bin/muninn
    chmod +x /usr/local/bin/muninn
fi

echo "MuninnDB version:"
muninn --version

# Create systemd service (simple, no pre-start)
cat > /etc/systemd/system/muninndb.service << 'EOF'
[Unit]
Description=MuninnDB Go Service
After=network.target

[Service]
Type=simple
User=danexall
Group=danexall
WorkingDirectory=/home/danexall/muninn
Environment=HOME=/home/danexall
ExecStart=/usr/local/bin/muninn start --data-dir /home/danexall/muninn/data
Restart=always
RestartSec=10
LimitNOFILE=65536
MemoryMax=768M
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable muninndb
systemctl restart muninndb

sleep 10

echo ""
echo "=== Service Status ==="
systemctl status muninndb --no-pager | head -15

echo ""
echo "=== Test Endpoints ==="
curl -s --connect-timeout 3 http://localhost:8475/ || echo "8475 not responding"
curl -s --connect-timeout 3 http://localhost:8476/ || echo "8476 not responding"
curl -s --connect-timeout 3 http://localhost:8750/ || echo "8750 not responding"

echo ""
echo "=== Setup Complete ==="
