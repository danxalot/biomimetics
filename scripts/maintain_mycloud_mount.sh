#!/bin/bash
#
# ARCA MyCloud Home SMB Mount Watchdog
# Maintains persistent connection to MyCloud Home NAS
#
# Logic:
#   - If /Volumes/danexall missing: create and mount
#   - If present: touch .keepalive to force network activity
#

set -euo pipefail

# Configuration
MOUNT_POINT="/Volumes/danexall"
SMB_USER="danexall"
SMB_PASS="Christ123"
SMB_HOST="192.168.0.103"
SMB_SHARE="danexall"
LOG_FILE="$HOME/.arca/mycloud_watchdog.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if mount point exists
if [ ! -d "$MOUNT_POINT" ]; then
    log "Mount point missing. Creating directory..."
    mkdir -p "$MOUNT_POINT"
fi

# Check if already mounted (by testing if it's an actual mount)
if mount | grep -q "$MOUNT_POINT"; then
    log "Mount already active at $MOUNT_POINT. Sending keepalive..."
    # Force network activity to prevent sleep timeout
    touch "$MOUNT_POINT/.keepalive"
    
    # Additional keepalive: list directory to maintain connection
    ls -la "$MOUNT_POINT" > /dev/null 2>&1 || true
    
    log "Keepalive sent successfully"
else
    log "Mount not active. Attempting to mount SMB share..."
    
    # Unmount any stale mount first
    if [ -d "$MOUNT_POINT" ]; then
        umount "$MOUNT_POINT" 2>/dev/null || true
        sleep 1
    fi
    
    # Recreate mount point
    mkdir -p "$MOUNT_POINT"
    
    # Mount SMB share
    # URL format: //user:pass@host/share
    SMB_URL="//${SMB_USER}:${SMB_PASS}@${SMB_HOST}/${SMB_SHARE}"
    
    if mount_smbfs "$SMB_URL" "$MOUNT_POINT" 2>&1; then
        log "Successfully mounted $SMB_SHARE to $MOUNT_POINT"
        
        # Create keepalive file
        touch "$MOUNT_POINT/.keepalive"
        
        # Verify mount
        if mount | grep -q "$MOUNT_POINT"; then
            log "Mount verified successfully"
        else
            log "WARNING: Mount may not be active despite successful command"
        fi
    else
        log "ERROR: Failed to mount SMB share. Check credentials and network."
        exit 1
    fi
fi

log "Watchdog cycle complete"
exit 0
