#!/bin/bash
# ARCA MCP Server Runtime Deployment Script
# Deploys runtime artifacts to OCI workhorse instance

set -e

# Configuration
ARTIFACT_NAME="runtime.tar.gz"
SOURCE_PATH="/tmp/${ARTIFACT_NAME}"
TARGET_PATH="/home/ubuntu/ARCA/services/mcp_server"
SERVICE_NAME="mcp_server"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Starting ARCA MCP Server Runtime Deployment${NC}"

# Check if artifact exists
if [ ! -f "$SOURCE_PATH" ]; then
    echo -e "${RED}❌ Runtime artifact not found: $SOURCE_PATH${NC}"
    echo -e "${YELLOW}💡 Make sure to transfer the artifact first:${NC}"
    echo -e "   scp arm64-runtime-artifact/runtime.tar.gz ubuntu@100.124.13.62:/tmp/"
    exit 1
fi

echo -e "${YELLOW}📦 Deploying runtime artifact...${NC}"

# Stop existing service
echo -e "${YELLOW}🛑 Stopping existing MCP server...${NC}"
cd "$TARGET_PATH"
docker-compose down || true

# Backup current deployment (optional)
BACKUP_DIR="/home/ubuntu/ARCA/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
echo -e "${YELLOW}💾 Creating backup in $BACKUP_DIR...${NC}"
cp -r . "$BACKUP_DIR/" 2>/dev/null || true

# Clean current directory (keep docker-compose.yml and scripts)
echo -e "${YELLOW}🧹 Cleaning deployment directory...${NC}"
find . -mindepth 1 -not -name "docker-compose.yml" -not -name "*.sh" -not -name "*.md" -exec rm -rf {} + 2>/dev/null || true

# Extract runtime artifact
echo -e "${YELLOW}📦 Extracting runtime artifact...${NC}"
tar -xzf "$SOURCE_PATH"

# Ensure proper permissions
echo -e "${YELLOW}🔐 Setting proper permissions...${NC}"
chmod +x *.py *.sh 2>/dev/null || true
mkdir -p /home/ubuntu/ARCA/genesis
chmod 777 /home/ubuntu/ARCA/genesis

# Start the service
echo -e "${YELLOW}🚀 Starting MCP server...${NC}"
docker-compose up -d

# Wait for health check
echo -e "${YELLOW}🏥 Waiting for service to be healthy...${NC}"
sleep 10

# Check health
if curl -f http://localhost:8086/health >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Deployment successful!${NC}"
    echo -e "${GREEN}🌐 MCP Server is running on port 8086${NC}"
else
    echo -e "${RED}❌ Health check failed${NC}"
    echo -e "${YELLOW}📋 Checking service status...${NC}"
    docker-compose ps
    docker-compose logs --tail=20
    exit 1
fi

# Clean up
echo -e "${YELLOW}🧹 Cleaning up temporary files...${NC}"
rm -f "$SOURCE_PATH"

echo -e "${GREEN}🎉 Deployment complete!${NC}"