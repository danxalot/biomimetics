#!/bin/bash
#
# Gemini Relay VPS Provisioning Script
# Ubuntu-based micro VPS setup (0.1 vCPU / 512MB RAM)
#
# This script:
# 1. Installs Python 3.12+ and pip
# 2. Installs cloudflared daemon
# 3. Creates systemd service for WebSocket relay
# 4. Creates systemd service for Cloudflare Tunnel
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/your-repo/gemini_relay/setup_vps.sh | bash
#
# Or manually:
#   chmod +x setup_vps.sh && ./setup_vps.sh
#

set -euo pipefail

# Configuration
GEMINI_RELAY_DIR="/opt/gemini_relay"
GEMINI_RELAY_USER="gemini"
CLOUDFLARED_DIR="/usr/local/bin"
SYSTEMD_DIR="/etc/systemd/system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root (sudo ./setup_vps.sh)"
        exit 1
    fi
    log_success "Running as root"
}

# Update package lists
update_packages() {
    log_info "Updating package lists..."
    apt-get update -qq
    log_success "Package lists updated"
}

# Install Python 3.12+
install_python() {
    log_info "Installing Python 3.12+..."
    
    # Add deadsnakes PPA for latest Python
    apt-get install -y software-properties-common > /dev/null 2>&1
    add-apt-repository -y ppa:deadsnakes/ppa > /dev/null 2>&1
    apt-get update -qq
    
    # Install Python and pip
    apt-get install -y python3.12 python3.12-venv python3.12-dev python3-pip > /dev/null 2>&1
    
    # Set Python 3.12 as default
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
    update-alternatives --set python3 /usr/bin/python3.12
    
    log_success "Python $(python3 --version) installed"
}

# Install cloudflared
install_cloudflared() {
    log_info "Installing cloudflared..."
    
    # Download latest cloudflared for Linux AMD64
    curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb > /dev/null 2>&1
    
    # Install
    dpkg -i /tmp/cloudflared.deb > /dev/null 2>&1
    rm -f /tmp/cloudflared.deb
    
    # Verify installation
    if command -v cloudflared &> /dev/null; then
        log_success "cloudflared $(cloudflared --version | head -1) installed"
    else
        log_error "cloudflared installation failed"
        exit 1
    fi
}

# Create gemini user
create_user() {
    log_info "Creating $GEMINI_RELAY_USER user..."
    
    if id "$GEMINI_RELAY_USER" &>/dev/null; then
        log_warning "User $GEMINI_RELAY_USER already exists"
    else
        useradd -r -s /bin/false -d "$GEMINI_RELAY_DIR" "$GEMINI_RELAY_USER"
        log_success "User $GEMINI_RELAY_USER created"
    fi
}

# Create application directory
create_directory() {
    log_info "Creating application directory..."
    
    mkdir -p "$GEMINI_RELAY_DIR"
    mkdir -p /root/.gemini_relay
    
    chown -R "$GEMINI_RELAY_USER:$GEMINI_RELAY_USER" "$GEMINI_RELAY_DIR"
    
    log_success "Directory created: $GEMINI_RELAY_DIR"
}

# Install Python dependencies
install_dependencies() {
    log_info "Installing Python dependencies..."
    
    cd "$GEMINI_RELAY_DIR"
    
    # Create virtual environment
    python3 -m venv venv
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip -q
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt -q
        log_success "Python dependencies installed"
    else
        log_warning "requirements.txt not found, skipping dependency installation"
    fi
    
    deactivate
}

# Create systemd service for WebSocket relay
create_relay_service() {
    log_info "Creating systemd service for WebSocket relay..."
    
    cat > "$SYSTEMD_DIR/gemini-relay.service" << 'EOF'
[Unit]
Description=Gemini Live WebSocket Relay
Documentation=https://github.com/your-repo/gemini_relay
After=network.target cloudflared.service
Wants=cloudflared.service

[Service]
Type=simple
User=gemini
Group=gemini
WorkingDirectory=/opt/gemini_relay
Environment="PATH=/opt/gemini_relay/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=-/etc/gemini_relay.env
ExecStart=/opt/gemini_relay/venv/bin/python /opt/gemini_relay/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=gemini-relay

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/root/.gemini_relay /opt/gemini_relay

# Resource limits for micro VPS
MemoryLimit=256M
CPUQuota=50%

[Install]
WantedBy=multi-user.target
EOF

    log_success "Systemd service created: gemini-relay.service"
}

# Create systemd service for Cloudflare Tunnel
create_tunnel_service() {
    log_info "Creating systemd service for Cloudflare Tunnel..."
    
    cat > "$SYSTEMD_DIR/cloudflared-tunnel.service" << 'EOF'
[Unit]
Description=Cloudflare Tunnel for Gemini Relay
Documentation=https://developers.cloudflare.com/cloudflare-one/connections/connect-apps
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root
Environment="CLOUDFLARED_TUNNEL_TOKEN=${CLOUDFLARED_TUNNEL_TOKEN:-}"
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate run
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cloudflared-tunnel

# Security hardening
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

    log_success "Systemd service created: cloudflared-tunnel.service"
}

# Create environment file template
create_env_file() {
    log_info "Creating environment file template..."
    
    cat > /etc/gemini_relay.env << 'EOF'
# Gemini Relay Environment Configuration
# Edit this file with your actual values

# Gemini API Configuration
GEMINI_API_KEY=
AZURE_KEY_VAULT_NAME=arca-mcp-kv-dae
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
GEMINI_SECRET_NAME=gemini-api-key

# Muninn Memory Spooler
MUNINN_URL=

# Relay Configuration
RELAY_HOST=0.0.0.0
RELAY_PORT=8765
EOF

    chmod 600 /etc/gemini_relay.env
    log_success "Environment file created: /etc/gemini_relay.env"
    log_warning "Edit /etc/gemini_relay.env with your API credentials"
}

# Reload systemd and enable services
enable_services() {
    log_info "Enabling systemd services..."
    
    systemctl daemon-reload
    systemctl enable gemini-relay.service
    systemctl enable cloudflared-tunnel.service
    
    log_success "Services enabled"
}

# Print next steps
print_next_steps() {
    echo ""
    echo "============================================================"
    echo "  VPS Provisioning Complete!"
    echo "============================================================"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Configure environment variables:"
    echo "   sudo nano /etc/gemini_relay.env"
    echo ""
    echo "2. Copy your application files to $GEMINI_RELAY_DIR:"
    echo "   scp main.py requirements.txt root@your-vps:$GEMINI_RELAY_DIR/"
    echo ""
    echo "3. Install Python dependencies:"
    echo "   cd $GEMINI_RELAY_DIR && sudo -u gemini ./venv/bin/pip install -r requirements.txt"
    echo ""
    echo "4. Configure Cloudflare Tunnel:"
    echo "   sudo cloudflared tunnel login"
    echo "   sudo cloudflared tunnel create gemini-relay"
    echo "   sudo cloudflared tunnel route dns gemini-relay your-domain.com"
    echo ""
    echo "5. Start services:"
    echo "   sudo systemctl start cloudflared-tunnel"
    echo "   sudo systemctl start gemini-relay"
    echo ""
    echo "6. Check status:"
    echo "   sudo systemctl status gemini-relay"
    echo "   sudo systemctl status cloudflared-tunnel"
    echo ""
    echo "7. View logs:"
    echo "   sudo journalctl -u gemini-relay -f"
    echo "   sudo journalctl -u cloudflared-tunnel -f"
    echo ""
    echo "============================================================"
}

# Main execution
main() {
    echo ""
    echo "============================================================"
    echo "  Gemini Relay VPS Provisioning"
    echo "  Ubuntu Micro VPS (0.1 vCPU / 512MB RAM)"
    echo "============================================================"
    echo ""
    
    check_root
    update_packages
    install_python
    install_cloudflared
    create_user
    create_directory
    install_dependencies
    create_relay_service
    create_tunnel_service
    create_env_file
    enable_services
    print_next_steps
}

# Run main function
main "$@"
