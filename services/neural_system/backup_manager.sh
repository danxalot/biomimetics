#!/bin/bash
# Backup and Upgrade Manager for ARCA Neural System State

BACKUP_DIR="/data/arca_state_backups"
STATE_FILE=".sync_state.json" # Or whatever primary state files exist

mkdir -p "$BACKUP_DIR/hourly"
mkdir -p "$BACKUP_DIR/daily"

function do_backup() {
    local ts=$(date +"%Y%m%d_%H%M%S")
    local type=$1
    local dest="$BACKUP_DIR/$type"
    
    echo "Creating $type backup at $ts..."
    # Backup relevant state files (assuming they are in the project root or specified paths)
    # We will backup Redis state and local .json states
    
    tar -czf "$dest/state_$ts.tar.gz" .sync_state.json arca_state.json 2>/dev/null || echo "No local json state files found to backup."
    
    # Prune old backups
    if [ "$type" == "hourly" ]; then
        # Keep only last 24 hourly backups
        ls -tp "$dest"/state_*.tar.gz | grep -v '/$' | tail -n +25 | xargs -I {} rm -- {} 2>/dev/null
    elif [ "$type" == "daily" ]; then
        # Keep only last 3 daily backups
        ls -tp "$dest"/state_*.tar.gz | grep -v '/$' | tail -n +4 | xargs -I {} rm -- {} 2>/dev/null
    fi
}

function upgrade_and_restore() {
    echo "Upgrading container and restoring state..."
    # 1. Take a pre-upgrade backup
    do_backup "hourly"
    
    local latest_backup=$(ls -tp "$BACKUP_DIR/hourly"/state_*.tar.gz | head -n 1)
    
    if [ -n "$latest_backup" ]; then
        echo "Found latest backup: $latest_backup"
        # Extract state to a safe temporary location
        mkdir -p /tmp/arca_state_restore
        tar -xzf "$latest_backup" -C /tmp/arca_state_restore
    fi

    # 2. Perform Upgrade (e.g. docker-compose pull && docker-compose up -d)
    echo "Pulling latest images..."
    # Assuming standard docker-compose workflow in ARCA
    if [ -f "docker-compose.yml" ]; then
        docker-compose pull neural_system
        docker-compose up -d neural_system
    else
        echo "Warning: docker-compose.yml not found. Please upgrade manually."
    fi

    # 3. Restore state
    if [ -d "/tmp/arca_state_restore" ]; then
        echo "Restoring state files..."
        cp -a /tmp/arca_state_restore/* ./ 2>/dev/null
        rm -rf /tmp/arca_state_restore
    fi
    echo "Upgrade and restore complete."
}

function run_daemon() {
    echo "Starting backup daemon..."
    while true; do
        do_backup "hourly"
        
        # Check if it's midnight to run daily backup
        local hour=$(date +"%H")
        if [ "$hour" == "00" ]; then
            do_backup "daily"
        fi
        
        sleep 3600
    done
}

case "$1" in
    hourly)
        do_backup "hourly"
        ;;
    daily)
        do_backup "daily"
        ;;
    upgrade)
        upgrade_and_restore
        ;;
    daemon)
        run_daemon
        ;;
    *)
        echo "Usage: $0 {hourly|daily|upgrade|daemon}"
        exit 1
        ;;
esac
