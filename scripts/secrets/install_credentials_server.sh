#!/bin/bash
#
# Azure Credentials Server LaunchAgent
# Auto-starts on login, keeps running, restarts on crash
#

cat << 'PLIST' > ~/Library/LaunchAgents/com.bios.credentials-server.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bios.credentials-server</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/Users/danexall/biomimetics/scripts/secrets/venv/bin/python</string>
        <string>/Users/danexall/biomimetics/scripts/secrets/credentials_server.py</string>
    </array>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>CREDENTIALS_API_KEY</key>
        <string>__CREDENTIALS_API_KEY__</string>
        <key>CREDENTIALS_PORT</key>
        <string>8089</string>
        <key>AZURE_KEY_VAULT_NAME</key>
        <string>arca-mcp-kv-dae</string>
    </dict>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>/Users/danexall/biomimetics/logs/credentials_server.log</string>
    
    <key>StandardErrorPath</key>
    <string>/Users/danexall/biomimetics/logs/credentials_server.err</string>
    
    <key>ProcessType</key>
    <string>Background</string>
    
    <key>LowPriorityIO</key>
    <true/>
</dict>
</plist>
PLIST

echo "LaunchAgent created. To install:"
echo "  cp ~/Library/LaunchAgents/com.bios.credentials-server.plist ~/Library/LaunchAgents/"
echo "  launchctl load ~/Library/LaunchAgents/com.bios.credentials-server.plist"
echo ""
echo "To start manually:"
echo "  python3 ~/biomimetics/scripts/secrets/credentials_server.py"
