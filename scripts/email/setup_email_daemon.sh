#!/bin/bash
#
# Setup Email Ingestion Daemon
# Configures LaunchAgent for all 5 ProtonMail accounts
# Uses password from secrets/proton_bridge_password
#

set -euo pipefail

LAUNCH_AGENT_PLIST="$HOME/Library/LaunchAgents/com.arca.email-ingest.plist"
SECRETS_DIR="$HOME/biomimetics/secrets"
PASSWORD_FILE="$SECRETS_DIR/proton_bridge_password"

echo "📧 Email Ingestion Daemon Setup"
echo "================================"
echo ""

# Create secrets directory if needed
mkdir -p "$SECRETS_DIR"

# Check if password file exists
if [ -f "$PASSWORD_FILE" ]; then
    echo "✓ Found Proton Bridge password: $PASSWORD_FILE"
else
    echo "Enter Proton Mail Bridge password:"
    echo "(All 5 accounts use the same password)"
    echo ""
    read -s -p "Bridge password: " BRIDGE_PASS
    echo ""
    echo "$BRIDGE_PASS" > "$PASSWORD_FILE"
    chmod 600 "$PASSWORD_FILE"
    echo "✓ Password saved to: $PASSWORD_FILE"
fi

echo ""
echo "Accounts configured:"
echo "  1. dan.exall@pm.me"
echo "  2. dan@arca-vsa.tech"
echo "  3. claws@arca-vsa.tech"
echo "  4. arca@arca-vsa.tech"
echo "  5. info@arca-vsa.tech"
echo ""

# Setup LaunchAgent
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_PLIST="$SCRIPT_DIR/../launch_agents/com.arca.email-ingest.plist"

if [ -f "$SOURCE_PLIST" ]; then
    cp "$SOURCE_PLIST" "$LAUNCH_AGENT_PLIST"
    
    # Add environment variables to plist
    /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:PROTON_BRIDGE_PASSWORD string $(cat $PASSWORD_FILE)" "$LAUNCH_AGENT_PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:PROTON_BRIDGE_PASSWORD $(cat $PASSWORD_FILE)" "$LAUNCH_AGENT_PLIST"
    
    /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:PROTONMAIL_IMAP_HOST string 127.0.0.1" "$LAUNCH_AGENT_PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:PROTONMAIL_IMAP_HOST 127.0.0.1" "$LAUNCH_AGENT_PLIST"
    
    /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:PROTONMAIL_IMAP_PORT string 1143" "$LAUNCH_AGENT_PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:PROTONMAIL_IMAP_PORT 1143" "$LAUNCH_AGENT_PLIST"
    
    echo "✓ LaunchAgent configured: $LAUNCH_AGENT_PLIST"
else
    echo "⚠️  Source plist not found: $SOURCE_PLIST"
    exit 1
fi

# Unload if already loaded
launchctl unload "$LAUNCH_AGENT_PLIST" 2>/dev/null || true

# Load the agent
if launchctl load "$LAUNCH_AGENT_PLIST"; then
    echo "✓ LaunchAgent loaded"
else
    echo "⚠️  Failed to load LaunchAgent"
fi

echo ""
echo "================================"
echo "Setup complete!"
echo ""
echo "To test manually:"
echo "  python3 $SCRIPT_DIR/email-ingestion-daemon.py --once"
echo ""
echo "To view logs:"
echo "  tail -f ~/.arca/email-ingest.log"
echo ""
echo "To disable:"
echo "  launchctl unload $LAUNCH_AGENT_PLIST"
