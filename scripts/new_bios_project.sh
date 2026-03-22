#!/bin/bash
# Script to generate a new BiOS Filament project template

if [ -z "$1" ]; then
    echo "Usage: $0 <project_path>"
    exit 1
fi

PROJECT_PATH="$1"

echo "Creating new BiOS project at: $PROJECT_PATH"

# Create directories
mkdir -p "$PROJECT_PATH"/{.agents/rules,.agents/workflows,.zed,.bios,docs/KNOWLEDGE_GRAPH,src}

# Create marker files
cat > "$PROJECT_PATH/.agents/rules/bios_core.md" << 'EOF'
# BiOS Core Constraints
EOF

cat > "$PROJECT_PATH/.zed/settings.json" << 'EOF'
{
  "agent_servers": {
    "BiOS_PM": {
      "type": "custom",
      "command": "python3",
      "args": [
        "~/.copaw/bios_orchestrator.py"
      ],
      "env": {
        "NOTION_DB_ID": "3224d2d9fc7c80deb18dd94e22e5bb21",
        "GCP_GATEWAY": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
      }
    }
  }
}
EOF

cat > "$PROJECT_PATH/.bios/manifest.json" << 'EOF'
{
  "project_id": "",
  "notion_id": "",
  "gcp_id": ""
}
EOF

cat > "$PROJECT_PATH/.bios/sync_heartbeat.sh" << 'EOF'
#!/bin/bash
# Local wrapper for omni_sync.py
echo "Sync heartbeat ping"
EOF
chmod +x "$PROJECT_PATH/.bios/sync_heartbeat.sh"

cat > "$PROJECT_PATH/docs/ARCHITECTURE.md" << 'EOF'
# High-Level System Design
EOF

cat > "$PROJECT_PATH/docs/GUIDELINES.md" << 'EOF'
# Rules for Agent-Human collaboration
EOF

echo "BiOS project template instantiated at $PROJECT_PATH"
