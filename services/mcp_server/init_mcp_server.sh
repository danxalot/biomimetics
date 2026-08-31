#!/bin/bash
# MCP Server Initialization Script
# Ensures all required data, skills, and tools are properly loaded on container startup
# This script runs BEFORE the main server starts to guarantee persistence

# set -e  # Disabled to prevent premature exit on non-critical setup failures

echo "========================================================================"
echo "🚀 ARCA MCP Server - Initialization Script"
echo "========================================================================"
echo "Date: $(date)"
echo ""

# ============================================================================
# ENVIRONMENT VALIDATION
# ============================================================================
echo "📋 Validating Environment..."

REQUIRED_DIRS=(
    "${MCP_DATA_DIR:-/app/data}"
    "${MCP_SKILLS_DIR:-/app/skills}"
    "${TOOLS_DIR:-/app/tools}"
    "${MCP_REASONING_DIR:-/app/reasoning_bank}"
    "/app/cache"
    "/app/logs"
    "/app/shared_storage"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "⚠️  Creating missing directory: $dir"
        mkdir -p "$dir"
    else
        echo "✅ Directory exists: $dir"
    fi
    # Ensure app user has ownership of the directory
    if [ "$dir" != "/app/shared_storage" ]; then
        chown -R app:app "$dir" 2>/dev/null || true
    fi
done

# ============================================================================
# SKILLS REGISTRY INITIALIZATION
# ============================================================================
echo ""
echo "📚 Initializing Skills Registry..."

DATA_DIR="${MCP_DATA_DIR:-/app/data}"
SKILLS_DIR="${MCP_SKILLS_DIR:-/app/skills}"

# Check if enhanced registry exists and copy to standard location if needed
if [ -f "$DATA_DIR/skills_registry_enhanced.json" ]; then
    echo "✅ Found enhanced skills registry"
    
    # Always ensure standard registry is up to date with enhanced version
    if [ ! -f "$DATA_DIR/skills_registry.json" ] || \
       [ "$DATA_DIR/skills_registry_enhanced.json" -nt "$DATA_DIR/skills_registry.json" ]; then
        echo "📝 Updating skills_registry.json from enhanced version..."
        cp "$DATA_DIR/skills_registry_enhanced.json" "$DATA_DIR/skills_registry.json"
        echo "✅ Skills registry synchronized"
    else
        echo "✅ Skills registry already current"
    fi
    
    # Count skills in registry
    SKILL_COUNT=$(python3 -c "import json; print(len(json.load(open('$DATA_DIR/skills_registry_enhanced.json'))))" 2>/dev/null || echo "unknown")
    echo "📊 Skills in registry: $SKILL_COUNT"
else
    echo "⚠️  Enhanced skills registry not found - will be created on first run"
fi

# Count markdown skills
if [ -d "$SKILLS_DIR" ]; then
    MD_COUNT=$(find "$SKILLS_DIR" -name "*.md" -type f | wc -l | tr -d ' ')
    echo "📊 Markdown skill files: $MD_COUNT"
else
    echo "⚠️  Skills directory not mounted: $SKILLS_DIR"
fi

# ============================================================================
# TOOLS VALIDATION
# ============================================================================
echo ""
echo "🔧 Validating MCP Tools..."

TOOLS_DIR="${TOOLS_DIR:-/app/tools}"

if [ -d "$TOOLS_DIR" ]; then
    TOOL_COUNT=$(find "$TOOLS_DIR" -name "mcp_*.py" -type f | wc -l | tr -d ' ')
    echo "📊 Tool modules found: $TOOL_COUNT"
    
    # List all available tools
    echo "📝 Available tools:"
    find "$TOOLS_DIR" -name "mcp_*.py" -type f -exec basename {} .py \; | sed 's/^/   - /'
else
    echo "⚠️  Tools directory not mounted: $TOOLS_DIR"
fi

# ============================================================================
# REASONING BANK VALIDATION
# ============================================================================
echo ""
echo "🧠 Validating Reasoning Bank..."

REASONING_DIR="${MCP_REASONING_DIR:-/app/reasoning_bank}"

if [ -d "$REASONING_DIR" ]; then
    REASONING_COUNT=$(find "$REASONING_DIR" -name "*.json" -type f | wc -l | tr -d ' ')
    echo "📊 Reasoning trajectories: $REASONING_COUNT"
else
    echo "⚠️  Reasoning bank directory not mounted: $REASONING_DIR"
    echo "   Creating directory..."
    mkdir -p "$REASONING_DIR"
fi

# ============================================================================
# CACHE & LOGS SETUP
# ============================================================================
echo ""
echo "💾 Setting up Cache & Logs..."

# Ensure cache directories
mkdir -p /app/cache/models
mkdir -p /app/cache/embeddings
mkdir -p /app/logs/startup
mkdir -p /app/logs/skills
mkdir -p /app/logs/reasoning

echo "✅ Cache and log directories ready"

# ============================================================================
# VOLUME MOUNT VALIDATION
# ============================================================================
echo ""
echo "🔍 Validating Volume Mounts..."

# Check if volumes are properly mounted (read-write test)
if [ -w "$DATA_DIR" ]; then
    echo "✅ Data directory is writable: $DATA_DIR"
else
    echo "❌ ERROR: Data directory is NOT writable: $DATA_DIR"
    exit 1
fi

if [ -d "/app/shared_storage" ] && [ -w "/app/shared_storage" ]; then
    echo "✅ Shared storage is writable: /app/shared_storage"
else
    echo "⚠️  Shared storage is NOT writable (may be read-only)"
fi

# ============================================================================
# CONFIGURATION SUMMARY
# ============================================================================
echo ""
echo "========================================================================"
echo "📊 MCP SERVER CONFIGURATION SUMMARY"
echo "========================================================================"
echo "Data Directory:      $DATA_DIR"
echo "Skills Directory:    $SKILLS_DIR"
echo "Tools Directory:     $TOOLS_DIR"
echo "Reasoning Directory: $REASONING_DIR"
echo "Port:               ${PORT:-8086}"
echo "TLS Enabled:        ${MCP_TLS_ENABLED:-false}"
echo ""
echo "Memory Limits:"
echo "  - Container Limit: 1.5G"
echo "  - Reservation:     1.0G"
echo ""
echo "Service Dependencies:"
echo "  - LLM Gateway:      ${LLM_GATEWAY_URL:-not set}"
echo "  - Embedding:        ${EMBEDDING_SERVICE_URL:-not set}"
echo "  - Memory System:    ${MEMORY_SYSTEM_URL:-not set}"
echo "========================================================================"
echo ""

# ============================================================================
# STARTUP TIMESTAMP
# ============================================================================
echo "$(date '+%Y-%m-%d %H:%M:%S') - MCP Server initialization complete" > /app/logs/startup/last_init.log

# ============================================================================
# PORT CONFLICT DETECTION
# ============================================================================
echo ""
echo "🔍 Checking for port 8086 conflicts..."
# Use /proc/net/tcp to find processes on 8086 (0x1F96)
PORT_HEX="1F96"
if grep -q ":$PORT_HEX " /proc/net/tcp; then
    echo "⚠️ Port 8086 is already in use. Identifying process..."
    # Find PIDs of processes owned by app or root that might be holding the port
    for pid in $(ls /proc | grep -E '^[0-9]+$'); do
        if [ -d "/proc/$pid/fd" ]; then
            if ls -l "/proc/$pid/fd" 2>/dev/null | grep -q "socket:"; then
                # This process has sockets open, let's look closer if needed
                # For now, if it's a python3 process not being us, we might want to kill it
                if grep -q "python3" "/proc/$pid/cmdline" 2>/dev/null; then
                    echo "🔥 Killing orphaned python3 process (PID $pid) holding port 8086..."
                    kill -9 "$pid" || true
                fi
            fi
        fi
    done
    sleep 2
fi

echo "✅ Initialization complete - starting MCP server..."
echo ""

# ============================================================================
# DOCKER SOCKET PERMISSIONS
# ============================================================================
echo ""
echo "🐳 Configuring Docker Socket Permissions..."

DOCKER_SOCKET="/var/run/docker.sock"

if [ -e "$DOCKER_SOCKET" ]; then
    SOCKET_GID=$(stat -c '%g' "$DOCKER_SOCKET")
    echo "   Docker socket GID: $SOCKET_GID"
    
    # Check if a group with this GID exists
    if getent group "$SOCKET_GID" > /dev/null; then
        GROUP_NAME=$(getent group "$SOCKET_GID" | cut -d: -f1)
        echo "   Group exists: $GROUP_NAME"
    else
        GROUP_NAME="docker_sock"
        echo "   Creating group '$GROUP_NAME' with GID $SOCKET_GID"
        groupadd -g "$SOCKET_GID" "$GROUP_NAME"
    fi
    
    # Add app user to the group
    echo "   Adding 'app' user to group '$GROUP_NAME'"
    usermod -aG "$GROUP_NAME" app 2>/dev/null || echo "   ⚠️  Could not modify user groups (permission denied or read-only)"
else
    echo "⚠️  Docker socket not found at $DOCKER_SOCKET"
fi

# ============================================================================
# EXECUTE SERVER AS 'app' USER
# ============================================================================
echo ""
echo "🚀 Starting MCP Server..."
# Execute directly without privilege dropping to avoid su/gosu auth failures
cd /app && exec python3 mcp_server.py
