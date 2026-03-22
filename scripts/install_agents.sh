#!/bin/bash
#
# Biomimetics LaunchAgent Installer
# Loads all LaunchAgents for continuous operation
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCH_AGENTS_DIR="$SCRIPT_DIR/../launch_agents"
USER_LAUNCH_DIR="$HOME/Library/LaunchAgents"

echo "Biomimetics LaunchAgent Installer"
echo "================================="
echo ""

# Ensure user LaunchAgents directory exists
mkdir -p "$USER_LAUNCH_DIR"

# Copy and load each plist
for plist in "$LAUNCH_AGENTS_DIR"/*.plist; do
    if [ -f "$plist" ]; then
        filename=$(basename "$plist")
        target="$USER_LAUNCH_DIR/$filename"
        
        echo "Installing: $filename"
        
        # Copy to user LaunchAgents
        cp "$plist" "$target"
        
        # Unload if already loaded (ignore errors)
        launchctl unload "$target" 2>/dev/null || true
        
        # Load the agent
        if launchctl load "$target"; then
            echo "  ✓ Loaded: $filename"
        else
            echo "  ✗ Failed: $filename"
        fi
    fi
done

echo ""
echo "Verification:"
echo "-------------"
launchctl list | grep "com.arca" || echo "  No ARCA agents found (may need logout/login)"

echo ""
echo "Done! Agents will start on next login."
echo "To view logs: tail -f ~/.arca/*.log"
