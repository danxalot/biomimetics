#!/bin/bash
# MuninnDB Go Binary Installation Script
# For GCP e2-micro VM (Debian 11)

set -e

echo "=== MuninnDB Installation ==="
date

# Stop any existing Python server
pkill -9 -f muninn-server.py 2>/dev/null || true
pkill -9 -f 'python.*8080' 2>/dev/null || true

# Create data directory (user is danexall on this VM)
mkdir -p /home/danexall/muninn/data
chown danexall:danexall /home/danexall/muninn/data

# Download official Go binary
echo "Downloading MuninnDB v0.4.2-alpha..."
curl -sL 'https://github.com/scrypster/muninndb/releases/download/v0.4.2-alpha/muninn_v0.4.2-alpha_linux_amd64.tar.gz' -o /tmp/muninn.tar.gz
tar -xzf /tmp/muninn.tar.gz -C /tmp/
mv /tmp/muninn /usr/local/bin/muninn
chmod +x /usr/local/bin/muninn

echo "MuninnDB version:"
muninn --version

# Create systemd service
echo "Creating systemd service..."
cat > /etc/systemd/system/muninndb.service << 'EOF'
[Unit]
Description=MuninnDB Cognitive Memory Service
After=network.target
Documentation=https://github.com/scrypster/muninndb

[Service]
Type=simple
User=danexall
Group=danexall
WorkingDirectory=/home/danexall/muninn
ExecStart=/usr/local/bin/muninn start --data-dir /home/danexall/muninn/data
Restart=always
RestartSec=10
LimitNOFILE=65536

# Resource limits for e2-micro (1GB RAM)
MemoryMax=768M
MemoryHigh=512M

# Environment
Environment=HOME=/home/danexall
Environment=MUNINN_DATA_DIR=/home/danexall/muninn/data

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl daemon-reload
systemctl enable muninndb
systemctl start muninndb

# Wait for startup
sleep 5

# Check status
echo "=== Service Status ==="
systemctl status muninndb --no-pager || true

# Test HTTP endpoint
echo "=== Testing HTTP endpoint ==="
curl -s http://localhost:8097/health 2>/dev/null || echo "Service starting..."

echo "=== Installation Complete ==="
